"""Menu nút bấm cho bot chi tiêu: 4 mục chính, cũng là 4 nút cố định dưới ô chat.

- 🏠 Hôm nay (/menu, /start): hôm nay chi gì, còn được tiêu bao nhiêu, tài khoản chính, chuỗi ngày ghi, việc cần làm
  hôm nay (mỗi việc kèm nút làm luôn).
- 💰 Tiền của tôi: mọi ngăn tiền một màn hình (tài khoản, quỹ dự phòng, đầu tư, tiết kiệm, vàng, cổ phiếu, nợ).
- 🎯 Kế hoạch: chia lương tháng này, đang ở bước nào của lộ trình, nút làm hết theo kế hoạch.
- 💬 Hỏi: câu hỏi hay gặp bấm là có, câu khác cứ nhắn câu thường.
Bấm nút thì mở ngay trong tin đó, có nút ⬅️ Hôm nay. /huongdan: mọi lệnh, theo nhóm việc.
"""
import html
import sys

from infrastructure import kho
from repositories import keys
import sochitieu as ct
from domain.common.dates import WEEKDAYS
from presentation.menu.view import (BOTTOM, GREETING, GUIDE, HOW_TO, MAIN, MONEY_ROWS, NAV, OLD_BOTTOM, QUESTIONS,  # noqa: F401
                                    SETTINGS, bottom_keyboard, gain)


def short(x):
    return ct.taisan().short(x) if abs(x) >= 1000 else "0đ"


def part(name, make):
    """Một dòng của màn hình; lỗi thì bỏ dòng đó, không hỏng cả màn hình."""
    try:
        return make()
    except Exception as e:
        print(f"[lỗi] màn hình, phần {name}: {e!r}", file=sys.stderr)
        return None


def note(e):
    return html.escape((e.get("ghichu") or ct.bare(ct.name(e["nhom"])))[:20])


# ---- 🏠 Hôm nay ----------------------------------------------------------------------------

def fund_deadline(now):
    """Hôm nay là hạn đặt lệnh quỹ mà chưa đặt: (việc, nút); None nếu không."""
    from interface.dautu import fund as dautu
    cfg = dautu.config()
    if not dautu.active(cfg):
        return None
    deadline, sess = dautu.is_deadline(cfg, now)
    if not deadline:
        return None
    st = dautu.status(cfg, now)
    if st["ordered"] or st["skip"] or not (st["buy"] or st["side_buy"]):
        return None
    return (f"📈 Hôm nay là hạn đặt lệnh {cfg['ma']}, trước 14:40", ("📈 Xem lệnh cần đặt", "dt:xem"))


def todo(day, n, now):
    """Việc cần làm hôm nay: [(chữ, nút hoặc None)], quan trọng trước."""
    from interface.kehoach import plan as kehoach
    from interface.no import debt as sono
    out = []
    deadline = part("hạn đặt lệnh quỹ", lambda: fund_deadline(now))
    if deadline:
        out.append(deadline)
    salary = part("nhắc lương", lambda: ct.taisan().salary_due(day))
    if salary:
        out.append((salary[0], salary[1][0][0]))
    if n:
        steps = kehoach.steps(n)
        paid = any(e["nhom"] == ct.INCOME for e in ct.load(n["ym"]))
        if paid and len(steps) > 1:
            out.append(("📋 Lương đã về: " + " · ".join(f"{html.escape(label[0].lower() + label[1:])} {short(amount)}"
                                                        for _, label, amount, _ in steps),
                        ("✅ Làm hết theo kế hoạch", "kh:het")))
        else:
            for kind, label, amount, ref in steps:
                if kind == "no":
                    d = sono.by_id(n["data"], ref)
                    due = f" (hạn ngày {d['ngay_tra']})" if d and d.get("ngay_tra") else ""
                    out.append((f"💳 {html.escape(label)} {short(amount)}{due}",
                                (f"✅ Đã trả {sono.short_name(d)}", f"no:tra:{ref}:{int(amount)}") if d else None))
                elif paid:
                    out.append((f"{'🛟' if kind == 'dp' else '📈'} {html.escape(label)} {short(amount)}",
                                (f"✅ {label[:18]}", f"dp:nap:{int(amount)}" if kind == "dp" else f"dt:nap:{int(amount)}")))
        if not n["fund"].monthly:
            out.append((f"📒 Ghi chép đủ 14 ngày để bot tính quỹ dự phòng (đang có {n['fund'].days} ngày)", None))
    for text, rows in part("hoán đổi quỹ", lambda: ct.dautu().switch_prompts(day)) or []:
        out.append((text, rows[0][0]))
    check = part("đối chiếu", lambda: __import__("interface.doichieu.reconcile", fromlist=["todo"]).todo(day))
    if check:
        out.append(check)
    unsorted = sum(ct.pending(e) for e in ct.load(day.strftime("%Y-%m")))
    if unsorted:
        out.append((f"🗂 {unsorted} khoản chưa rõ nhóm", ("🗂 Xếp nhóm", "m:cx")))
    return out


