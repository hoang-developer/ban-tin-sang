"""Các lệnh và nút bấm của bot Telegram; phần nhận tin nhắn nằm ở api/telegram.py.

Mỗi lệnh trả về tin nhắn HTML, hoặc (tin nhắn, nút bấm) với nút dạng [[(nhãn, dữ liệu), ...], ...].
Xem thử: python lenh.py /vang
         python lenh.py /stock FPT
"""
import html
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone

import amlich
import kho
import tg
from bantin import BUTTONS as BANTIN_BUTTONS
from bantin import VN_TZ, WEEKDAYS, build_message, gold, gold_prices, index_history, section, vn_num
from chungkhoan import MAX_SYMBOLS, SYMBOL, dong, news, quote, quotes, stock_command
from thoitiet import find_place, report

# ---- Cấu hình -------------------------------------------------------------
MAX_WATCH = 10            # số mã theo dõi tối đa
MAX_REMINDERS = 30        # số ngày cần nhớ tối đa
SAVINGS_RATE = 0.05       # lãi gửi tiết kiệm/năm để so sánh trong /neu
GUESS_DEADLINE = (9, 15)  # nhận đoán xanh/đỏ tới giờ này (hết đợt khớp lệnh mở cửa)
# ---------------------------------------------------------------------------

NEED_STORE = "⚠️ Tính năng này cần kho dữ liệu. Gõ /caidat để xem cách cài."
DATE = re.compile(r"(\d{1,2})/(\d{1,2})")
LUNAR_WORDS = {"âm", "am", "al", "âl"}


def today():
    return datetime.now(VN_TZ).date()


def day_label(d):
    return f"{WEEKDAYS[d.weekday()]} {d:%d/%m/%Y}"


def rows_of(buttons, size=3):
    return [buttons[i:i + size] for i in range(0, len(buttons), size)]


# ---- Chứng khoán và theo dõi mã ------------------------------------------------

def watchlist():
    """{mã: [báo khi ≤, báo khi ≥]} (nghìn đồng, None = không báo); {} nếu chưa có kho."""
    if not kho.ready():
        return {}
    try:
        return kho.get("theodoi", {})
    except Exception as e:
        print(f"[lỗi] đọc danh sách theo dõi: {e!r}", file=sys.stderr)
        return {}


def price_alerts():
    """Mã có đặt giá báo, theo dạng WATCHLIST của canhbao.py."""
    return {s: tuple(levels) for s, levels in watchlist().items() if any(x is not None for x in levels)}


def stock_buttons(symbols):
    if not symbols:
        return [[("🔁 Làm mới", "stock:")]]
    watch = watchlist()
    if len(symbols) == 1:
        s = symbols[0]
        return [[("✅ Đang theo dõi" if s in watch else "⭐ Theo dõi", f"theo:{s}"),
                 ("📰 Thêm tin", f"tin:{s}"), ("🔁 Làm mới", f"stock:{s}")]]
    return ([[(f"{'✅' if s in watch else '⭐'} {s}", f"theo:{s}"), (f"📰 {s}", f"tin:{s}")] for s in symbols]
            + [[("🔁 Làm mới", "stock:" + ",".join(symbols))]])


def stock(args):
    symbols = list(dict.fromkeys(a.upper() for a in args))
    text = stock_command(args)
    if not all(SYMBOL.fullmatch(s) for s in symbols):
        return text  # tham số sai: stock_command đã báo lỗi
    return text, stock_buttons(symbols[:MAX_SYMBOLS])


def more_news(symbol):
    return f"📰 <b>Tin về {symbol}</b> trong 7 ngày\n" + "\n".join(news(symbol, 8))


def parse_level(text):
    return None if text == "-" else float(text.replace(",", "."))


def level_text(levels):
    low, high = levels
    parts = ([f"≤ {dong(low * 1000)}"] if low is not None else []) + \
            ([f"≥ {dong(high * 1000)}"] if high is not None else [])
    return f" · báo khi {' hoặc '.join(parts)}" if parts else ""


