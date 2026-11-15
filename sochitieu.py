"""Bot ghi chi tiêu: nhắn "cà phê 35k" là bot ghi lại và tự xếp nhóm; phần nhận tin ở api/chitieu.py.

Mỗi lệnh trả về tin nhắn HTML, hoặc (tin nhắn, nút bấm) như lenh.py; /xuat trả về file CSV.
Xem thử (chỉ đọc và xếp nhóm, không ghi): python sochitieu.py "cà phê 35k"
"""
import base64
import csv
import html
import io
import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.request
from calendar import monthrange
from datetime import date, datetime, timedelta

from domain.chitieu import classify as classify_rules
from domain.chitieu import income as income_rules
from domain.chitieu import period as periods
from domain.chitieu import labels
from domain.chitieu import text as chitieu_text
from domain.chitieu.learn import MAX_LEARNED, NOISE, learn_key, pending  # noqa: F401
from domain.chitieu import parse as parse_rules
from domain.chitieu.categories import (AMBIGUOUS_PLAIN, CATEGORIES, GENERIC, KEYWORDS, plain_pattern,  # noqa: F401
                                       word_pattern)
from domain.chitieu.kinds import INCOME, OTHER  # noqa: F401
from domain.chitieu.parse import DATE, DAY_WORDS, TAG  # noqa: F401
from domain.common import format as format_text
from domain.common.money import MONEY, QUANTITY, UNITS, money, money_count, parse_amount, to_number  # noqa: F401
from domain.common.text import norm, plain  # noqa: F401
from infrastructure import kho
from repositories import keys
from repositories.chitieu import groups as groups_repo
from repositories.chitieu import ledger as ledger_repo
from bantin import VN_TZ, vn_num

MAX_GROUPS, MAX_WORDS = 20, 60  # số nhóm tự tạo, số từ khóa tự thêm cho mỗi nhóm

NEED_STORE = "⚠️ Bot chi tiêu cần kho dữ liệu (Upstash Redis trên Vercel), xem README."


def token():
    return os.environ.get("CHITIEU_BOT_TOKEN", "").strip()


def owner_chats():
    """Chat được dùng bot: CHITIEU_CHAT_ID (nhiều người thì cách nhau dấu phẩy), mặc định TELEGRAM_CHAT_ID."""
    ids = os.environ.get("CHITIEU_CHAT_ID") or os.environ.get("TELEGRAM_CHAT_ID", "")
    return [x.strip() for x in ids.split(",") if x.strip()]


def today():
    return datetime.now(VN_TZ).date()


# ---- Đọc tin nhắn ----------------------------------------------------------------

# ---- Nhóm tự chỉnh: người dùng thêm nhóm, thêm từ khóa, đổi tên, ẩn nhóm ngay trong Telegram (/nhom) ----
# Lưu ở khóa chitieu:nhomrieng: {"moi": [mã nhóm tự tạo], "ten": {mã: tên}, "tu": {mã: [từ khóa]},
# "an": [mã nhóm đã ẩn], "dem": số nhóm đã tạo}. Nhóm ẩn vẫn giữ tên để khoản cũ hiện đúng.

config, reset, save_config = groups_repo.config, groups_repo.reset, groups_repo.save






# ---- Xếp nhóm bằng AI (tùy chọn) ------------------------------------------------------
# Chỉ hỏi AI những khoản từ khóa không nhận ra (rơi vào Khác); AI cũng hiểu câu hỏi, viết nhận xét.
# Hai nhà cung cấp, cùng kiểu API của OpenAI (chat/completions), có cái nào dùng cái đó:
# - Google Gemini (biến GEMINI_API_KEY), dùng trước: gói miễn phí không giới hạn chung 50 lượt/ngày.
#   Thử ngày 04/11/2026: Gemini 3.5 Flash-Lite xếp đúng 13/13 khoản lạ trong khoảng 1 giây, Flash cũng
#   13/13 (khoảng 8 giây, gói miễn phí 5 lượt/phút). Model trước lỗi, bận, hết lượt thì thử model sau.
# - OpenRouter (biến AI_API_KEY), dự phòng: model miễn phí, cả tài khoản 50 lượt/ngày; AI_MODEL nhiều
#   model cách nhau dấu phẩy thì OpenRouter tự chuyển. AI_API_URL đổi được sang nhà cung cấp khác.
# AI lỗi hết thì khoản vào Khác và bot hỏi người dùng.

