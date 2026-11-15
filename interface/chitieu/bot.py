"""Định tuyến bot chi tiêu: bảng lệnh /..., trả lời một tin nhắn (lệnh, khoản chi/thu, câu nói thường), ghi khoản kèm các
dòng phụ, và lượt bấm nút của mọi chức năng. Chỗ duy nhất biết chức năng nào xử lý lệnh/nút nào."""
import html
import sys

from domain.chitieu.kinds import INCOME, OTHER
from domain.chitieu.learn import pending
from domain.chitieu.refs import button_ref
from domain.common.format import vnd
from domain.common.text import plain
from infrastructure import ai as ai_client
from interface import common
from interface.chitieu import commands, features
from interface.chitieu.context import (CHI_BUTTONS, REPORT_BUTTONS, SORT_TITLE, entries_message, groups, name,
                                       report, reset, today)
from presentation.chitieu.view import NEED_STORE
from repositories.chitieu import groups as groups_repo
from repositories.chitieu import ledger as ledger_repo
from services.chitieu import ledger


def period_kind(args):
    """Tham số kỳ của /bieudo, /nhanxet: trống là tháng này, '10' là tháng 10, 'thangtruoc'..."""
    word = plain("".join(args))
    if word.isdigit() and 1 <= int(word) <= 12:
        return str(int(word))
    return {"thangtruoc": "thangtruoc", "tuan": "tuan", "tuannay": "tuan", "homnay": "ngay"}.get(word, "thang")

COMMANDS = {
    "baocao": ("Báo cáo chi tiêu, có nút chọn kỳ", commands.baocao),
    "homnay": ("Chi tiêu hôm nay", lambda args: (report("ngay", today())[0], REPORT_BUTTONS)),
    "tuan": ("Chi tiêu tuần này", lambda args: (report("tuan", today())[0], REPORT_BUTTONS)),
    "thang": ("Chi tiêu tháng này; /thang 10 cho tháng 10", commands.thang),
    "lichsu": ("10 khoản gần nhất, bấm ❌ để xóa", commands.lichsu),
    "xoa": ("Xóa khoản vừa ghi", commands.xoa_cuoi),
    "ngansach": ("Ngân sách tháng: /ngansach ăn uống 3tr", commands.ngansach),
    "nhom": ("Các nhóm chi tiêu; tự tạo nhóm, thêm từ khóa", commands.nhom_cmd),
    "chuaxep": ("Xếp nhóm các khoản đang ở Khác", commands.chuaxep),
    "dubao": ("Dự báo chi tiêu hằng ngày (ăn uống, sinh hoạt); /dubao tatca cho mọi khoản",
              lambda args: features.phantich().dubao(args)),
    "hoi": ("Hỏi bằng câu thường: /hoi tháng này cà phê hết bao nhiêu", lambda args: features.phantich().hoi(" ".join(args), today())),
    "bieudo": ("Biểu đồ chi tiêu tháng; /bieudo 10 cho tháng 10", lambda args: features.phantich().chart_reply(period_kind(args), today())),
    "taisan": ("Tài sản ròng: tiền, tiết kiệm, cổ phiếu, vàng, quỹ, nợ…; /taisan huongdan", lambda args: features.taisan().taisan(args)),
    "suckhoe": ("Khám sức khỏe tài chính cá nhân", lambda args: features.taisan().health(today())),
    "luong": ("Nhắc ngày nhận lương: /luong 10 25tr", lambda args: features.taisan().luong(args)),
    "duphong": ("Quỹ dự phòng: mục tiêu, tiến độ, mỗi tháng cần để bao nhiêu", lambda args: features.duphong().duphong(args)),
    "nhanxet": ("Nhận xét chi tiêu tháng (AI); /nhanxet 10 cho tháng 10", lambda args: features.phantich().commentary(period_kind(args), today())),
    "xuat": ("Xuất file CSV mở bằng Excel: /xuat 10", commands.xuat),
    "menu": ("🏠 Hôm nay: đã chi, còn được tiêu, việc cần làm", lambda args: features.menu().menu_cmd(args)),
    "start": ("Bắt đầu", lambda args: features.menu().start(args)),
    "huongdan": ("Cách dùng và mọi lệnh", lambda args: features.menu().guide(args)),
    "no": ("Sổ nợ: còn bao nhiêu, mỗi tháng trả, nhắc trả", lambda args: features.sono().no_cmd(args)),
    "kehoach": ("Lộ trình xây tài sản, chia lương mỗi tháng", lambda args: features.kehoach().kehoach(args)),
    "dautu": ("Đầu tư quỹ mở hằng tháng: tháng này nên mua bao nhiêu", lambda args: features.dautu().dautu(args)),
    "tietkiem": ("Tiết kiệm từ khi dùng bot, chuỗi ngày ghi chép", lambda args: features.tietkiem().tietkiem(args)),
    "doichieu": ("Đối chiếu tài sản tháng: so từng ngăn với app ngân hàng, Fmarket",
                 lambda args: __import__("interface.doichieu.reconcile", fromlist=["doichieu"]).doichieu(args)),
}
COMMANDS["help"] = COMMANDS["huongdan"]
# Danh sách lệnh hiện ở nút Menu của Telegram: chỉ các lệnh chính, lệnh khác vẫn gõ được (/huongdan)
VISIBLE = ["menu", "taisan", "kehoach", "hoi", "baocao", "huongdan"]
MENU = [{"command": n, "description": COMMANDS[n][0]} for n in VISIBLE]