def theodoi(args):
    if not kho.ready():
        return NEED_STORE
    watch = kho.get("theodoi", {})
    if not args:
        if not watch:
            return ("Chưa theo dõi mã nào.\nThêm mã: /theodoi FPT\n"
                    "Báo khi chạm giá (nghìn đồng): /theodoi FPT 50 60")
        try:
            prices = quotes(watch)
        except Exception as e:
            print(f"[lỗi] giá mã theo dõi: {e!r}", file=sys.stderr)
            prices = {}
        lines = ["⭐ <b>Mã đang theo dõi</b>"]
        for s, levels in watch.items():
            q = prices.get(s)
            price = ""
            if q and q["ref"]:
                p = q["price"] or q["ref"]
                price = f" {dong(p)} ({vn_num((p / q['ref'] - 1) * 100, sign=True)}%)"
            lines.append(f"• <b>{s}</b>{price}{level_text(levels)}")
        lines.append("<i>Có trên bảng điện ghim, bản tin tối và được báo tin cổ tức</i>")
        return "\n".join(lines), rows_of([(f"❌ Bỏ {s}", f"bo:{s}") for s in watch])
    symbol = args[0].upper()
    if not SYMBOL.fullmatch(symbol):
        return "Mã không hợp lệ. Ví dụ: /theodoi FPT 50 60"
    try:
        levels = [parse_level(a) for a in (args[1:3] + ["-", "-"])[:2]]
    except ValueError:
        return "Giá báo là số nghìn đồng, ví dụ /theodoi FPT 50 60 (dùng - để bỏ trống một bên)"
    if symbol not in watch and len(watch) >= MAX_WATCH:
        return f"Đã theo dõi tối đa {MAX_WATCH} mã. Bỏ bớt trong /theodoi"
    if not quote(symbol):
        return f"❓ Không tìm thấy mã <b>{symbol}</b>"
    watch[symbol] = levels
    kho.put("theodoi", watch)
    return f"⭐ Đã theo dõi <b>{symbol}</b>{level_text(levels)}. Xem danh sách: /theodoi"


def toggle_follow(symbol):
    """Bấm ⭐: theo dõi hoặc bỏ theo dõi; trả câu thông báo ngắn."""
    watch = kho.get("theodoi", {})
    if symbol in watch:
        del watch[symbol]
        kho.put("theodoi", watch)
        return f"Đã bỏ theo dõi {symbol}"
    if len(watch) >= MAX_WATCH:
        return f"Đã theo dõi tối đa {MAX_WATCH} mã"
    if not quote(symbol):
        return f"Không tìm thấy mã {symbol}"
    watch[symbol] = [None, None]
    kho.put("theodoi", watch)
    return f"⭐ Đã theo dõi {symbol}"


# ---- Ngày cần nhớ, âm lịch ---------------------------------------------------------

def when_text(r):
    return f"{r['ngay']}/{r['thang']}{' âm lịch' if r['am'] else ''}"


def nho(args):
    usage = ("Lưu ngày cần nhớ, bot nhắc trước 3 ngày và đúng ngày:\n"
             "/nho giỗ ông 12/3 âm\n/nho sinh nhật vợ 20/11")
    if not kho.ready():
        return NEED_STORE
    items = kho.get("nhac", [])
    if not args:
        if not items:
            return usage
        t = today()
        upcoming = sorted(((amlich.next_date(r["ngay"], r["thang"], r["am"], t), r) for r in items),
                          key=lambda x: x[0])
        lines = ["🔔 <b>Ngày cần nhớ</b>"] + [
            f"• {html.escape(r['ten'])} – {when_text(r)} · {day_label(d)} (còn {(d - t).days} ngày)"
            for d, r in upcoming]
        return "\n".join(lines), rows_of([(f"❌ {r['ten'][:14]}", f"xoanho:{r['id']}") for _, r in upcoming], 2)
    at = next((i for i, a in enumerate(args) if DATE.fullmatch(a)), None)
    if at is None:
        return usage
    day, month = map(int, DATE.fullmatch(args[at]).groups())
    lunar = any(a.lower() in LUNAR_WORDS for a in args[at + 1:])
    name = " ".join(args[:at]) or "Ngày cần nhớ"
    try:
        if lunar and not (1 <= day <= 30 and 1 <= month <= 12):
            raise ValueError
        if not lunar:
            date(2024, month, day)  # 2024 là năm nhuận nên 29/2 hợp lệ
    except ValueError:
        return f"Ngày {day}/{month} không hợp lệ.\n{usage}"
    if len(items) >= MAX_REMINDERS:
        return f"Đã lưu tối đa {MAX_REMINDERS} ngày. Xóa bớt trong /nho"
    item = {"id": max((r["id"] for r in items), default=0) + 1, "ten": name[:60],
            "ngay": day, "thang": month, "am": lunar}
    items.append(item)
    kho.put("nhac", items)
    t = today()
    d = amlich.next_date(day, month, lunar, t)
    return (f"🔔 Đã lưu: <b>{html.escape(item['ten'])}</b> – {when_text(item)}\n"
            f"Lần tới: {day_label(d)} (còn {(d - t).days} ngày). Bot nhắc trước 3 ngày và đúng ngày.")