def home(day, now=None):
    """🏠 Hôm nay."""
    if not kho.ready():
        return ct.NEED_STORE
    from interface.kehoach import plan as kehoach
    from interface.no import debt as sono
    ts = ct.taisan()
    now = now or ts.now_vn()
    month = ct.load(day.strftime("%Y-%m"))
    group = part("nhóm trả nợ", lambda: sono.debt_group()[0])
    spend = [e for e in month if e["nhom"] not in (ct.INCOME, group) and not e.get("no")]
    today = [e for e in spend if e["ngay"] == day.isoformat()]
    lines = [f"🏠 <b>Hôm nay, {WEEKDAYS[day.weekday()].lower()} {day:%d/%m}</b>"]
    if today:
        shown = " · ".join(f"{note(e)} {short(e['tien'])}" for e in today[-4:])
        lines.append(f"💸 Đã chi <b>{short(sum(e['tien'] for e in today))}</b>: {shown}"
                     + (f" (+{len(today) - 4} khoản)" if len(today) > 4 else ""))
    else:
        lines.append("💸 Chưa ghi khoản chi nào. Nhắn kiểu: <b>cà phê 35k</b>")
    n = part("chia lương", lambda: kehoach.numbers(day))
    s = part("mỗi ngày được tiêu", lambda: kehoach.spendable(day, n)) if n else None
    if s:
        lines.append(kehoach.spend_text(s, bold=True))
    income = sum(e["tien"] for e in month if e["nhom"] == ct.INCOME)
    lines.append(f"📅 Tháng {day.month}: đã chi {short(sum(e['tien'] for e in spend))}"
                 + (f" · đã thu {short(income)}" if income else ""))
    main = part("tài khoản chính", lambda: ts.main_line(day))
    if main:
        lines.append(main)
    saved = part("tiết kiệm", lambda: __import__("interface.tietkiem.progress", fromlist=["home_line"]).home_line(day))
    if saved:
        lines.append(saved)
    tasks = part("việc cần làm", lambda: todo(day, n, now)) or []
    rows = []
    if tasks:
        lines += ["", "👉 <b>Việc cần làm</b>"] + [f"• {t}" for t, _ in tasks]
        rows = [[b] for _, b in tasks if b][:4]
    elif month:
        lines += ["", "👉 Không có việc gấp 👌"]
    if not today and now.hour >= 18:
        rows.append([("🙅 Hôm nay không tiêu", f"tk:khong:{day.isoformat()}")])
    rows += [[("📊 Chi tiêu tháng", "m:chi"), ("🔮 Dự báo", "db"), ("🧾 Vừa ghi", "m:ls")],
             [("➕ Thêm", "y:them"), ("⚙️ Cài đặt", "m:cd")]]
    return "\n".join(lines), rows


# ---- 💰 Tiền của tôi -----------------------------------------------------------------------
def money(day):
    """💰 Tiền của tôi: mọi ngăn tiền, mỗi ngăn một dòng."""
    if not kho.ready():
        return ct.NEED_STORE
    ts = ct.taisan()
    v = ts.valuation(day)
    if not v["rows"]:
        return ("💰 <b>Tiền của tôi</b>\nChưa khai báo gì. Nhắn câu thường, ví dụ «tài khoản VCB còn 30tr», «gửi tiết "
                "kiệm TCB 50tr lãi 5% 6 tháng», «vay anh Nam 10tr», hoặc bấm ➕ Thêm.", [[("➕ Thêm", "y:them"), ct.BACK]])
    items = {str(it["id"]): it for it in ts.load()["items"]}
    rows = v["rows"]

    def of(r):
        return items.get(r[1], {})
    fund = [r for r in rows if of(r).get("duphong")]
    wait = [r for r in rows if of(r).get("dautu")]
    main = [r for r in rows if of(r).get("chinh")]
    used = {r[1] for r in fund + wait + main}
    lines = [f"💰 <b>Tiền của tôi</b> · tài sản ròng <b>{short(v['net'])}</b>{ts.compare_line(day, v['net'])}"]
    for r in main:
        lines.append(f"🏦 {html.escape(r[2])} (chính) ~<b>{short(r[3])}</b>")
    other = [r for r in rows if r[0] == "tien" and r[1] not in used]
    if other:
        lines.append(("👛 " if main else "🏦 ") + " · ".join(f"{html.escape(r[2])} {short(r[3])}" for r in other))
    if fund:
        f = part("quỹ dự phòng", lambda: __import__("services.duphong.reserve", fromlist=["status"]).status(day))
        total = sum(r[3] for r in fund)
        lines.append(f"🛟 Quỹ dự phòng <b>{short(total)}</b>" + (
            f" / {short(f.target)} ({total / f.target * 100:.0f}%)" if f and f.target else ""))
    funds = [r for r in rows if r[0] == "quy"]
    shown = ([f"<b>{short(sum(r[3] for r in funds))}</b>{gain(funds)}"] if funds else []) + [
        f"quỹ chờ {short(r[3])}" for r in wait if r[3]]
    if shown:
        lines.append("📈 Quỹ mở " + " · ".join(shown))
    for kinds, label in ((("tietkiem",), "🐷 Tiết kiệm"), (("vang",), "🥇 Vàng"), (("cp", "etf"), "📊 Cổ phiếu, ETF"),
                         (("coin",), "🪙 Tiền số"), (("ngoaite",), "💵 Ngoại tệ"), (("khac",), "🏠 Khác")):
        group = [r for r in rows if r[0] in kinds and r[1] not in used]
        if group:
            lines.append(f"{label} <b>{short(sum(r[3] for r in group))}</b>"
                         + ("" if kinds == ("tietkiem",) else gain(group)))
    debt = part("nợ", lambda: __import__("interface.no.debt", fromlist=["home_line"]).home_line(day))
    if debt:
        lines.append(debt)
    elif v["debts"]:
        lines.append(f"💳 Nợ <b>{short(v['debts'])}</b>")
    if not main:
        lines.append("<i>💡 Chưa chọn tài khoản chính: bấm 🏦</i>")
    return "\n".join(lines), MONEY_ROWS


