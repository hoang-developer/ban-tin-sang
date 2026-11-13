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

import kho
import sochitieu as ct
from bantin import WEEKDAYS

KEYBOARD_FLAG = "chitieu:banphim:2"  # đã gửi hàng nút cố định bản 4 mục chưa
BOTTOM = {"🏠 Hôm nay": "home", "💰 Tiền của tôi": "tien", "🎯 Kế hoạch": "kh", "💬 Hỏi": "hoi"}
OLD_BOTTOM = {"🏠 Menu": "home", "📊 Chi tiêu": "chi", "💼 Tài sản": "tien"}  # hàng nút cũ: vẫn chạy, gửi hàng mới
NAV = [("🏠 Hôm nay", "m:home"), ("💰 Tiền của tôi", "m:tien"), ("🎯 Kế hoạch", "m:kh"), ("💬 Hỏi", "m:hoi")]
MAIN = [NAV[:2], NAV[2:], [("➕ Thêm", "y:them"), ("📝 Cách ghi", "m:ghi"), ("⚙️ Cài đặt", "m:cd")]]
GREETING = ("👋 <b>Bot ghi chi tiêu và xây tài sản</b>\n"
            "Nhắn số tiền kèm nội dung để ghi, ví dụ: <b>cà phê 35k</b>. Việc khác cứ nhắn câu thường (mua vàng, gửi tiết "
            "kiệm, vay, trả nợ, hỏi còn nợ bao nhiêu…), bot hỏi lại nếu thiếu và xin xác nhận trước khi ghi. Gửi ảnh hóa "
            "đơn, chuyển khoản, lệnh quỹ, đơn mua vàng cũng được.\nBốn nút dưới ô chat: 🏠 Hôm nay · 💰 Tiền của tôi · "
            "🎯 Kế hoạch · 💬 Hỏi.")
HOW_TO = ("📝 <b>Cách ghi</b>\n"
          "• Nhắn số tiền kèm nội dung: cà phê 35k · đổ xăng 80000 · tiền nhà 5tr (1tr2 là 1.200.000đ)\n"
          "• Khoản thu: + lương 19tr\n"
          "• Ngày khác: hôm qua ăn tối 250k · 02/11 cắt tóc 100k\n"
          "• Tự chọn nhóm: đóng họ 1tr #trả nợ\n"
          "• Nhiều khoản: mỗi khoản một dòng; gõ không dấu cũng được\n"
          "• 📷 Gửi ảnh hóa đơn, màn hình chuyển khoản, lịch sử giao dịch ngân hàng\n"
          "• Trả nợ: trả nợ chú Tư 5tr (tự trừ vào sổ nợ /no)\n"
          "• Mua bán cổ phiếu, ETF: mua 500 E1VFVN30 giá 33,6 · bán 100 FPT giá 120\n"
          "• Hỏi: tháng này ăn uống hết bao nhiêu? · tôi còn nợ bao nhiêu? · quỹ lãi lỗ thế nào?\n"
          "• Việc khác nhắn câu thường, bot hỏi lại nếu thiếu và xin xác nhận trước khi ghi: mua 2 chỉ vàng nhẫn hết 27tr · "
          "gửi tiết kiệm VCB 50tr lãi 4,7% 6 tháng · vay anh Nam 10tr · nạp 2tr vào quỹ dự phòng · tài khoản Techcombank "
          "còn 14tr · chuyển 5tr từ VCB sang MoMo · hôm nay không tiêu gì\n"
          "• 🏦 Chọn tài khoản chính (💼 Tài sản → 🏦): bot tự cộng thu, trừ chi, trừ tiền nạp quỹ, góp đầu tư, trả nợ, "
          "nên luôn biết còn bao nhiêu. Lương về thì bấm ✅ Làm hết theo kế hoạch\n"
          "• 📷 Ảnh lệnh mua quỹ, đơn mua vàng, kết quả bán cổ phiếu: bot đọc rồi hỏi lại trước khi ghi\n"
          "Xếp sai nhóm thì bấm ✏️ Đổi nhóm, lần sau bot tự nhớ. Khoản chưa rõ nhóm thì bot hỏi luôn.\n"
          "Khai báo nhiều thứ một lần: dán nhiều lệnh, mỗi lệnh một dòng.")