def delete_reminder(rid):
    items = kho.get("nhac", [])
    kept = [r for r in items if str(r["id"]) != rid]
    kho.put("nhac", kept)
    return "Đã xóa" if len(kept) < len(items) else "Mục này đã xóa rồi"


def amlich_cmd(args):
    t = today()
    if args and DATE.fullmatch(args[0]):
        day, month = map(int, DATE.fullmatch(args[0]).groups())
        d = amlich.next_date(day, month, True, t) if 1 <= day <= 30 and 1 <= month <= 12 else None
        if not d:
            return f"Ngày {day}/{month} âm lịch không hợp lệ"
        return f"🌙 {day}/{month} âm lịch tới là <b>{day_label(d)}</b> (còn {(d - t).days} ngày)"
    moons = amlich.next_moon_days(t)

    def moon(d):
        return "hôm nay" if d == t else day_label(d)

    return (f"🌙 Hôm nay {t:%d/%m/%Y} là ngày <b>{amlich.label(t)}</b> âm lịch\n"
            f"Mùng 1 tới: {moon(moons[1])}\nRằm tới: {moon(moons[15])}\n"
            "<i>Đổi ngày âm sang dương: /amlich 12/3</i>")


# ---- Nếu ngày xưa mua... -------------------------------------------------------------

AMOUNT = re.compile(r"(\d+(?:[.,]\d+)?)(tr|triệu|trieu|k|ty|tỷ|tỉ|ti)?")
PERIOD = re.compile(r"(\d+)(nam|năm|thang|tháng|tuan|tuần|ngay|ngày)")
UNIT_MONEY = {None: 1, "k": 1e3, "tr": 1e6, "triệu": 1e6, "trieu": 1e6, "ty": 1e9, "tỷ": 1e9, "tỉ": 1e9, "ti": 1e9}
UNIT_DAYS = {"nam": 365, "năm": 365, "thang": 30, "tháng": 30, "tuan": 7, "tuần": 7, "ngay": 1, "ngày": 1}
INDEX_NAMES = {"VNINDEX": "VN-Index", "VN30": "VN30", "HNX": "HNX", "UPCOM": "UPCoM"}


def money(vnd):
    for unit, name in [(1e9, "tỷ"), (1e6, "triệu")]:
        if abs(vnd) >= unit:
            x = vnd / unit
            return f"{vn_num(x, 0 if abs(x - round(x)) < 0.005 else 2)} {name}"  # số tròn thì bỏ ",00"
    return f"{vn_num(vnd, 0)}đ"


def history_from(what, start):
    """(ngày mua, giá lúc đó, giá nay) kể từ ngày `start`; None nếu không đủ dữ liệu."""
    if what in ("VANG", "VÀNG"):
        hist = sorted(kho.get("vang_lichsu", {}).items()) if kho.ready() else []
        after = [(d, p) for d, p in hist if d >= str(start)]
        if not after or after[0][0] == hist[-1][0]:
            return None
        return date.fromisoformat(after[0][0]), after[0][1], hist[-1][1]
    days = (today() - start).days + 10
    t, c = index_history(what, what, days=days)
    for ts, price in zip(t, c):
        d = datetime.fromtimestamp(ts, timezone.utc).date()  # mốc là 0h UTC của ngày giao dịch
        if d >= start and ts != t[-1]:
            return d, price, c[-1]
    return None


