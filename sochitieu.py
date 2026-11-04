"""Bot ghi chi tiêu: nhắn "cà phê 35k" là bot ghi lại và tự xếp nhóm; phần nhận tin ở api/chitieu.py.

Mỗi lệnh trả về tin nhắn HTML, hoặc (tin nhắn, nút bấm) như lenh.py; /xuat trả về file CSV.
Xem thử (chỉ đọc và xếp nhóm, không ghi): python sochitieu.py "cà phê 35k"
"""
import csv
import html
import io
import json
import os
import re
import sys
import unicodedata
from calendar import monthrange
from datetime import date, datetime, timedelta

import kho
from bantin import VN_TZ, WEEKDAYS, vn_num

# ---- Nhóm chi tiêu --------------------------------------------------------------
# mã -> (tên, từ khóa). Từ khóa so khớp nguyên từ; nhiều từ cùng khớp thì lấy cụm dài nhất
# ("tiền nước" thắng "nước"). Gõ không dấu cũng nhận ra.
CATEGORIES = {
    "an": ("🍜 Ăn uống", [
        "ăn", "ăn sáng", "ăn trưa", "ăn tối", "ăn đêm", "ăn vặt", "cơm", "cơm văn phòng", "phở", "bún", "miến",
        "mì", "mỳ", "hủ tiếu", "bánh mì", "bánh cuốn", "bánh", "bánh ngọt", "xôi", "cháo", "lẩu", "nướng", "gà",
        "vịt", "bò", "pizza", "burger", "kfc", "lotteria", "jollibee", "mcdonald", "cà phê", "cafe", "coffee",
        "highlands", "highland", "starbucks", "starbuck", "phúc long", "katinat", "trà", "trà sữa", "trà đá",
        "nước", "nước ngọt", "nước suối", "nước lọc", "nước mía", "nước ép", "sinh tố", "bia", "rượu", "nhậu", "chè", "kem", "sữa chua", "hoa quả", "trái cây",
        "đồ ăn", "nhà hàng", "quán", "buffet", "grabfood", "shopeefood", "baemin", "gofood", "đặt đồ ăn",
        "bim bim", "snack", "kẹo", "liên hoan", "tiệc"]),
    "cho": ("🛒 Đi chợ, siêu thị", [
        "chợ", "đi chợ", "siêu thị", "winmart", "vinmart", "bách hóa xanh", "coopmart", "co.op", "aeon", "big c",
        "lotte mart", "mega market", "tạp hóa", "rau", "thịt", "cá", "tôm", "trứng", "gạo", "mắm", "dầu ăn",
        "gia vị", "sữa", "đồ khô", "thực phẩm", "nước giặt", "bột giặt", "giấy vệ sinh", "nước rửa bát",
        "dầu gội", "sữa tắm", "kem đánh răng", "đồ dùng"]),
    "xe": ("🛵 Đi lại", [
        "xăng", "đổ xăng", "grab", "grabbike", "grabcar", "be", "xanh sm", "taxi", "gojek", "xe ôm", "gửi xe",
        "trông xe", "đỗ xe", "vé xe", "xe khách", "xe buýt", "bus", "tàu", "vé tàu", "máy bay", "vé máy bay",
        "metro", "xe", "xe máy", "ô tô", "oto", "rửa xe", "sửa xe", "thay dầu", "thay nhớt", "bảo dưỡng",
        "bảo dưỡng xe", "vá xe", "lốp", "phí đường", "cầu đường", "vetc", "epass", "đăng kiểm", "bảo hiểm xe", "phạt nguội", "nộp phạt"]),
    "nha": ("🏠 Nhà cửa, hóa đơn", [
        "tiền nhà", "thuê nhà", "tiền phòng", "tiền trọ", "trọ", "điện", "tiền điện", "hóa đơn điện",
        "tiền nước", "hóa đơn nước", "internet", "wifi", "tiền mạng", "cước", "điện thoại", "nạp điện thoại",
        "nạp tiền điện thoại", "4g", "gas", "bình gas", "phí quản lý", "phí dịch vụ", "chung cư", "sửa nhà",
        "sửa điện", "thợ", "đồ gia dụng", "nồi", "chảo", "giường", "tủ", "bàn ghế", "điều hòa", "máy giặt",
        "tủ lạnh", "truyền hình", "k+", "viettel", "vnpt", "fpt"]),
    "mua": ("🛍️ Mua sắm", [
        "mua", "quần", "áo", "quần áo", "váy", "giày", "dép", "túi", "ví", "đồng hồ", "kính", "mỹ phẩm", "son",
        "nước hoa", "skincare", "shopee", "lazada", "tiki", "tiktok shop", "sendo", "uniqlo", "zara",
        "mua điện thoại", "laptop", "máy tính", "tai nghe", "ốp lưng", "sạc", "đồ điện tử", "phụ kiện",
        "trang sức", "cây cảnh", "đồ trang trí", "cắt tóc", "làm tóc", "gội đầu", "làm nail", "spa"]),
    "khoe": ("💊 Sức khỏe", [
        "thuốc", "nhà thuốc", "pharmacity", "long châu", "khám", "khám bệnh", "bệnh viện", "phòng khám",
        "nha khoa", "răng", "xét nghiệm", "tiêm", "vắc xin", "vitamin", "thực phẩm chức năng", "bảo hiểm",
        "bảo hiểm y tế", "gym", "phòng tập", "yoga", "bơi", "massage", "khẩu trang", "kính mắt"]),
    "choi": ("🎬 Giải trí, du lịch", [
        "phim", "xem phim", "rạp", "cgv", "lotte cinema", "bhd", "netflix", "spotify", "youtube",
        "youtube premium", "apple music", "icloud", "google one", "chatgpt", "game", "nạp game", "steam",
        "karaoke", "bi a", "bida", "concert", "vé xem", "du lịch", "khách sạn", "homestay", "resort", "tour",
        "vé tham quan", "dã ngoại", "picnic", "cắm trại", "đi chơi"]),
    "hoc": ("📚 Học tập", [
        "học phí", "tiền học", "đóng học", "học", "học thêm", "lớp", "khóa học", "sách", "vở", "bút",
        "văn phòng phẩm", "giáo trình", "udemy", "coursera", "tiếng anh", "ielts", "lệ phí thi"]),
    "qua": ("🎁 Hiếu hỷ, quà tặng", [
        "đám cưới", "cưới", "mừng cưới", "sinh nhật", "quà", "tặng", "biếu", "đám ma", "đám hiếu", "phúng",
        "viếng", "lì xì", "mừng tuổi", "từ thiện", "ủng hộ", "hoa", "đi lễ", "lễ chùa", "công đức"]),
    "giadinh": ("👨‍👩‍👧 Gia đình, con cái", [
        "cho con", "của con", "con đi học", "cho bé", "bỉm", "tã", "sữa bột", "đồ chơi", "gửi bố mẹ",
        "biếu bố mẹ", "bố mẹ", "ông bà", "giúp việc", "osin", "trông trẻ", "nhà trẻ", "mầm non", "thú cưng",
        "cho chó", "cho mèo", "thức ăn cho chó", "thức ăn cho mèo", "pate"]),
    "khac": ("📦 Khác", []),
    "thu": ("💰 Thu nhập", [
        "lương", "nhận lương", "thưởng", "tiền thưởng", "hoa hồng", "lãi tiết kiệm", "cổ tức", "bán",
        "thu nhập", "được cho", "được tặng", "hoàn tiền", "cashback", "freelance", "làm thêm"]),
}
GENERIC = {"mua", "ăn", "quán", "học", "bánh", "nước", "xe"}  # từ chung chung: chỉ dùng khi không có từ nào rõ hơn
INCOME, OTHER = "thu", "khac"
MAX_LEARNED = 500  # số cụm từ học được tối đa
# ---------------------------------------------------------------------------------