from infrastructure import ai as ai_client  # noqa: E402

env_list, gemini_key, openrouter_key = ai_client.env_list, ai_client.gemini_key, ai_client.openrouter_key
ai_key, ai_models, ai_providers = ai_client.key, ai_client.openrouter_models, ai_client.providers
ai_post, ai_chat, first_json = ai_client.post, ai_client.chat, ai_client.first_json
from services.chitieu import ai_sort, ledger as ledger_service  # noqa: E402
from interface.chitieu import commands  # noqa: E402
from interface.chitieu.context import (BACK, CHI_BUTTONS, INCOME_KINDS, REPORT_BUTTONS, SORT_TITLE, bare, budget_label,  # noqa: E402,F401
                                       budget_lines, budget_status, button_ref, classify, entries_message, entry_text,
                                       find_group, full_month, groups, income_kind, income_kinds, name, parse_date,
                                       parse_line, period, pick, picker, read_tag, ref, report, rules, short, vnd,
                                       with_picker)

baocao, thang, lichsu, delete, xoa_cuoi, ngansach = (commands.baocao, commands.thang, commands.lichsu, commands.delete,
                                                     commands.xoa_cuoi, commands.ngansach)
nhom_cmd, chuaxep, xuat = commands.nhom_cmd, commands.chuaxep, commands.xuat
nhom_them, nhom_tukhoa, nhom_doiten, nhom_xoa = (commands.nhom_them, commands.nhom_tukhoa, commands.nhom_doiten,
                                                 commands.nhom_xoa)
add_words, after_change, NHOM_USAGE = commands.add_words, commands.after_change, commands.NHOM_USAGE
split_spec, make_label = labels.split_spec, labels.make_label


def find_category(text):
    """Tên nhóm người dùng gõ ('ăn uống', 'di lai', 'tổng') -> mã, None nếu không rõ."""
    return classify_rules.find_category(text, config())

add, recent, learn_all, learn, tidy = (ledger_service.add, ledger_service.recent, ledger_service.learn_all,
                                       ledger_service.learn, ledger_service.tidy)
ai_prompt, ai_request, ask_ai, ai_stats = ai_sort.ai_prompt, ai_sort.ai_request, ai_sort.ask_ai, ai_sort.ai_stats
quota_text, ai_status = ai_sort.quota_text, ai_sort.ai_status


def ai_quota():
    return ai_client.quota()
AI_URL, AI_TIMEOUT = ai_client.AI_URL, ai_client.AI_TIMEOUT  # noqa: F401


# ---- Lưu trữ: mỗi tháng một Redis hash, mỗi khoản một mục (id -> JSON) ---------------
# Ghi/sửa/xóa từng mục riêng nên hai tin nhắn tới cùng lúc không đè mất khoản của nhau.

def load(ym):
    return ledger_repo.load(ym)


def save(e):
    ledger_repo.save(e)


def find(reference):
    """'2026-11:12' -> khoản đó, None nếu đã xóa."""
    ym, _, rid = reference.partition(":")
    return ledger_repo.find(ym, rid)


def between(start, end):
    """Các khoản từ ngày start tới end (tính cả hai đầu)."""
    return ledger_repo.between(start, end)




# ---- Hiển thị ---------------------------------------------------------------------



# ---- Báo cáo ------------------------------------------------------------------------


def from_menu(message):
    """Tin này mở từ menu (có nút ⬅️ Menu): vẽ lại thì giữ nút menu."""
    return any(data.startswith("m:") for row in keyboard_rows(message) for _, data in row)




# ---- Lệnh ---------------------------------------------------------------------------

def taisan():
    from interface.taisan import assets as module  # tài sản, mua bán cổ phiếu, khám sức khỏe tài chính
    return module