def neu(args):
    usage = ("Nếu ngày xưa mua thì giờ thế nào?\n/neu FPT 10tr 1nam\n/neu vnindex 50tr 6thang\n"
             "/neu vang 100tr 3thang")
    if not args:
        return usage
    what, amount, days = args[0].upper(), 10e6, 365
    for a in (x.lower() for x in args[1:]):
        if m := PERIOD.fullmatch(a):
            days = int(m[1]) * UNIT_DAYS[m[2]]
        elif m := AMOUNT.fullmatch(a):
            amount = float(m[1].replace(",", ".")) * UNIT_MONEY[m[2]]
        else:
            return usage
    if not (1 <= days <= 3650) or amount <= 0:
        return "Khoảng thời gian từ 1 ngày tới 10 năm, số tiền lớn hơn 0"
    if what not in ("VANG", "VÀNG") and not SYMBOL.fullmatch(what):
        return usage
    start = today() - timedelta(days=days)
    try:
        found = history_from(what, start)
    except Exception as e:
        print(f"[lỗi] lịch sử {what}: {e!r}", file=sys.stderr)
        found = None
    gold_name = what in ("VANG", "VÀNG")
    if not found:
        if gold_name:
            return ("Chưa đủ lịch sử giá vàng cho khoảng này: không có nguồn công khai nên bot tự ghi "
                    "giá SJC mỗi tối, từ ngày cài kho dữ liệu.")
        return f"❓ Không có dữ liệu giá <b>{what}</b> trong khoảng này"
    bought, p0, p1 = found
    ratio = p1 / p0
    name = "vàng miếng SJC" if gold_name else INDEX_NAMES.get(what, what)
    if gold_name:
        prices = f"Giá bán lúc đó {vn_num(p0, 1)} → nay {vn_num(p1, 1)} triệu/lượng"
    elif what in INDEX_NAMES:
        prices = f"Điểm lúc đó {vn_num(p0)} → nay {vn_num(p1)}"
    else:
        prices = f"Giá lúc đó {dong(p0 * 1000)} → nay {dong(p1 * 1000)} <i>(giá đã điều chỉnh theo cổ tức)</i>"
    held = (today() - bought).days
    lines = [f"💭 <b>Nếu mua {name} ngày {bought:%d/%m/%Y}</b> với {money(amount)}",
             prices,
             f"{'📈' if ratio >= 1 else '📉'} Hôm nay còn <b>{money(amount * ratio)}</b> "
             f"({vn_num((ratio - 1) * 100, 1, sign=True)}%)"]
    compare = [f"gửi tiết kiệm {SAVINGS_RATE * 100:.0f}%/năm được {money(amount * (1 + SAVINGS_RATE) ** (held / 365))}"]
    if what != "VNINDEX":
        try:
            vni = history_from("VNINDEX", bought)
            if vni:
                compare.insert(0, f"VN-Index {vn_num((vni[2] / vni[1] - 1) * 100, 1, sign=True)}%")
        except Exception as e:
            print(f"[lỗi] so với VN-Index: {e!r}", file=sys.stderr)
    lines.append("So cùng kỳ: " + " · ".join(compare))
    if not gold_name:
        lines.append("<i>Chưa tính phí giao dịch và thuế</i>")
    return "\n".join(lines)


# ---- Ví vàng -------------------------------------------------------------------

KINDS = {"sjc": "sjc", "mieng": "sjc", "miếng": "sjc", "nhan": "nhan", "nhẫn": "nhan"}
UNITS = {"chi": 0.1, "chỉ": 0.1, "luong": 1, "lượng": 1, "cay": 1, "cây": 1}


def amount_text(taels):
    tenths = round(taels * 10)
    whole, rest = divmod(tenths, 10)
    return " ".join(([f"{whole} lượng"] if whole else []) + ([f"{rest} chỉ"] if rest else [])) or "0 chỉ"


def wallet(items, prices=None):
    """(các dòng chi tiết, dòng tổng) của ví vàng theo giá cửa hàng mua vào."""
    prices = prices or gold_prices()
    total = profit = 0
    priced = False
    lines = []
    for it in items:
        value = prices[it["loai"]][0] * it["luong"]  # triệu đồng
        total += value
        name = "Miếng SJC" if it["loai"] == "sjc" else prices["nhan_ten"]
        line = f"• {name} {amount_text(it['luong'])}: {vn_num(value, 1)} triệu"
        if it.get("gia"):  # chỉ món có ghi giá mua mới tính được lãi/lỗ
            gain = value - it["gia"] * it["luong"]
            profit += gain
            priced = True
            line += f" (mua {vn_num(it['gia'], 1)} → {vn_num(gain, 1, sign=True)} triệu)"
        lines.append(line)
    summary = f"Tổng: <b>{vn_num(total, 1)} triệu</b>"
    if priced:
        summary += f" · lãi/lỗ {vn_num(profit, 1, sign=True)} triệu"
    return lines, summary


def wallet_brief(items):
    _, summary = wallet(items)
    return f"👛 Ví vàng của bạn: {summary.removeprefix('Tổng: ')}"