K_COUNTER, K_LEARN, K_BUDGET = "chitieu:dem", "chitieu:hoc", "chitieu:ngansach"
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

def norm(text):
    return " ".join(unicodedata.normalize("NFC", text).lower().split())


def plain(text):
    """Bỏ dấu: 'Cà phê đá' -> 'ca phe da'."""
    text = unicodedata.normalize("NFD", norm(text).replace("đ", "d"))
    return "".join(c for c in text if not unicodedata.combining(c))


def word_pattern(word):
    return re.compile(rf"(?<!\w){re.escape(word)}(?!\w)")


# (mẫu có dấu, mẫu không dấu, điểm, mã nhóm); điểm là độ dài cụm, từ chung chung điểm thấp
KEYWORDS = [(word_pattern(norm(k)), word_pattern(plain(k)), 0.5 if norm(k) in GENERIC else len(norm(k)), code)
            for code, (_, words) in CATEGORIES.items() for k in words]


def classify(note, learned=None):
    """Mã nhóm của ghi chú. Cụm từ đã học (người dùng sửa nhóm) thắng từ khóa có sẵn."""
    text, bare = norm(note), plain(note)
    learned_rules = [(word_pattern(k), word_pattern(plain(k)), 100 + len(k), code)
                     for k, code in (learned or {}).items() if code in CATEGORIES]
    rules = learned_rules + KEYWORDS
    # So dạng bỏ dấu chỉ trên những chữ người dùng gõ không dấu; chữ đã có dấu thì che đi,
    # kẻo "trả" bỏ dấu thành "tra" rồi bị hiểu là "trà".
    typed_plain = " ".join(w if w == plain(w) else "#" for w in text.split())
    # Câu có dấu: so có dấu trước, không khớp gì mới so phần gõ không dấu.
    # Câu gõ không dấu: so dạng bỏ dấu ngay, để "cho be" (cho bé) thắng "be" (gọi xe).
    passes = [(1, typed_plain)] if text == bare else [(0, text), (1, typed_plain)]
    for index, subject in passes:
        found = [(score, code) for *patterns, score, code in rules if patterns[index].search(subject)]
        if found:
            return max(found, key=lambda x: x[0])[1]
    return OTHER