GUIDE = ("📖 <b>Mọi lệnh</b> (dễ nhất là bấm /menu)\n"
         "\n📊 <b>Chi tiêu</b>\n"
         "/baocao báo cáo, có nút chọn kỳ · /homnay · /tuan · /thang (/thang 10)\n"
         "/bieudo biểu đồ · /dubao chi hằng ngày còn được tiêu bao nhiêu · /nhanxet nhận xét của AI\n"
         "/tietkiem chi lặt vặt so với trước khi dùng bot, chuỗi ngày ghi chép (/tietkiem khongtieu: hôm nay không "
         "tiêu gì)\n"
         "/hoi hỏi bằng câu thường · /lichsu 10 khoản gần nhất · /xoa xóa khoản vừa ghi\n"
         "/chuaxep xếp nhóm khoản chưa rõ · /xuat file Excel (/xuat 10)\n"
         "\n💼 <b>Tài sản</b>\n"
         "/taisan tài sản ròng, khai báo (/taisan huongdan) · /suckhoe khám sức khỏe tài chính\n"
         "\n💳 <b>Nợ</b>\n"
         "/no sổ nợ: còn bao nhiêu, mỗi tháng trả, bao giờ xong (/no huongdan)\n"
         "\n🎯 <b>Kế hoạch</b>\n"
         "/kehoach lộ trình xây tài sản · /kehoach chia: chia lương tháng này\n"
         "/duphong quỹ dự phòng · /luong ngày nhận lương (/luong 5 19tr)\n"
         "/dautu đầu tư quỹ mở hằng tháng: tháng này nên mua bao nhiêu, nhắc hạn đặt lệnh (/dautu huongdan)\n"
         "\n⚙️ <b>Cài đặt</b>\n"
         "/nhom tự tạo nhóm, thêm từ khóa · /ngansach ngân sách tháng\n"
         "\n" + HOW_TO)
SETTINGS = ("⚙️ <b>Cài đặt</b>\n"
            "Bấm nút để đổi. Gõ lệnh cũng được: /nhom, /ngansach, /luong 5 19tr, /duphong muctieu 6, /dautu gop 4tr, "
            "/dubao nhom ăn uống, đi chợ")


def bottom_keyboard():
    """Hàng nút cố định dưới ô chat (bấm là gửi chữ trên nút)."""
    labels = list(BOTTOM)
    return {"keyboard": [[{"text": x} for x in labels[:2]], [{"text": x} for x in labels[2:]]],
            "resize_keyboard": True, "is_persistent": True,
            "input_field_placeholder": "Nhắn khoản chi, ví dụ: cà phê 35k"}


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
    import dautu
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
    import kehoach
    import sono
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
        if not n["fund"]["monthly"]:
            out.append((f"📒 Ghi chép đủ 14 ngày để bot tính quỹ dự phòng (đang có {n['fund']['days']} ngày)", None))
    unsorted = sum(ct.pending(e) for e in ct.load(day.strftime("%Y-%m")))
    if unsorted:
        out.append((f"🗂 {unsorted} khoản chưa rõ nhóm", ("🗂 Xếp nhóm", "m:cx")))
    return out


def home(day, now=None):
    """🏠 Hôm nay."""
    if not kho.ready():
        return ct.NEED_STORE
    import kehoach
    import sono
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
        lines.append(f"🧾 {kehoach.spend_text(s, bold=True)}")
    income = sum(e["tien"] for e in month if e["nhom"] == ct.INCOME)
    lines.append(f"📅 Tháng {day.month}: đã chi {short(sum(e['tien'] for e in spend))}"
                 + (f" · đã thu {short(income)}" if income else ""))
    main = part("tài khoản chính", lambda: ts.main_line(day))
    if main:
        lines.append(main)
    saved = part("tiết kiệm", lambda: __import__("tietkiem").home_line(day))
    if saved:
        lines.append(saved)
    tasks = part("việc cần làm", lambda: todo(day, n, now)) or []
    rows = []
    if tasks:
        lines += ["", "👉 <b>Việc cần làm</b>"] + [f"• {t}" for t, _ in tasks]
        rows = [[b] for _, b in tasks if b][:4]
    elif month:
        lines += ["", "👉 Không có việc gấp, cứ ghi chép đều nhé ✨"]
    if not today and now.hour >= 18:
        rows.append([("🙅 Hôm nay không tiêu", f"tk:khong:{day.isoformat()}")])
    rows += [[("📊 Chi tiêu tháng", "m:chi"), ("🔮 Dự báo", "db"), ("🧾 Vừa ghi", "m:ls")],
             [("➕ Thêm", "y:them"), ("⚙️ Cài đặt", "m:cd")]]
    return "\n".join(lines), rows