def vivang(args):
    usage = ("Thêm vàng vào ví (giá mua triệu/lượng, có thể bỏ):\n/vivang nhan 2 chi 136\n"
             "/vivang sjc 1 luong 140\nXóa ví: /vivang xoa")
    if not kho.ready():
        return NEED_STORE
    items = kho.get("vivang", [])
    if not args:
        if not items:
            return usage
        lines, summary = wallet(items)
        return "\n".join(["🪙 <b>Ví vàng</b> <i>(theo giá cửa hàng mua vào)</i>"] + lines + [summary])
    if args[0].lower() in ("xoa", "xóa"):
        kho.put("vivang", [])
        return "🗑 Đã xóa ví vàng"
    try:
        kind = KINDS[args[0].lower()]
        taels = float(args[1].replace(",", ".")) * UNITS[args[2].lower()]
        paid = float(args[3].replace(",", ".")) if len(args) > 3 else None
    except (KeyError, IndexError, ValueError):
        return usage
    if taels <= 0 or taels > 1000:
        return usage
    items.append({"loai": kind, "luong": taels, "gia": paid})
    kho.put("vivang", items)
    lines, summary = wallet(items)
    return "\n".join([f"🪙 Đã thêm {amount_text(taels)} vào ví"] + lines + [summary])


# ---- Đoán xanh/đỏ ------------------------------------------------------------------

GUESS_TEXT = ("🎯 <b>Đoán nhanh</b>: hôm nay VN-Index đóng cửa <b>xanh</b> hay <b>đỏ</b>?\n"
              f"<i>Nhận đoán tới {GUESS_DEADLINE[0]}:{GUESS_DEADLINE[1]:02d} · 15h bot chấm điểm</i>")
GUESS_BUTTONS = [[("🟢 Xanh", "doan:xanh"), ("🔴 Đỏ", "doan:do")]]
GUESS_LABEL = {"xanh": "🟢 Xanh", "do": "🔴 Đỏ"}


def record_guess(choice, now):
    if choice not in GUESS_LABEL:
        return "Lựa chọn không hợp lệ"
    if now.weekday() >= 5 or (now.hour, now.minute) >= GUESS_DEADLINE:
        return "Hết giờ đoán hôm nay rồi"
    kho.put(f"doan:{now.date()}", choice, 3 * 86400)
    return None


def doan(args):
    if not kho.ready():
        return NEED_STORE
    s = kho.get("doan_thongke", {})
    if not s.get("tong"):
        return ("🎯 Chưa có lượt đoán nào. Mỗi ngày giao dịch, 8:15–9:15 bot hỏi VN-Index hôm nay "
                "xanh hay đỏ, 15h chấm điểm.")
    month = today().strftime("%Y-%m")
    right, total = s.get("thang", {}).get(month, [0, 0])
    return (f"🎯 <b>Đoán xanh/đỏ</b>\nĐúng {s['dung']}/{s['tong']} ({s['dung'] / s['tong'] * 100:.0f}%) · "
            f"chuỗi đúng hiện tại {s['chuoi']} · dài nhất {s['chuoi_max']}\n"
            f"Tháng này: {right}/{total}")


# ---- Thời tiết, cài đặt ----------------------------------------------------------------

def thoitiet(args):
    if not args:
        return report()
    name = " ".join(args)
    found = find_place(name)
    if not found:
        return f"Không tìm thấy nơi nào tên “{html.escape(name)}”. Thử tên tỉnh, thành phố, ví dụ /thoitiet Đà Nẵng"
    return report(*found)


def answer_location(latitude, longitude):
    return report((latitude, longitude), "chỗ bạn")


def caidat(args):
    host = os.environ.get("VERCEL_PROJECT_PRODUCTION_URL", "ban-tin-sang.vercel.app")
    lines = ["⚙️ <b>Cài đặt bot</b>"]
    if kho.ready():
        try:
            last = kho.get("tick_cuoi")
            lines.append("Kho dữ liệu: ✅ đã kết nối")
            lines.append(f"Lịch chạy: {'lần gần nhất ' + last if last else '❌ chưa chạy lần nào'}")
        except Exception as e:
            lines.append(f"Kho dữ liệu: ⚠️ lỗi {html.escape(repr(e))}")
    else:
        lines.append("Kho dữ liệu: ❌ chưa có. Cài Upstash Redis theo README (mục Kho dữ liệu)")
    lines += ["", "Trên cron-job.org, tạo việc gọi địa chỉ này mỗi 15 phút (đừng chia sẻ, có khóa bí mật):",
              f"<code>https://{host}/api/tick?key={tg.derived_secret('tick')}</code>"]
    return "\n".join(lines)


# ---- Bảng lệnh ---------------------------------------------------------------------