# ---- 🎯 Kế hoạch, 💬 Hỏi, ⚙️ Cài đặt ---------------------------------------------------------


def ask_screen():
    lines = ["💬 <b>Hỏi</b>",
             "Cứ nhắn câu hỏi bằng lời thường, ví dụ:",
             "• tháng này cà phê hết bao nhiêu?",
             "• tuần này tiêu nhiều nhất vào gì?",
             "• tháng 10 đi lại hết bao nhiêu, so với tháng 9?",
             "• bao giờ trả xong nợ? · quỹ dự phòng đủ chưa?",
             "Hoặc bấm câu hay hỏi:"]
    return "\n".join(lines), [[(q, f"m:q:{k}")] for q, k in QUESTIONS] + [[ct.BACK]]


def answer_question(key, day):
    """Câu hỏi có sẵn: trả lời bằng màn hình có sẵn (không cần AI, trừ nhận xét)."""
    pt = ct.phantich()
    makers = {"tieu": lambda: pt.dubao([]), "thang": lambda: (ct.report("thang", day)[0], ct.REPORT_BUTTONS),
              "so": lambda: pt.hoi("tháng này so với tháng trước", day), "no": lambda: ct.sono().view(day),
              "quy": lambda: ct.dautu().view(), "sk": lambda: ct.taisan().health(day),
              "nx": lambda: pt.commentary("thang", day)}
    return makers[key]()


def notify_rows():
    """Nút bật/tắt thông báo, ghi trạng thái hiện tại."""
    from services.tietkiem import progress as tietkiem_service
    remind = tietkiem_service.reminder_on()
    rows = [[(f"🔔 Nhắc ghi chép 21h: {'bật' if remind else 'tắt'}", "m:tb:nhac")]]
    try:
        cfg = ct.dautu().config()
        if ct.dautu().active(cfg):
            rows.append([(f"📊 Báo lãi/lỗ quỹ tối: {'tắt' if cfg.get('baocao_toi') is False else 'bật'}", "m:tb:quy")])
    except Exception as e:
        print(f"[lỗi] cài đặt báo quỹ: {e!r}", file=sys.stderr)
    return rows


def settings():
    rows = [[("🏷 Các nhóm", "m:nhom"), ("🎯 Ngân sách", "m:ns")],
            [("💼 Ngày lương", "y:them:ngay_luong"), ("🎯 Đặt ngân sách", "y:them:ngan_sach")]]
    rows += notify_rows()
    rows += [[("📤 Xuất Excel tháng này", "m:xuat"), ("📖 Mọi lệnh", "m:hd")], [("📝 Cách ghi", "m:ghi"), ct.BACK]]
    return SETTINGS, rows


def toggle(which):
    if which == "nhac":
        from services.tietkiem import progress as tietkiem_service
        on = tietkiem_service.toggle_reminder()
        return "Đã " + ("bật" if on else "tắt") + " nhắc ghi chép 21h"
    dt = ct.dautu()
    cfg = dt.config()
    cfg["baocao_toi"] = cfg.get("baocao_toi") is False
    dt.save(cfg)
    return "Đã " + ("bật" if cfg["baocao_toi"] else "tắt") + " báo lãi/lỗ quỹ buổi tối"