def answer(text, now, chat=None):
    """Trả lời một tin nhắn (respond); tin đầu tiên sau khi đổi hàng nút dưới ô chat thì kèm hàng nút mới."""
    reply = respond(text, now, chat)
    if isinstance(reply, (str, tuple)) and common.ready():
        reply = features.menu().with_keyboard(reply)
    return reply

def respond(text, now, chat=None):
    """Trả lời một tin nhắn: lệnh, khoản chi/thu cần ghi, hoặc câu nói thường về việc khác (troly.py hiểu, hỏi lại
    khi thiếu, xin xác nhận trước khi ghi). chat: mã chat, để nhớ bot đang hỏi dở việc gì."""
    if not common.ready():
        return NEED_STORE
    reset()
    helper = features.troly()
    screen = features.menu().from_keyboard(text)  # nút cố định dưới ô chat
    if screen:
        helper.forget(chat)
        return screen
    many = features.menu().run_lines(text, now)  # nhiều lệnh, mỗi lệnh một dòng
    if many:
        return many
    parts = text.split()
    if parts and parts[0].startswith("/"):
        helper.forget(chat)  # gõ lệnh: bỏ việc đang hỏi dở
        command = parts[0][1:].split("@")[0].lower()
        if command in COMMANDS:
            return COMMANDS[command][1](parts[1:])
        return f"Không có lệnh /{html.escape(command[:30])}. Bấm /menu để mở menu, /huongdan để xem mọi lệnh"
    pending = helper.on_reply(text, now, chat)  # bot đang hỏi dở, hoặc đang chờ lời sửa một thẻ
    if pending is not None:
        return pending
    traded = features.taisan().trade(text, now)  # "mua 1000 FPT giá 95", "bán 500 FPT giá 120"
    if traded:
        return traded
    fund_order = features.dautu().from_text(text, now)  # "mua VMEEF 3tr": ghi lệnh mua quỹ đang đầu tư
    if fund_order:
        return fund_order
    known = helper.quick(text, now)  # "hôm nay không tiêu gì": hiểu bằng luật, không cần AI
    if known is not None:
        return known
    question = features.phantich().is_question(text)
    if question and not (ai_client.key() and helper.beyond_spending(text)):
        return features.phantich().hoi(text, now.date())  # câu hỏi về chi tiêu đã ghi
    if question or helper.wants(text):  # không phải khoản chi thường: nhờ AI hiểu câu
        reply = helper.understand(text, now, chat, question)
        if reply is not None:
            return reply
    return record_text(text, now)

def record_text(text, now):
    """Ghi các khoản chi/thu trong tin nhắn (mỗi dòng một khoản) và trả câu báo kèm nút."""
    entries = ledger.add(text, now)
    if not entries:
        return "Không thấy số tiền. Nhắn kiểu: <b>cà phê 35k</b> hoặc bấm /menu"
    debt_lines, debt_rows = debt_after(entries, now.date())
    try:
        extra = features.phantich().after_record(entries, now.date())
    except Exception as e:  # phần phân tích lỗi thì vẫn báo đã ghi
        print(f"[lỗi] phân tích sau khi ghi: {e!r}", file=sys.stderr)
        extra = []
    try:
        extra += features.tietkiem().after_record(entries, now.date())  # 🔥 chuỗi ngày ghi · hôm nay so với mốc · đã bớt
    except Exception as e:
        print(f"[lỗi] tiết kiệm sau khi ghi: {e!r}", file=sys.stderr)
    reply, rows = entries_message(entries, now.date(), extra=debt_lines + extra)
    rows = (rows or []) + debt_rows
    hint = salary_fund_hint(entries, now.date())
    if hint:
        reply, rows = reply + "\n" + hint[0], rows + [hint[1]]
    return reply, rows

def salary_fund_hint(entries, day):
    """Vừa ghi lương: (dòng gợi ý chia lương, hàng nút) — trả nợ, chi tiêu, quỹ dự phòng; None nếu không cần."""
    try:
        return features.kehoach().salary_hint(entries, day)
    except Exception as e:
        print(f"[lỗi] gợi ý chia lương: {e!r}", file=sys.stderr)
        return None