# tên lệnh -> (mô tả trong menu Telegram, hàm nhận các tham số sau lệnh)
COMMANDS = {
    "stock": ("Phiên chứng khoán; /stock FPT để xem một mã", stock),
    "theodoi": ("Mã theo dõi; /theodoi FPT 50 60 để báo khi chạm giá", theodoi),
    "vang": ("Giá vàng SJC", lambda args: section("🪙 Giá vàng", gold)),
    "vivang": ("Ví vàng: giá trị vàng bạn đang giữ", vivang),
    "neu": ("Nếu ngày xưa mua: /neu FPT 10tr 1nam", neu),
    "thoitiet": ("Thời tiết, gợi ý; /thoitiet Đà Nẵng cho nơi khác", thoitiet),
    "nho": ("Ngày cần nhớ: /nho giỗ ông 12/3 âm", nho),
    "amlich": ("Âm lịch hôm nay, mùng 1 và rằm tới", amlich_cmd),
    "doan": ("Thành tích đoán VN-Index xanh/đỏ", doan),
    "bantin": ("Gửi lại bản tin sáng", lambda args: (build_message(), BANTIN_BUTTONS)),
    "caidat": ("Tình trạng kho dữ liệu và lịch chạy", caidat),
}
HELP = ("Lệnh của bot:\n" + "\n".join(f"/{name} – {desc}" for name, (desc, _) in COMMANDS.items())
        + "\n📍 Gửi vị trí để xem thời tiết chỗ bạn đang đứng")
MENU = [{"command": name, "description": desc} for name, (desc, _) in COMMANDS.items()]


def answer(text):
    """Tin trả lời cho một tin nhắn của chủ bot; None nếu tin đó không phải lệnh."""
    parts = text.split()
    if not parts or not parts[0].startswith("/"):
        return None
    name = parts[0][1:].split("@")[0].lower()  # trong nhóm chat lệnh có dạng /stock@TenBot
    if name in COMMANDS:
        return COMMANDS[name][1](parts[1:])
    return HELP  # /start, /help hay gõ sai tên lệnh thì gửi hướng dẫn


def on_button(data, message, now):
    """Bấm nút dưới tin `message`: trả (thông báo nhỏ, việc tiếp theo).

    Việc tiếp theo là None hoặc (cách, hàm trả tin nhắn): "edit" sửa chính tin đó, "send" gửi tin mới,
    "buttons" chỉ thay nút.
    """
    kind, _, arg = data.partition(":")
    if kind == "bantin":
        return "Đang cập nhật bản tin…", ("edit", lambda: (build_message(), BANTIN_BUTTONS))
    if kind == "vn30":
        return None, ("send", lambda: stock([]))
    if kind == "mua":
        return None, ("send", report)
    if kind == "stock":
        return "Đang làm mới…", ("edit", lambda: stock(arg.split(",") if arg else []))
    if kind == "tin":
        return None, ("send", lambda: more_news(arg))
    if kind == "doan":
        problem = record_guess(arg, now) if kho.ready() else "Chưa có kho dữ liệu"
        if problem:
            return problem, None
        return f"Đã ghi: {GUESS_LABEL[arg]}", ("edit", lambda: f"{GUESS_TEXT}\n\nBạn chọn: <b>{GUESS_LABEL[arg]}</b>")
    if not kho.ready():
        return "Chưa có kho dữ liệu, gõ /caidat", None
    if kind == "theo":
        toast = toggle_follow(arg)
        # Giữ nguyên danh sách mã của tin: lấy từ nút "Làm mới" (stock:FPT,VNM)
        keys = [b.get("callback_data", "") for row in (message.get("reply_markup") or {}).get(
            "inline_keyboard", []) for b in row]
        symbols = next((k[6:].split(",") for k in keys if k.startswith("stock:") and k != "stock:"), [arg])
        return toast, ("buttons", lambda: stock_buttons(symbols))
    if kind == "bo":
        watch = kho.get("theodoi", {})
        watch.pop(arg, None)
        kho.put("theodoi", watch)
        return f"Đã bỏ theo dõi {arg}", ("edit", lambda: theodoi([]))
    if kind == "xoanho":
        return delete_reminder(arg), ("edit", lambda: nho([]))
    return None, None


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    reply = answer(" ".join(sys.argv[1:]))
    text, buttons = reply if isinstance(reply, tuple) else (reply, None)
    print(text or "(không phải lệnh)")
    for row in buttons or []:
        print("  ".join(f"[{label}]" for label, _ in row))


if __name__ == "__main__":
    main()