MONEY = re.compile(
    r"(?<![\w.,])(\d+(?:[.,]\d+)*)\s*"                                   # 35 | 35.000 | 1,5
    r"(k|nghìn|nghin|ngàn|ngan|tr|triệu|trieu|củ|cu|tỷ|ty|tỏi)?(\d{1,3})?"  # đơn vị, phần lẻ: 1tr2, 1k5
    r"\s*(đ|đồng|dong|vnđ|vnd)?(?!\w)", re.IGNORECASE)
UNITS = {"k": 1e3, "nghìn": 1e3, "nghin": 1e3, "ngàn": 1e3, "ngan": 1e3, "tr": 1e6, "triệu": 1e6, "trieu": 1e6,
         "củ": 1e6, "cu": 1e6, "tỷ": 1e9, "ty": 1e9, "tỏi": 1e9}
DATE = re.compile(r"(?<![\d/])(\d{1,2})/(\d{1,2})(?:/(\d{2}|\d{4}))?(?![\d/])")
DAY_WORDS = {"hôm nay": 0, "hôm qua": -1, "hôm kia": -2}


def to_number(digits):
    """'35.000' -> 35000; '1,5' -> 1.5; None nếu không đọc được."""
    parts = re.split(r"[.,]", digits)
    if len(parts) > 1 and all(len(p) == 3 for p in parts[1:]):
        return float("".join(parts))  # dấu ngăn nghìn
    if len(parts) == 2:
        return float(f"{parts[0]}.{parts[1]}")  # số lẻ: 1,5tr
    return float(digits) if len(parts) == 1 else None


def money(match):
    """Số tiền (đồng) của một chỗ khớp MONEY, kèm cờ có ghi đơn vị/đồng hay không."""
    number = to_number(match[1])
    if number is None:
        return None, False
    unit = UNITS.get((match[2] or "").lower())
    if unit:
        number = number * unit + (int(match[3]) / 10 ** len(match[3]) * unit if match[3] else 0)
    elif not match[4] and number < 1000:
        number *= 1000  # "cà phê 35" hiểu là 35 nghìn
    return round(number), bool(unit or match[4])


def parse_amount(text):
    """Số tiền trong một đoạn chữ: (số tiền, vị trí bắt đầu, vị trí kết thúc) hoặc None.

    Có nhiều số thì ưu tiên số có ghi đơn vị (35k, 1tr, 35.000đ), rồi tới số đứng sau cùng.
    """
    found = []
    for m in MONEY.finditer(text):
        value, explicit = money(m)
        if value:
            found.append((explicit, m.start(), value, m.end()))
    if not found:
        return None
    explicit, start, value, end = max(found)
    return value, start, end