def duphong():
    from interface.duphong import reserve as module  # quỹ dự phòng
    return module


def phantich():
    import phantich as module  # nạp khi cần: phantich.py cũng dùng các hàm trong file này
    return module


def sono():
    from interface.no import debt as module  # sổ nợ
    return module


def kehoach():
    from interface.kehoach import plan as module  # lộ trình tài chính, chia lương
    return module


def menu():
    import menu as module  # menu nút bấm, tổng quan, hướng dẫn
    return module


def dautu():
    from interface.dautu import fund as module  # đầu tư quỹ mở hằng tháng (Value Averaging)
    return module


def tietkiem():
    from interface.tietkiem import progress as module  # tiết kiệm từ khi dùng bot, chuỗi ngày ghi chép
    return module


def troly():
    import troly as module  # hiểu câu nói thường, hỏi lại khi thiếu, thẻ xác nhận
    return module


def period_kind(args):
    """Tham số kỳ của /bieudo, /nhanxet: trống là tháng này, '10' là tháng 10, 'thangtruoc'..."""
    word = plain("".join(args))
    if word.isdigit() and 1 <= int(word) <= 12:
        return str(int(word))
    return {"thangtruoc": "thangtruoc", "tuan": "tuan", "tuannay": "tuan", "homnay": "ngay"}.get(word, "thang")