# ---- 💰 Tiền của tôi -----------------------------------------------------------------------

MONEY_ROWS = [[("🏦 Tài khoản chính", "ts:chinh"), ("🔁 Chuyển tiền", "y:them:chuyen_tk")],
              [("💼 Chi tiết, giá mới", "ts:xem"), ("📊 Biểu đồ", "ts:bd")],
              [("🛟 Quỹ dự phòng", "dp:xem"), ("💳 Sổ nợ", "no:xem")],
              [("📈 Đầu tư quỹ", "dt:xem"), ("🩺 Sức khỏe", "ts:sk")],
              [("➕ Thêm", "y:them"), ct.BACK]]


def gain(rows):
    priced = [r for r in rows if r[4]]
    cost = sum(r[4] for r in priced)
    if not cost:
        return ""
    change = sum(r[3] for r in priced) - cost
    return f" ({change / cost * 100:+.1f}%)".replace(".", ",")


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
        f = part("quỹ dự phòng", lambda: __import__("duphong").status(day))
        total = sum(r[3] for r in fund)
        lines.append(f"🛟 Quỹ dự phòng <b>{short(total)}</b>" + (
            f" / {short(f['target'])} ({total / f['target'] * 100:.0f}%)" if f and f["target"] else ""))
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
    debt = part("nợ", lambda: __import__("sono").home_line(day))
    if debt:
        lines.append(debt)
    elif v["debts"]:
        lines.append(f"💳 Nợ <b>{short(v['debts'])}</b>")
    if not main:
        lines.append("<i>💡 Chọn tài khoản chính (nơi lương về) để bot tự cộng thu, trừ chi và tiền chuyển đi</i>")
    return "\n".join(lines), MONEY_ROWS


# ---- 🎯 Kế hoạch, 💬 Hỏi, ⚙️ Cài đặt ---------------------------------------------------------

QUESTIONS = [("Hôm nay còn được tiêu bao nhiêu?", "tieu"), ("Tháng này tiêu vào đâu?", "thang"),
             ("So với tháng trước thế nào?", "so"), ("Còn nợ bao nhiêu, bao giờ xong?", "no"),
             ("Quỹ đầu tư lãi lỗ thế nào?", "quy"), ("Tài chính của tôi có ổn không?", "sk"),
             ("Nhận xét chi tiêu tháng này", "nx")]


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
    import tietkiem
    remind = tietkiem.config().get("nhac", True)
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
        import tietkiem
        cfg = tietkiem.config()
        cfg["nhac"] = not cfg.get("nhac", True)
        tietkiem.save(cfg)
        return "Đã " + ("bật" if cfg["nhac"] else "tắt") + " nhắc ghi chép 21h"
    dt = ct.dautu()
    cfg = dt.config()
    cfg["baocao_toi"] = cfg.get("baocao_toi") is False
    dt.save(cfg)
    return "Đã " + ("bật" if cfg["baocao_toi"] else "tắt") + " báo lãi/lỗ quỹ buổi tối"


def chi_screen(day):
    return ct.report("thang", day)[0], ct.CHI_BUTTONS


def screen(name, day):
    import kehoach
    return {"home": lambda: home(day), "tien": lambda: money(day), "kh": lambda: kehoach.plan(day),
            "hoi": ask_screen, "chi": lambda: chi_screen(day), "ts": lambda: money(day),
            "no": lambda: ct.sono().view(day), "lt": lambda: kehoach.roadmap(day),
            "ghi": lambda: (HOW_TO, [[ct.BACK]]), "cd": settings}[name]()


def with_keyboard(reply):
    """Lần đầu (hoặc khi còn hàng nút cũ): gửi thêm lời chào kèm hàng nút cố định dưới ô chat, rồi mới tới màn hình."""
    if not kho.put_new(KEYBOARD_FLAG, True, 3 * 365 * 86400):
        return reply
    return {"messages": [(GREETING, bottom_keyboard()), reply]}


def start(args):
    if not kho.ready():
        return ct.NEED_STORE
    kho.delete(KEYBOARD_FLAG)  # /start luôn gửi lại hàng nút (lỡ người dùng tắt)
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
    if label in BOTTOM:
        return screen(BOTTOM[label], ct.today())
    if label in OLD_BOTTOM:
        return with_keyboard(screen(OLD_BOTTOM[label], ct.today()))
    return None


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
            reply = ct.answer(line, now)
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