def parse_date(text, day):
    """Ngày ghi trong câu ('hôm qua', '02/11'): (ngày, câu đã bỏ phần ngày)."""
    t = norm(text)
    for words, offset in DAY_WORDS.items():
        for form in (words, plain(words)):
            if word_pattern(form).search(t):
                return day + timedelta(days=offset), word_pattern(form).sub(" ", t)
    m = DATE.search(t)
    if m:
        year = int(m[3]) + (2000 if m[3] and len(m[3]) == 2 else 0) if m[3] else day.year
        try:
            d = date(year, int(m[2]), int(m[1]))
            if not m[3] and d > day:
                d = d.replace(year=year - 1)  # 25/12 nhắn hồi tháng 1 là năm trước
            return d, t[:m.start()] + " " + t[m.end():]
        except ValueError:
            pass
    return day, t


def parse_line(line, day, learned=None):
    """Một dòng tin nhắn -> khoản chi/thu (chưa có id), None nếu không có số tiền."""
    line = line.strip()
    income = line.startswith("+")
    when, text = parse_date(line.lstrip("+").strip(), day)
    found = parse_amount(text)
    if not found:
        return None
    amount, start, end = found
    note = " ".join((text[:start] + " " + text[end:]).split()).strip(" ,.:;-–")
    return {"ngay": when.isoformat(), "tien": amount, "ghichu": note,
            "nhom": INCOME if income else classify(note, learned)}


# ---- Lưu trữ: mỗi tháng một Redis hash, mỗi khoản một mục (id -> JSON) ---------------
# Ghi/sửa/xóa từng mục riêng nên hai tin nhắn tới cùng lúc không đè mất khoản của nhau.

def month_key(ym):
    return f"chitieu:{ym}"


def load(ym):
    flat = kho.command("HGETALL", month_key(ym)) or []  # [id1, json1, id2, json2, ...]
    return sorted((json.loads(v) for v in flat[1::2]), key=lambda e: e["id"])


def save(e):
    kho.command("HSET", month_key(e["ngay"][:7]), e["id"], json.dumps(e, ensure_ascii=False))


def ref(e):
    return f"{e['ngay'][:7]}:{e['id']}"


def find(reference):
    """'2026-11:12' -> khoản đó, None nếu đã xóa."""
    ym, _, rid = reference.partition(":")
    value = kho.command("HGET", month_key(ym), rid)
    return json.loads(value) if value else None


def add(text, now):
    """Ghi mọi khoản trong tin nhắn (mỗi dòng một khoản); trả về các khoản đã ghi."""
    learned = kho.get(K_LEARN, {})
    entries = [e for e in (parse_line(line, now.date(), learned) for line in text.splitlines()) if e]
    for e in entries:
        e["id"] = kho.command("INCR", K_COUNTER)
        e["gio"] = now.strftime("%H:%M")
        save(e)
    return entries


def between(start, end):
    """Các khoản từ ngày start tới end (tính cả hai đầu)."""
    out, ym = [], date(start.year, start.month, 1)
    while ym <= end:
        out += [e for e in load(ym.strftime("%Y-%m")) if start.isoformat() <= e["ngay"] <= end.isoformat()]
        ym = (ym + timedelta(days=32)).replace(day=1)
    return out