COMMANDS = {
    "baocao": ("Báo cáo chi tiêu, có nút chọn kỳ", baocao),
    "homnay": ("Chi tiêu hôm nay", lambda args: (report("ngay", today())[0], REPORT_BUTTONS)),
    "tuan": ("Chi tiêu tuần này", lambda args: (report("tuan", today())[0], REPORT_BUTTONS)),
    "thang": ("Chi tiêu tháng này; /thang 10 cho tháng 10", thang),
    "lichsu": ("10 khoản gần nhất, bấm ❌ để xóa", lichsu),
    "xoa": ("Xóa khoản vừa ghi", xoa_cuoi),
    "ngansach": ("Ngân sách tháng: /ngansach ăn uống 3tr", ngansach),
    "nhom": ("Các nhóm chi tiêu; tự tạo nhóm, thêm từ khóa", nhom_cmd),
    "chuaxep": ("Xếp nhóm các khoản đang ở Khác", chuaxep),
    "dubao": ("Dự báo chi tiêu hằng ngày (ăn uống, sinh hoạt); /dubao tatca cho mọi khoản",
              lambda args: phantich().dubao(args)),
    "hoi": ("Hỏi bằng câu thường: /hoi tháng này cà phê hết bao nhiêu", lambda args: phantich().hoi(" ".join(args), today())),
    "bieudo": ("Biểu đồ chi tiêu tháng; /bieudo 10 cho tháng 10", lambda args: phantich().chart_reply(period_kind(args), today())),
    "taisan": ("Tài sản ròng: tiền, tiết kiệm, cổ phiếu, vàng, quỹ, nợ…; /taisan huongdan", lambda args: taisan().taisan(args)),
    "suckhoe": ("Khám sức khỏe tài chính cá nhân", lambda args: taisan().health(today())),
    "luong": ("Nhắc ngày nhận lương: /luong 10 25tr", lambda args: taisan().luong(args)),
    "duphong": ("Quỹ dự phòng: mục tiêu, tiến độ, mỗi tháng cần để bao nhiêu", lambda args: duphong().duphong(args)),
    "nhanxet": ("Nhận xét chi tiêu tháng (AI); /nhanxet 10 cho tháng 10", lambda args: phantich().commentary(period_kind(args), today())),
    "xuat": ("Xuất file CSV mở bằng Excel: /xuat 10", xuat),
    "menu": ("🏠 Hôm nay: đã chi, còn được tiêu, việc cần làm", lambda args: menu().menu_cmd(args)),
    "start": ("Bắt đầu", lambda args: menu().start(args)),
    "huongdan": ("Cách dùng và mọi lệnh", lambda args: menu().guide(args)),
    "no": ("Sổ nợ: còn bao nhiêu, mỗi tháng trả, nhắc trả", lambda args: sono().no_cmd(args)),
    "kehoach": ("Lộ trình xây tài sản, chia lương mỗi tháng", lambda args: kehoach().kehoach(args)),
    "dautu": ("Đầu tư quỹ mở hằng tháng: tháng này nên mua bao nhiêu", lambda args: dautu().dautu(args)),
    "tietkiem": ("Tiết kiệm từ khi dùng bot, chuỗi ngày ghi chép", lambda args: tietkiem().tietkiem(args)),
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
    if isinstance(reply, (str, tuple)) and kho.ready():
        reply = menu().with_keyboard(reply)
    return reply


def respond(text, now, chat=None):
    """Trả lời một tin nhắn: lệnh, khoản chi/thu cần ghi, hoặc câu nói thường về việc khác (troly.py hiểu, hỏi lại
    khi thiếu, xin xác nhận trước khi ghi). chat: mã chat, để nhớ bot đang hỏi dở việc gì."""
    if not kho.ready():
        return NEED_STORE
    reset()
    helper = troly()
    screen = menu().from_keyboard(text)  # nút cố định dưới ô chat
    if screen:
        helper.forget(chat)
        return screen
    many = menu().run_lines(text, now)  # nhiều lệnh, mỗi lệnh một dòng
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
    traded = taisan().trade(text, now)  # "mua 1000 FPT giá 95", "bán 500 FPT giá 120"
    if traded:
        return traded
    fund_order = dautu().from_text(text, now)  # "mua VMEEF 3tr": ghi lệnh mua quỹ đang đầu tư
    if fund_order:
        return fund_order
    known = helper.quick(text, now)  # "hôm nay không tiêu gì": hiểu bằng luật, không cần AI
    if known is not None:
        return known
    question = phantich().is_question(text)
    if question and not (ai_key() and helper.beyond_spending(text)):
        return phantich().hoi(text, now.date())  # câu hỏi về chi tiêu đã ghi
    if question or helper.wants(text):  # không phải khoản chi thường: nhờ AI hiểu câu
        reply = helper.understand(text, now, chat, question)
        if reply is not None:
            return reply
    return record_text(text, now)


def record_text(text, now):
    """Ghi các khoản chi/thu trong tin nhắn (mỗi dòng một khoản) và trả câu báo kèm nút."""
    entries = add(text, now)
    if not entries:
        return "Không thấy số tiền. Nhắn kiểu: <b>cà phê 35k</b> hoặc bấm /menu"
    debt_lines, debt_rows = debt_after(entries, now.date())
    try:
        extra = phantich().after_record(entries, now.date())
    except Exception as e:  # phần phân tích lỗi thì vẫn báo đã ghi
        print(f"[lỗi] phân tích sau khi ghi: {e!r}", file=sys.stderr)
        extra = []
    try:
        extra += tietkiem().after_record(entries, now.date())  # 🔥 chuỗi ngày ghi · hôm nay so với mốc · đã bớt
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
        return kehoach().salary_hint(entries, day)
    except Exception as e:
        print(f"[lỗi] gợi ý chia lương: {e!r}", file=sys.stderr)
        return None


def debt_after(entries, day):
    """Khoản vừa ghi là trả nợ thì trừ dư nợ: (dòng thêm, hàng nút); lỗi thì bỏ qua, khoản vẫn được ghi."""
    try:
        return sono().after_record(entries, day)
    except Exception as e:
        print(f"[lỗi] trừ dư nợ: {e!r}", file=sys.stderr)
        return [], []


def keyboard_rows(message):
    return [[(b["text"], b.get("callback_data", "")) for b in row]
            for row in (message.get("reply_markup") or {}).get("inline_keyboard", [])]


def refs_in(message):
    """Các khoản có nút dưới tin, theo thứ tự xuất hiện."""
    refs = [button_ref(data) for row in keyboard_rows(message) for _, data in row]
    return list(dict.fromkeys(r for r in refs if r))


def render(refs, day, message=None, focus=None):
    sorting = ((message or {}).get("text") or "").startswith(SORT_TITLE)
    return entries_message([e for e in map(find, refs) if e], day, sorting, focus)


def on_button(data, message, now):
    """Bấm nút: trả (thông báo nhỏ, việc tiếp theo) như lenh.on_button."""
    if not kho.ready():
        return "Chưa có kho dữ liệu", None
    reset()
    kind, _, arg = data.partition(":")
    day = now.date()
    if kind == "bc":
        rows = CHI_BUTTONS if from_menu(message) else REPORT_BUTTONS
        return None, ("edit", lambda: (report(arg, day)[0], rows))
    if kind == "m":
        return menu().on_button(arg, message, now)
    if kind == "no":
        return sono().on_button(arg, message, now)
    if kind == "kh":
        return kehoach().on_button(arg, message, now)
    if kind == "ts":
        return taisan().on_button(arg, message, now)
    if kind == "anh":
        import docanh
        return docanh.on_button(arg, message, now)
    if kind == "dp":
        return duphong().on_button(arg, message, now)
    if kind == "dc":
        from interface.doichieu import reconcile as doichieu
        return doichieu.on_button(arg, message, now)
    if kind == "dt":
        return dautu().on_button(arg, message, now)
    if kind == "tk":
        return tietkiem().on_button(arg, message, now)
    if kind == "y":
        return troly().on_button(arg, message, now)
    if kind == "bd":
        return "Đang vẽ biểu đồ…", ("send", lambda: phantich().chart_reply(arg, day))
    if kind == "db":
        return None, ("send", lambda: phantich().daily_text(day))
    if kind == "nx":
        return "AI đang viết nhận xét, chờ chút…", ("send", lambda: phantich().commentary(arg, day))
    if kind == "xls":
        gone = delete(arg)
        return ("Đã xóa" if gone else "Khoản này đã xóa rồi"), ("edit", lambda: lichsu([]))
    refs = refs_in(message)
    if kind == "doi":
        return "Chọn nhóm đúng cho khoản này", ("edit", lambda: render(refs, day, message, focus=arg))
    if kind == "nhom":
        reference, _, code = arg.rpartition(":")
        e = find(reference)
        if e is None:
            return "Khoản này đã xóa rồi", ("edit", lambda: render(refs, day, message))
        if code not in groups():
            return "Nhóm này không còn, chọn nhóm khác", ("edit", lambda: render(refs, day, message))
        if e.get("ai") and code != e["nhom"]:
            kho.command("HINCRBY", keys.AI_STATS, "sua", 1)  # AI đoán sai
        e["nhom"] = code
        e.pop("ai", None)  # người dùng đã chọn, không còn là AI đoán
        e.pop("dekhac", None)
        if code == OTHER:
            e["dekhac"] = True  # tự chọn Khác: không hỏi lại
        save(e)
        moved = 0
        if code not in (INCOME, OTHER):
            learn(e["ghichu"], code)
            moved = tidy(day)  # khoản khác cùng nội dung đang ở Khác cũng xếp luôn
        toast = f"Đã chuyển sang {name(code)}, lần sau bot tự nhớ" + (
            f" (xếp luôn {moved} khoản giống vậy)" if moved else "")
        return toast, ("edit", lambda: render(refs, day, message))
    if kind == "giu":
        e = find(arg)
        if e and pending(e):  # "📦 Để ở Khác": không hỏi lại khoản này
            e["dekhac"] = True
            save(e)
            return "Để ở Khác", ("edit", lambda: render(refs, day, message))
        return None, ("edit", lambda: render(refs, day, message))
    if kind == "xoa":
        gone = delete(arg)
        return ("Đã xóa" if gone else "Khoản này đã xóa rồi"), ("edit", lambda: render(refs, day, message))
    return None, None


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    for line in " ".join(sys.argv[1:]).split("\\n"):
        e = parse_line(line, today())
        print(f"{line!r} -> " + (f"{vnd(e['tien'])} · {name(e['nhom'])} · {e['ghichu']!r} · {e['ngay']}"
                                 if e else "không thấy số tiền"))


if __name__ == "__main__":
    main()
