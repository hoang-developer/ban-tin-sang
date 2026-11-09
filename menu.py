"""Menu nút bấm cho bot chi tiêu.

- /menu (và /start): màn hình tổng quan (chi tháng này, quỹ dự phòng, nợ, tài sản ròng, việc nên làm) kèm 6 nút:
  Chi tiêu · Tài sản · Nợ · Kế hoạch · Cách ghi · Cài đặt. Bấm nút thì mở ngay trong tin đó, có nút ⬅️ Menu.
- Hàng nút cố định dưới ô chat (🏠 Menu · 📊 Chi tiêu · 💼 Tài sản · 🎯 Kế hoạch), gửi một lần ở /start, /menu.
- /huongdan: mọi lệnh, theo nhóm việc.
"""
import html
import sys

import kho
import sochitieu as ct

KEYBOARD_FLAG = "chitieu:banphim"  # đã gửi hàng nút cố định chưa (bản 1)
BOTTOM = {"🏠 Menu": "home", "📊 Chi tiêu": "chi", "💼 Tài sản": "ts", "🎯 Kế hoạch": "kh"}
MAIN = [[("📊 Chi tiêu", "m:chi"), ("💼 Tài sản", "m:ts")],
        [("💳 Nợ", "m:no"), ("🎯 Kế hoạch", "m:kh")],
        [("📝 Cách ghi", "m:ghi"), ("⚙️ Cài đặt", "m:cd")]]
GREETING = ("👋 <b>Bot ghi chi tiêu và xây tài sản</b>\n"
            "Nhắn số tiền kèm nội dung để ghi, ví dụ: <b>cà phê 35k</b>. Gửi ảnh hóa đơn, ảnh chuyển khoản cũng được.\n"
            "Các nút dưới ô chat mở nhanh menu.")
HOW_TO = ("📝 <b>Cách ghi</b>\n"
          "• Nhắn số tiền kèm nội dung: cà phê 35k · đổ xăng 80000 · tiền nhà 5tr (1tr2 là 1.200.000đ)\n"
          "• Khoản thu: + lương 19tr\n"
          "• Ngày khác: hôm qua ăn tối 250k · 02/11 cắt tóc 100k\n"
          "• Tự chọn nhóm: đóng họ 1tr #trả nợ\n"
          "• Nhiều khoản: mỗi khoản một dòng; gõ không dấu cũng được\n"
          "• 📷 Gửi ảnh hóa đơn, màn hình chuyển khoản, lịch sử giao dịch ngân hàng\n"
          "• Trả nợ: trả nợ chú Tư 5tr (tự trừ vào sổ nợ /no)\n"
          "• Mua bán cổ phiếu, ETF: mua 500 E1VFVN30 giá 33,6 · bán 100 FPT giá 120\n"
          "• Hỏi: tháng này ăn uống hết bao nhiêu?\n"
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
            "• 🏷 Nhóm chi tiêu: /nhom them 🏦 Trả nợ: trả nợ, trả góp · /nhom tukhoa Ăn uống: bún chả\n"
            "• 🎯 Ngân sách: /ngansach ăn uống 3tr · /ngansach tổng 15tr · /ngansach hằng ngày 9tr\n"
            "• 📅 Ngày lương: /luong 5 19tr (tới ngày bot hỏi đã nhận chưa)\n"
            "• 🛟 Quỹ dự phòng: /duphong muctieu 6 (tháng chi) · /duphong han 12 (đạt trong bao nhiêu tháng)\n"
            "• 📈 Đầu tư quỹ mở: /dautu gop 4tr (góp mỗi tháng) · /dautu tang 1% (mức tăng của kế hoạch)\n"
            "• 🔮 Nhóm tính chi hằng ngày: /dubao nhom ăn uống, đi chợ, đi lại")
SETTINGS_ROWS = [[("🏷 Các nhóm", "m:nhom"), ("🎯 Ngân sách", "m:ns")],
                 [("📤 Xuất Excel tháng này", "m:xuat")], [ct.BACK]]