def debt_after(entries, day):
    """Khoản vừa ghi là trả nợ thì trừ dư nợ: (dòng thêm, hàng nút); lỗi thì bỏ qua, khoản vẫn được ghi."""
    try:
        return features.sono().after_record(entries, day)
    except Exception as e:
        print(f"[lỗi] trừ dư nợ: {e!r}", file=sys.stderr)
        return [], []

def refs_in(message):
    """Các khoản có nút dưới tin, theo thứ tự xuất hiện."""
    refs = [button_ref(data) for row in common.keyboard_rows(message) for _, data in row]
    return list(dict.fromkeys(r for r in refs if r))

def render(refs, day, message=None, focus=None):
    sorting = ((message or {}).get("text") or "").startswith(SORT_TITLE)
    return entries_message([e for e in map(ledger.find, refs) if e], day, sorting, focus)

def on_button(data, message, now):
    """Bấm nút: trả (thông báo nhỏ, việc tiếp theo) như lenh.on_button."""
    if not common.ready():
        return "Chưa có kho dữ liệu", None
    reset()
    kind, _, arg = data.partition(":")
    day = now.date()
    if kind == "bc":
        rows = CHI_BUTTONS if common.from_menu(message) else REPORT_BUTTONS
        return None, ("edit", lambda: (report(arg, day)[0], rows))
    if kind == "m":
        return features.menu().on_button(arg, message, now)
    if kind == "no":
        return features.sono().on_button(arg, message, now)
    if kind == "kh":
        return features.kehoach().on_button(arg, message, now)
    if kind == "ts":
        return features.taisan().on_button(arg, message, now)
    if kind == "anh":
        import docanh
        return docanh.on_button(arg, message, now)
    if kind == "dp":
        return features.duphong().on_button(arg, message, now)
    if kind == "dc":
        from interface.doichieu import reconcile as doichieu
        return doichieu.on_button(arg, message, now)
    if kind == "dt":
        return features.dautu().on_button(arg, message, now)
    if kind == "tk":
        return features.tietkiem().on_button(arg, message, now)
    if kind == "y":
        return features.troly().on_button(arg, message, now)
    if kind == "bd":
        return "Đang vẽ biểu đồ…", ("send", lambda: features.phantich().chart_reply(arg, day))
    if kind == "db":
        return None, ("send", lambda: features.phantich().daily_text(day))
    if kind == "nx":
        return "AI đang viết nhận xét, chờ chút…", ("send", lambda: features.phantich().commentary(arg, day))
    if kind == "xls":
        gone = commands.delete(arg)
        return ("Đã xóa" if gone else "Khoản này đã xóa rồi"), ("edit", lambda: commands.lichsu([]))
    refs = refs_in(message)
    if kind == "doi":
        return "Chọn nhóm đúng cho khoản này", ("edit", lambda: render(refs, day, message, focus=arg))
    if kind == "nhom":
        reference, _, code = arg.rpartition(":")
        e = ledger.find(reference)
        if e is None:
            return "Khoản này đã xóa rồi", ("edit", lambda: render(refs, day, message))
        if code not in groups():
            return "Nhóm này không còn, chọn nhóm khác", ("edit", lambda: render(refs, day, message))
        if e.get("ai") and code != e["nhom"]:
            groups_repo.add_ai_fixed(1)  # AI đoán sai
        e["nhom"] = code
        e.pop("ai", None)  # người dùng đã chọn, không còn là AI đoán
        e.pop("dekhac", None)
        if code == OTHER:
            e["dekhac"] = True  # tự chọn Khác: không hỏi lại
        ledger_repo.save(e)
        moved = 0
        if code not in (INCOME, OTHER):
            ledger.learn(e["ghichu"], code)
            moved = ledger.tidy(day)  # khoản khác cùng nội dung đang ở Khác cũng xếp luôn
        toast = f"Đã chuyển sang {name(code)}, lần sau bot tự nhớ" + (
            f" (xếp luôn {moved} khoản giống vậy)" if moved else "")
        return toast, ("edit", lambda: render(refs, day, message))
    if kind == "giu":
        e = ledger.find(arg)
        if e and pending(e):  # "📦 Để ở Khác": không hỏi lại khoản này
            e["dekhac"] = True
            ledger_repo.save(e)
            return "Để ở Khác", ("edit", lambda: render(refs, day, message))
        return None, ("edit", lambda: render(refs, day, message))
    if kind == "xoa":
        gone = commands.delete(arg)
        return ("Đã xóa" if gone else "Khoản này đã xóa rồi"), ("edit", lambda: render(refs, day, message))
    return None, None