def recent(day, limit):
    """Các khoản mới nhất của tháng này và tháng trước."""
    prev = (day.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    items = load(prev) + load(day.strftime("%Y-%m"))
    return sorted(items, key=lambda e: (e["ngay"], e.get("gio", ""), e["id"]), reverse=True)[:limit]


def learn(note, code):
    if not note:
        return
    learned = kho.get(K_LEARN, {})
    learned.pop(norm(note), None)
    learned[norm(note)] = code
    kho.put(K_LEARN, dict(list(learned.items())[-MAX_LEARNED:]))


# ---- Hiển thị ---------------------------------------------------------------------

def vnd(x):
    return f"{vn_num(x, 0)}đ"


def name(code):
    return CATEGORIES.get(code, CATEGORIES[OTHER])[0]


def entry_text(e, day):
    when = "" if e["ngay"] == day.isoformat() else (
        " · hôm qua" if e["ngay"] == (day - timedelta(days=1)).isoformat() else f" · {e['ngay'][8:]}/{e['ngay'][5:7]}")
    note = html.escape(e["ghichu"]) if e["ghichu"] else "<i>không ghi chú</i>"
    return f"<b>{vnd(e['tien'])}</b> · {name(e['nhom'])} — {note}{when}"


def budget_lines(codes, day):
    """Tiến độ ngân sách tháng của các nhóm vừa ghi (và ngân sách tổng)."""
    budgets = kho.get(K_BUDGET, {})
    if not budgets:
        return []
    items = [e for e in load(day.strftime("%Y-%m")) if e["nhom"] != INCOME]
    lines = []
    for code in [c for c in dict.fromkeys(codes) if c in budgets] + (["tong"] if "tong" in budgets else []):
        spent = sum(e["tien"] for e in items if code == "tong" or e["nhom"] == code)
        limit = budgets[code]
        pct = spent / limit * 100
        label = "Tổng chi" if code == "tong" else name(code)
        mark = "🚨" if pct >= 100 else "⚠️" if pct >= 80 else "🎯"
        extra = f", vượt {vnd(spent - limit)}" if pct > 100 else ""
        lines.append(f"{mark} {label} tháng {day.month}: {vnd(spent)} / {vnd(limit)} ({pct:.0f}%{extra})")
    return lines


def entries_message(entries, day):
    """Tin báo các khoản vừa ghi, kèm nút ✏️ đổi nhóm và ❌ xóa từng khoản."""
    if not entries:
        return "🗑 Đã xóa", None
    budget = budget_lines([e["nhom"] for e in entries if e["nhom"] != INCOME], day)
    if len(entries) == 1:
        e = entries[0]
        text = "\n".join([f"✅ Đã ghi {entry_text(e, day)}"] + budget)
        return text, [[("✏️ Đổi nhóm", f"doi:{ref(e)}"), ("❌ Xóa", f"xoa:{ref(e)}")]]
    total = sum(e["tien"] for e in entries if e["nhom"] != INCOME)
    lines = [f"✅ Đã ghi {len(entries)} khoản" + (f", chi <b>{vnd(total)}</b>" if total else "")]
    lines += [f"{i}. {entry_text(e, day)}" for i, e in enumerate(entries, 1)]
    buttons = [[(f"✏️ {i}. {e['ghichu'][:12] or vnd(e['tien'])}", f"doi:{ref(e)}"), (f"❌ {i}", f"xoa:{ref(e)}")]
               for i, e in enumerate(entries, 1)]
    return "\n".join(lines + budget), buttons


def picker(reference, other_rows):
    """Nút chọn nhóm cho một khoản, giữ nguyên nút của các khoản khác trong cùng tin."""
    choices = [(label, f"nhom:{reference}:{code}") for code, (label, _) in CATEGORIES.items()]
    rows = [choices[i:i + 2] for i in range(0, len(choices), 2)]
    return rows + [[("↩️ Thôi", f"giu:{reference}")]] + other_rows


# ---- Báo cáo ------------------------------------------------------------------------

REPORT_BUTTONS = [[("Hôm nay", "bc:ngay"), ("Tuần này", "bc:tuan"), ("Tháng này", "bc:thang"),
                   ("Tháng trước", "bc:thangtruoc")]]


def period(kind, day):
    """(từ ngày, tới ngày, tên kỳ, từ ngày kỳ trước, tới ngày kỳ trước, tên kỳ trước)."""
    first = day.replace(day=1)
    if kind == "ngay":
        y = day - timedelta(days=1)
        return day, day, "hôm nay", y, y, "hôm qua"
    if kind == "tuan":
        start = day - timedelta(days=day.weekday())
        return start, day, "tuần này", start - timedelta(days=7), day - timedelta(days=7), "tuần trước, cùng số ngày"
    if kind == "thang":
        prev_first = (first - timedelta(days=1)).replace(day=1)
        prev_end = min(prev_first + timedelta(days=day.day - 1), first - timedelta(days=1))
        return first, day, f"tháng {day.month}/{day.year}", prev_first, prev_end, "cùng kỳ tháng trước"
    if kind == "thangtruoc":
        end = first - timedelta(days=1)
        return full_month(end.year, end.month, day)
    month = int(kind)  # /thang 10
    year = day.year if month <= day.month else day.year - 1
    return full_month(year, month, day)


def full_month(year, month, day):
    start = date(year, month, 1)
    end = min(date(year, month, monthrange(year, month)[1]), day)
    prev_end = start - timedelta(days=1)
    return (start, end, f"tháng {month}/{year}", prev_end.replace(day=1), prev_end,
            f"tháng {prev_end.month}/{prev_end.year}")


def report(kind, day):
    """(nội dung báo cáo, số khoản chi) của một kỳ."""
    start, end, label, prev_start, prev_end, prev_label = period(kind, day)
    items = between(start, end)
    spend = [e for e in items if e["nhom"] != INCOME]
    income = sum(e["tien"] for e in items if e["nhom"] == INCOME)
    total = sum(e["tien"] for e in spend)
    span = f"{start:%d/%m}" + (f" – {end:%d/%m}" if end != start else "")
    lines = [f"📊 <b>Chi tiêu {label}</b> ({span})"]
    if not items:
        return "\n".join(lines + ["Chưa có khoản nào. Nhắn kiểu: cà phê 35k"]), 0
    days = (end - start).days + 1
    lines.append(f"Chi: <b>{vnd(total)}</b> · {len(spend)} khoản" + (f" · TB {vnd(total / days)}/ngày" if days > 1 else ""))
    by_cat = {}
    for e in spend:
        by_cat[e["nhom"]] = by_cat.get(e["nhom"], 0) + e["tien"]
    top = max(by_cat.values(), default=0)
    for code, amount in sorted(by_cat.items(), key=lambda x: -x[1]):
        lines.append(f"{name(code)}: <b>{vnd(amount)}</b> ({amount / total * 100:.0f}%)\n"
                     + "▇" * max(1, round(amount / top * 10)))
    prev_total = sum(e["tien"] for e in between(prev_start, prev_end) if e["nhom"] != INCOME)
    if prev_total:
        change = (total - prev_total) / prev_total * 100
        lines.append(f"So với {prev_label}: {'↑' if change >= 0 else '↓'} {abs(change):.0f}% ({vnd(prev_total)})")
    if income:
        lines.append(f"💰 Thu: {vnd(income)} · còn lại <b>{vnd(income - total)}</b>")
    biggest = sorted(spend, key=lambda e: -e["tien"])[:3]
    if biggest and len(spend) > 3:
        lines.append("Khoản lớn nhất: " + " · ".join(
            f"{html.escape(e['ghichu'] or name(e['nhom']))} {vnd(e['tien'])}" for e in biggest))
    status = budget_status(day) if kind == "thang" else []
    if status:
        lines += ["", "<b>Ngân sách</b>"] + status
    return "\n".join(lines), len(spend)


def budget_status(day):
    """Tiến độ mọi ngân sách đã đặt (từng nhóm và tổng) trong tháng này."""
    return budget_lines([c for c in kho.get(K_BUDGET, {}) if c != "tong"], day)


# ---- Lệnh ---------------------------------------------------------------------------

HELP = ("💸 <b>Bot ghi chi tiêu</b>\nNhắn số tiền kèm nội dung, bot tự xếp nhóm:\n"
        "• cà phê 35k\n• đổ xăng 80000\n• tiền nhà 5tr · 1tr2 là 1.200.000đ\n"
        "• hôm qua ăn tối 250k · 02/11 cắt tóc 100k\n• + lương 20tr (dấu + là khoản thu)\n"
        "Nhiều khoản thì mỗi khoản một dòng; gõ không dấu cũng được.\n"
        "Xếp sai nhóm thì bấm ✏️ Đổi nhóm, lần sau bot tự nhớ.\n\n")


def baocao(args):
    kind = {"homnay": "ngay", "ngay": "ngay", "tuan": "tuan", "thang": "thang", "thangtruoc": "thangtruoc"}.get(
        plain("".join(args)), "thang")
    return report(kind, today())[0], REPORT_BUTTONS


def thang(args):
    if args and args[0].isdigit() and 1 <= int(args[0]) <= 12:
        return report(str(int(args[0])), today())[0], REPORT_BUTTONS
    return report("thang", today())[0], REPORT_BUTTONS


def lichsu(args):
    day = today()
    items = recent(day, 10)
    if not items:
        return "Chưa có khoản nào. Nhắn kiểu: cà phê 35k"
    lines = ["🧾 <b>10 khoản gần nhất</b>"] + [
        f"{i}. {e['ngay'][8:]}/{e['ngay'][5:7]} {e.get('gio', '')} · {entry_text(e, day).split(' · ', 1)[0]} · "
        f"{name(e['nhom']).split()[0]} {html.escape(e['ghichu'])}" for i, e in enumerate(items, 1)]
    buttons = [(f"❌ {i}", f"xls:{ref(e)}") for i, e in enumerate(items, 1)]
    return "\n".join(lines), [buttons[i:i + 5] for i in range(0, len(buttons), 5)]


def delete(reference):
    """Xóa một khoản; trả về khoản đã xóa, None nếu đã xóa từ trước."""
    gone = find(reference)
    if gone:
        kho.command("HDEL", month_key(gone["ngay"][:7]), gone["id"])
    return gone


def xoa_cuoi(args):
    items = recent(today(), 1)
    if not items:
        return "Chưa có khoản nào để xóa"
    gone = delete(ref(items[0]))
    return f"🗑 Đã xóa: {entry_text(gone, today())}"


def find_category(text):
    """Tên nhóm người dùng gõ ('ăn uống', 'di lai', 'tổng') -> mã, None nếu không rõ."""
    key = plain(text)
    if key in ("tong", "tat ca", "tong chi"):
        return "tong"
    for code, (label, _) in CATEGORIES.items():
        if key and key in plain(label.split(" ", 1)[1]):
            return code
    code = classify(text)
    return None if code == OTHER else code


def ngansach(args):
    usage = ("Đặt ngân sách tháng: /ngansach ăn uống 3tr · /ngansach tổng 15tr\n"
             "Bỏ ngân sách: /ngansach ăn uống 0")
    budgets = kho.get(K_BUDGET, {})
    if not args:
        lines = budget_status(today())
        return "\n".join(["🎯 <b>Ngân sách tháng này</b>"] + lines + ["", usage]) if lines else usage
    code = find_category(" ".join(args[:-1]))
    if code is None or code == INCOME:
        return usage
    if args[-1] == "0":
        budgets.pop(code, None)
        kho.put(K_BUDGET, budgets)
        return f"Đã bỏ ngân sách {'tổng' if code == 'tong' else name(code)}"
    found = parse_amount(args[-1])
    if found is None:
        return usage
    budgets[code] = found[0]
    kho.put(K_BUDGET, budgets)
    label = "Tổng chi" if code == "tong" else name(code)
    return "\n".join([f"🎯 Ngân sách {label}: {vnd(found[0])}/tháng"] + budget_lines([code], today()))


def nhom_cmd(args):
    learned = kho.get(K_LEARN, {})
    lines = ["🗂 <b>Các nhóm và vài từ khóa</b>"]
    for code, (label, words) in CATEGORIES.items():
        sample = ", ".join(words[:6]) if words else "những khoản không khớp nhóm nào"
        lines.append(f"{label}: <i>{html.escape(sample)}</i>")
    lines.append(f"\nBot đã học {len(learned)} cụm từ từ những lần bạn bấm ✏️ Đổi nhóm.")
    return "\n".join(lines)


def xuat(args):
    day = today()
    if args and args[0].isdigit() and 1 <= int(args[0]) <= 12:
        month = int(args[0])
        year = day.year if month <= day.month else day.year - 1
    else:
        year, month = day.year, day.month
    items = sorted(load(f"{year}-{month:02d}"), key=lambda e: (e["ngay"], e.get("gio", ""), e["id"]))
    if not items:
        return f"Tháng {month}/{year} chưa có khoản nào"
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Ngày", "Giờ", "Số tiền", "Thu/Chi", "Nhóm", "Ghi chú"])
    for e in items:
        writer.writerow([f"{e['ngay'][8:]}/{e['ngay'][5:7]}/{e['ngay'][:4]}", e.get("gio", ""), e["tien"],
                         "Thu" if e["nhom"] == INCOME else "Chi", name(e["nhom"]).split(" ", 1)[1], e["ghichu"]])
    # BOM để Excel nhận đúng tiếng Việt
    return {"file": ("\ufeff" + buf.getvalue()).encode("utf-8"), "name": f"chitieu-{year}-{month:02d}.csv",
            "caption": f"Chi tiêu tháng {month}/{year}: {len(items)} khoản"}


COMMANDS = {
    "baocao": ("Báo cáo chi tiêu, có nút chọn kỳ", baocao),
    "homnay": ("Chi tiêu hôm nay", lambda args: (report("ngay", today())[0], REPORT_BUTTONS)),
    "tuan": ("Chi tiêu tuần này", lambda args: (report("tuan", today())[0], REPORT_BUTTONS)),
    "thang": ("Chi tiêu tháng này; /thang 10 cho tháng 10", thang),
    "lichsu": ("10 khoản gần nhất, bấm ❌ để xóa", lichsu),
    "xoa": ("Xóa khoản vừa ghi", xoa_cuoi),
    "ngansach": ("Ngân sách tháng: /ngansach ăn uống 3tr", ngansach),
    "nhom": ("Các nhóm chi tiêu", nhom_cmd),
    "xuat": ("Xuất file CSV mở bằng Excel: /xuat 10", xuat),
}
HELP += "Lệnh:\n" + "\n".join(f"/{n} – {desc}" for n, (desc, _) in COMMANDS.items())
MENU = [{"command": n, "description": desc} for n, (desc, _) in COMMANDS.items()]


def answer(text, now):
    """Trả lời một tin nhắn: lệnh, hoặc các khoản chi/thu cần ghi."""
    if not kho.ready():
        return NEED_STORE
    parts = text.split()
    if parts and parts[0].startswith("/"):
        command = parts[0][1:].split("@")[0].lower()
        return COMMANDS[command][1](parts[1:]) if command in COMMANDS else HELP
    entries = add(text, now)
    if not entries:
        return "Không thấy số tiền. Nhắn kiểu: <b>cà phê 35k</b> hoặc gõ /start để xem hướng dẫn"
    return entries_message(entries, now.date())


def button_ref(data):
    """'nhom:2026-11:12:an' -> '2026-11:12' (khoản mà nút đó trỏ tới), None nếu không phải nút của khoản."""
    kind, _, rest = data.partition(":")
    return ":".join(rest.split(":")[:2]) if kind in ("doi", "xoa", "nhom", "giu") else None


def keyboard_rows(message):
    return [[(b["text"], b.get("callback_data", "")) for b in row]
            for row in (message.get("reply_markup") or {}).get("inline_keyboard", [])]


def refs_in(message):
    """Các khoản có nút dưới tin, theo thứ tự xuất hiện."""
    refs = [button_ref(data) for row in keyboard_rows(message) for _, data in row]
    return list(dict.fromkeys(r for r in refs if r))


def render(refs, day):
    return entries_message([e for e in map(find, refs) if e], day)


def on_button(data, message, now):
    """Bấm nút: trả (thông báo nhỏ, việc tiếp theo) như lenh.on_button."""
    if not kho.ready():
        return "Chưa có kho dữ liệu", None
    kind, _, arg = data.partition(":")
    day = now.date()
    if kind == "bc":
        return None, ("edit", lambda: (report(arg, day)[0], REPORT_BUTTONS))
    if kind == "xls":
        gone = delete(arg)
        return ("Đã xóa" if gone else "Khoản này đã xóa rồi"), ("edit", lambda: lichsu([]))
    refs = refs_in(message)
    if kind == "doi":
        others = [row for row in keyboard_rows(message) if all(button_ref(d) != arg for _, d in row)]
        return "Chọn nhóm đúng cho khoản này", ("buttons", lambda: picker(arg, others))
    if kind == "nhom":
        reference, _, code = arg.rpartition(":")
        e = find(reference)
        if e is None or code not in CATEGORIES:
            return "Khoản này đã xóa rồi", ("edit", lambda: render(refs, day))
        e["nhom"] = code
        save(e)
        if code != INCOME:
            learn(e["ghichu"], code)
        return f"Đã chuyển sang {name(code)}, lần sau bot tự nhớ", ("edit", lambda: render(refs, day))
    if kind == "giu":
        return None, ("edit", lambda: render(refs, day))
    if kind == "xoa":
        gone = delete(arg)
        return ("Đã xóa" if gone else "Khoản này đã xóa rồi"), ("edit", lambda: render(refs, day))
    return None, None


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    for line in " ".join(sys.argv[1:]).split("\\n"):
        e = parse_line(line, today())
        print(f"{line!r} -> " + (f"{vnd(e['tien'])} · {name(e['nhom'])} · {e['ghichu']!r} · {e['ngay']}"
                                 if e else "không thấy số tiền"))


if __name__ == "__main__":
    main()