def bottom_keyboard():
    """Hàng nút cố định dưới ô chat (bấm là gửi chữ trên nút)."""
    return {"keyboard": [[{"text": label} for label in BOTTOM]], "resize_keyboard": True, "is_persistent": True,
            "input_field_placeholder": "Nhắn khoản chi, ví dụ: cà phê 35k"}


def short(x):
    return ct.taisan().short(x) if abs(x) >= 1000 else "0đ"


def part(name, make):
    """Một dòng của màn hình tổng quan; lỗi thì bỏ dòng đó, không hỏng cả màn hình."""
    try:
        return make()
    except Exception as e:
        print(f"[lỗi] tổng quan, phần {name}: {e!r}", file=sys.stderr)
        return None


def home(day):
    if not kho.ready():
        return ct.NEED_STORE
    import kehoach
    import sono
    ts = ct.taisan()
    month = ct.load(day.strftime("%Y-%m"))
    lines = [f"🏠 <b>Tổng quan tháng {day.month}/{day.year}</b>"]
    group = part("nhóm trả nợ", lambda: sono.debt_group()[0])
    spend = [e for e in month if e["nhom"] not in (ct.INCOME, group) and not e.get("no")]
    if month:
        spent = sum(e["tien"] for e in spend)
        today = sum(e["tien"] for e in spend if e["ngay"] == day.isoformat())
        line = f"💸 Đã chi <b>{short(spent)}</b> (không tính trả nợ) · hôm nay {short(today)}"
        income = sum(e["tien"] for e in month if e["nhom"] == ct.INCOME)
        lines.append(line + (f"\n💰 Đã thu {short(income)}" if income else ""))
    else:
        lines.append("💸 Tháng này chưa ghi khoản nào. Nhắn kiểu: cà phê 35k")
    n = part("chia lương", lambda: kehoach.numbers(day))
    if n and n["fund"]["monthly"]:
        f = n["fund"]
        ratio = f["balance"] / f["target"] if f["target"] else 1
        lines.append(f"🛟 Quỹ dự phòng {short(f['balance'])}/{short(f['target'])} · {ratio * 100:.0f}%")
    debt = part("nợ", lambda: sono.home_line(day))
    if debt:
        lines.append(debt)
    saved = part("tiết kiệm", lambda: __import__("tietkiem").home_line(day))
    if saved:
        lines.append(saved)
    if ts.load()["items"] or kho.get(ts.K_GOLD):
        v = part("tài sản", lambda: ts.valuation(day))
        if v:
            lines.append(f"💼 Tài sản ròng <b>{short(v['net'])}</b>")
    actions = part("việc nên làm", lambda: kehoach.next_actions(day, n)) if n else None
    if actions:
        lines += ["", "👉 <b>Việc nên làm</b>"] + [f"• {a}" for a in actions]
    return "\n".join(lines), MAIN


def chi_screen(day):
    return ct.report("thang", day)[0], ct.CHI_BUTTONS


def ts_screen(day):
    reply = ct.taisan().overview(day)
    return reply if isinstance(reply, tuple) else (reply, [[ct.BACK]])


def screen(name, day):
    import kehoach
    import sono
    return {"home": lambda: home(day), "chi": lambda: chi_screen(day), "ts": lambda: ts_screen(day),
            "no": lambda: sono.view(day), "kh": lambda: kehoach.roadmap(day),
            "ghi": lambda: (HOW_TO, [[ct.BACK]]), "cd": lambda: (SETTINGS, SETTINGS_ROWS)}[name]()


def with_keyboard(reply):
    """Lần đầu: gửi thêm lời chào kèm hàng nút cố định dưới ô chat, rồi mới tới màn hình."""
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
    """Chữ của nút cố định dưới ô chat -> màn hình tương ứng; None nếu không phải nút."""
    name = BOTTOM.get(text.strip())
    return screen(name, ct.today()) if name else None


def on_button(arg, message, now):
    """Nút "m:...": mở một mục (sửa ngay tin đó) hoặc gửi danh sách, file."""
    day = now.date()
    if arg in ("home", "chi", "ts", "no", "kh", "ghi", "cd"):
        return ("Đang lấy giá…" if arg == "ts" else None), ("edit", lambda: screen(arg, day))
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