def chi_screen(day):
    return ct.report("thang", day)[0], ct.CHI_BUTTONS


def screen(name, day):
    from interface.kehoach import plan as kehoach
    return {"home": lambda: home(day), "tien": lambda: money(day), "kh": lambda: kehoach.plan(day),
            "hoi": ask_screen, "chi": lambda: chi_screen(day), "ts": lambda: money(day),
            "no": lambda: ct.sono().view(day), "lt": lambda: kehoach.roadmap(day),
            "ghi": lambda: (HOW_TO, [[ct.BACK]]), "cd": settings}[name]()


def with_keyboard(reply):
    """Lần đầu (hoặc khi còn hàng nút cũ): gửi thêm lời chào kèm hàng nút cố định dưới ô chat, rồi mới tới màn hình."""
    if not kho.put_new(keys.KEYBOARD_FLAG, True, 3 * 365 * 86400):
        return reply
    return {"messages": [(GREETING, bottom_keyboard()), reply]}


def push_keyboard(send):
    """Hàng nút dưới ô chat vừa đổi mà chưa gửi: gửi lời chào kèm hàng nút mới (việc theo giờ gọi). True nếu đã gửi."""
    if not kho.put_new(keys.KEYBOARD_FLAG, True, 3 * 365 * 86400):
        return False
    send(GREETING, bottom_keyboard())
    return True


def start(args):
    if not kho.ready():
        return ct.NEED_STORE
    kho.delete(keys.KEYBOARD_FLAG)  # /start luôn gửi lại hàng nút (lỡ người dùng tắt)
    return with_keyboard(home(ct.today()))


def menu_cmd(args):
    if not kho.ready():
        return ct.NEED_STORE
    return with_keyboard(home(ct.today()))


def guide(args=None):
    return GUIDE


def from_keyboard(text):
    """Chữ của nút cố định dưới ô chat -> màn hình tương ứng; None nếu không phải nút. Nút của hàng cũ vẫn chạy và
    kèm hàng nút mới."""
    label = text.strip()
    name = BOTTOM.get(label) or OLD_BOTTOM.get(label)
    return with_keyboard(screen(name, ct.today())) if name else None


def on_button(arg, message, now):
    """Nút "m:...": mở một mục (sửa ngay tin đó), gửi danh sách, file, câu trả lời, bật/tắt thông báo."""
    day = now.date()
    if arg in ("home", "tien", "kh", "hoi", "chi", "ts", "no", "lt", "ghi", "cd"):
        return ("Đang lấy giá…" if arg in ("tien", "ts") else None), ("edit", lambda: screen(arg, day))
    if arg.startswith("q:") and arg[2:] in dict((k, q) for q, k in QUESTIONS):
        return None, ("send", lambda: answer_question(arg[2:], day))
    if arg.startswith("tb:"):
        toast = toggle(arg[3:])
        return toast, ("edit", settings)
    sends = {"ls": lambda: ct.lichsu([]), "cx": lambda: ct.chuaxep([]), "ns": lambda: ct.ngansach([]),
             "nhom": lambda: ct.nhom_cmd([]), "xuat": lambda: ct.xuat([]), "hd": lambda: GUIDE}
    if arg in sends:
        return None, ("send", sends[arg])
    return None, None



def run_lines(text, now):
    """Tin nhiều dòng, dòng nào cũng là lệnh: chạy lần lượt (khai báo nhiều thứ một lần); trả các câu trả lời
    gộp lại. None nếu không phải kiểu tin đó."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 2 or not all(line.startswith("/") for line in lines):
        return None
    out = []
    for line in lines[:20]:
        try:
            reply = ct.respond(line, now)
        except Exception as e:
            print(f"[lỗi] lệnh {line!r}: {e!r}", file=sys.stderr)
            reply = "⚠️ Lỗi, thử lại riêng lệnh này"
        if isinstance(reply, tuple):
            reply = reply[0]
        if isinstance(reply, dict):
            reply = "↪️ Lệnh này gửi file hoặc ảnh, gõ riêng nhé"
        out.append(f"▶️ <code>{html.escape(line[:60])}</code>\n{reply}")
    text = "\n\n".join(out)
    while len(text) > 4000 and len(out) > 1:  # tin Telegram tối đa 4096 ký tự: bớt chi tiết, giữ dòng đầu mỗi lệnh
        out = [o.split("\n")[0] + "\n" + o.split("\n")[1] if o.count("\n") > 1 else o for o in out]
        text = "\n\n".join(out)
        if len(text) > 4000:
            text = text[:3990].rsplit("\n", 1)[0]
            break
    return text
