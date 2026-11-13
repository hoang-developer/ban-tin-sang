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
MAX_GROUPS, MAX_WORDS = 20, 60  # số nhóm tự tạo, số từ khóa tự thêm cho mỗi nhóm
# ---------------------------------------------------------------------------------

K_COUNTER, K_LEARN, K_BUDGET, K_AI = "chitieu:dem", "chitieu:hoc", "chitieu:ngansach", "chitieu:ai"
K_GROUPS, K_AI_STATS = "chitieu:nhomrieng", "chitieu:ai:thongke"
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


# Bỏ dấu rồi trùng với chữ thường gặp: "chợ"/"cho", "cá"/"ca", "quà"/"qua", "vở"/"vợ", "gà"/"ga"(gas)...
# Câu gõ không dấu thì không dùng các dạng này để đoán nhóm.
AMBIGUOUS_PLAIN = {"cho", "ca", "qua", "ta", "tu", "vo", "noi", "bo", "ga", "but", "che", "tang", "tra"}


def plain_pattern(word):
    bare = plain(word)
    return None if bare in AMBIGUOUS_PLAIN and bare != norm(word) else word_pattern(bare)


# (mẫu có dấu, mẫu không dấu hoặc None, điểm, mã nhóm); điểm là độ dài cụm, từ chung chung điểm thấp
KEYWORDS = [(word_pattern(norm(k)), plain_pattern(k), 0.5 if norm(k) in GENERIC else len(norm(k)), code)
            for code, (_, words) in CATEGORIES.items() for k in words]


# ---- Nhóm tự chỉnh: người dùng thêm nhóm, thêm từ khóa, đổi tên, ẩn nhóm ngay trong Telegram (/nhom) ----
# Lưu ở khóa chitieu:nhomrieng: {"moi": [mã nhóm tự tạo], "ten": {mã: tên}, "tu": {mã: [từ khóa]},
# "an": [mã nhóm đã ẩn], "dem": số nhóm đã tạo}. Nhóm ẩn vẫn giữ tên để khoản cũ hiện đúng.

_config = None  # đọc một lần mỗi lượt xử lý; reset() ở đầu mỗi tin nhắn, lượt bấm nút, lịch chạy


def reset():
    global _config
    _config = None


def config():
    global _config
    if _config is None:
        if not kho.ready():
            return {}
        _config = kho.get(K_GROUPS, {})
    return _config


def save_config(cfg):
    global _config
    kho.put(K_GROUPS, cfg)
    _config = cfg
    kho.delete(K_AI)  # nhóm đã khác: các câu AI trả lời trước đó không còn đúng danh sách nhóm


def name(code, cfg=None):
    """Tên nhóm kèm biểu tượng ('🍜 Ăn uống'), kể cả nhóm đã ẩn; mã lạ thì là Khác."""
    cfg = config() if cfg is None else cfg
    return cfg.get("ten", {}).get(code) or CATEGORIES.get(code, CATEGORIES[OTHER])[0]


def bare(label):
    """'🍜 Ăn uống' -> 'Ăn uống'."""
    return label.split(" ", 1)[-1]


def groups(cfg=None):
    """Các nhóm đang dùng, theo thứ tự hiện trên nút: mã -> (tên, từ khóa tự thêm, từ khóa có sẵn)."""
    cfg = config() if cfg is None else cfg
    hidden = set(cfg.get("an", []))
    order = [c for c in CATEGORIES if c not in (OTHER, INCOME)] + list(cfg.get("moi", [])) + [OTHER, INCOME]
    return {c: (name(c, cfg), cfg.get("tu", {}).get(c, []), CATEGORIES.get(c, ("", []))[1])
            for c in order if c not in hidden}


def rules(learned=None, cfg=None):
    """Bảng so khớp (mẫu có dấu, mẫu không dấu, điểm, mã): cụm từ đã học > từ khóa tự thêm > có sẵn."""
    active = groups(cfg)
    learned_rules = [(word_pattern(k), word_pattern(plain(k)), 100 + len(k), code)
                     for k, code in (learned or {}).items() if code in active]
    own = [(word_pattern(norm(k)), plain_pattern(k), len(norm(k)) + 0.5, code)  # +0.5: thắng từ có sẵn trùng
           for code, (_, words, _) in active.items() for k in words]
    return learned_rules + own + [r for r in KEYWORDS if r[3] in active]


def pick(note, table):
    """Câu có dấu chỉ so với từ khóa có dấu ("cho Lan" không phải "chợ", "trả" không phải "trà");
    câu gõ không dấu so với từ khóa đã bỏ dấu ("cho be" là "cho bé", thắng "be" gọi xe).
    Nhiều cụm cùng khớp thì lấy cụm điểm cao nhất (dài nhất)."""
    text = norm(note)
    typed_plain = text == plain(text)
    found = [(score, code) for exact, bare_word, score, code in table
             if (bare_word if typed_plain else exact) and (bare_word if typed_plain else exact).search(text)]
    return max(found, key=lambda x: x[0])[1] if found else OTHER


def classify(note, learned=None, cfg=None):
    """Mã nhóm của ghi chú. Cụm từ đã học (người dùng sửa nhóm) thắng từ khóa."""
    return pick(note, rules(learned, cfg))


def find_group(text, include_hidden=False, cfg=None):
    """Tên nhóm người dùng gõ ('ăn uống', 'di lai', 'ăn', 'trả nợ') -> mã, None nếu không có nhóm nào."""
    cfg = config() if cfg is None else cfg
    key = plain(re.sub(r"[^\w\s]", " ", text))
    key = " ".join(key.split())
    if not key:
        return None
    codes = list(groups(cfg)) + ([c for c in CATEGORIES if c in cfg.get("an", [])]
                                 + [c for c in cfg.get("moi", []) if c in cfg.get("an", [])] if include_hidden else [])
    best = None
    for code in codes:
        label = " ".join(plain(re.sub(r"[^\w\s]", " ", bare(name(code, cfg)))).split())
        score = 3 if label == key else 2 if label.startswith(key) else 1 if re.search(
            rf"(?<!\w){re.escape(key)}", label) else 0
        if score and (best is None or score > best[0]):
            best = (score, code)
    return best[1] if best else None


MONEY = re.compile(
    r"(?<![\w.,])(\d+(?:[.,]\d+)*)\s*"                                   # 35 | 35.000 | 1,5
    r"(?:(k|nghìn|nghin|ngàn|ngan|tr|triệu|trieu|củ|cu|tỷ|ty|tỏi)(\d{1,3})?)?"  # đơn vị, phần lẻ: 1tr2, 1k5
    # (phần lẻ chỉ đi sau đơn vị: "tháng 11 19,1tr" là 19,1 triệu, không phải "11 19")
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


TAG = re.compile(r"#\s*([^#\d\n]+)")  # "đóng họ 1tr #tiết kiệm": tự chọn nhóm khi ghi


def read_tag(line):
    """'#nhóm' trong dòng: (mã nhóm, tên nhóm chưa có, dòng đã bỏ phần #nhóm). Tên nhóm có thể nhiều chữ
    ("#tiết kiệm"); #nhóm đứng giữa câu thì lấy cụm chữ dài nhất trùng tên một nhóm, phần sau trả về ghi chú."""
    tag = TAG.search(line)
    words = tag[1].split() if tag else []
    if not words:
        return None, None, line
    before, after = line[:tag.start()], line[tag.end():]
    for n in range(len(words), 0, -1):
        code = find_group(" ".join(words[:n]))
        if code:
            return code, None, " ".join([before, *words[n:], after])
    if not after.strip() and classify(" ".join(words)) != OTHER:  # "#cafe", "#xe": từ khóa của một nhóm
        return classify(" ".join(words)), None, before
    n = len(words) if not after.strip() else 1  # không có nhóm nào: ở cuối dòng thì lấy hết, giữa câu lấy 1 chữ
    return None, " ".join(words[:n]).strip(" .,;:"), " ".join([before, *words[n:], after])


def parse_line(line, day, learned=None):
    """Một dòng tin nhắn -> khoản chi/thu (chưa có id), None nếu không có số tiền."""
    line = line.strip()
    income = line.startswith("+")
    chosen, missing, line = read_tag(line)
    when, text = parse_date(line.lstrip("+").strip(), day)
    found = parse_amount(text)
    if not found:
        return None
    amount, start, end = found
    note = " ".join((text[:start] + " " + text[end:]).split()).strip(" ,.:;-–")
    e = {"ngay": when.isoformat(), "tien": amount, "ghichu": note,
         "nhom": INCOME if income else chosen or classify(note, learned)}
    if missing:
        e["_tag"] = missing  # chưa có nhóm tên này: nhắc tạo nhóm
    if chosen and not income:
        e["_chon"] = True  # người dùng ghi #nhóm: không hỏi AI, nhớ cho lần sau
        if chosen == OTHER:
            e["dekhac"] = True
    return e


# ---- Xếp nhóm bằng AI (tùy chọn) ------------------------------------------------------
# Chỉ hỏi AI những khoản từ khóa không nhận ra (rơi vào Khác); AI cũng hiểu câu hỏi, viết nhận xét.
# Hai nhà cung cấp, cùng kiểu API của OpenAI (chat/completions), có cái nào dùng cái đó:
# - Google Gemini (biến GEMINI_API_KEY), dùng trước: gói miễn phí không giới hạn chung 50 lượt/ngày.
#   Thử ngày 04/11/2026: Gemini 3.5 Flash-Lite xếp đúng 13/13 khoản lạ trong khoảng 1 giây, Flash cũng
#   13/13 (khoảng 8 giây, gói miễn phí 5 lượt/phút). Model trước lỗi, bận, hết lượt thì thử model sau.
# - OpenRouter (biến AI_API_KEY), dự phòng: model miễn phí, cả tài khoản 50 lượt/ngày; AI_MODEL nhiều
#   model cách nhau dấu phẩy thì OpenRouter tự chuyển. AI_API_URL đổi được sang nhà cung cấp khác.
# AI lỗi hết thì khoản vào Khác và bot hỏi người dùng.

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
# 05/11/2026: 3.1 Flash-Lite cũng đúng 13/13, đọc đúng ảnh hóa đơn và lịch sử giao dịch (1–2 giây); nằm ở nhóm máy
# chủ khác nên lúc 3.5 báo quá tải (503) vẫn trả lời được
GEMINI_MODELS = "gemini-3.5-flash-lite,gemini-3.1-flash-lite,gemini-3.5-flash"
AI_URL = "https://openrouter.ai/api/v1/chat/completions"
# Chọn ngày 04/11/2026: thử 13 khoản lạ, Nemotron 3 Ultra đúng 12, Dots 3 đúng 12 (dự phòng).
# Không thêm openrouter/free: nó chọn ngẫu nhiên model miễn phí, có lần chỉ đúng 7/13.
AI_MODELS = "nvidia/nemotron-3-ultra-550b-a55b:free,dots-studio/dots-3-note-preview:free"
AI_TIMEOUT = 25  # giây; model miễn phí có "suy nghĩ" trước khi trả lời nên chậm, quá thì thôi
# Đọc ảnh: model Gemini ở trên đều xem được ảnh; trên OpenRouter phải dùng model riêng (thử 04/11/2026:
# Nemotron 3.5 Super VL đọc đúng số tiền 6/6 ảnh mẫu)
AI_VISION_MODELS = "nvidia/nemotron-3.5-super-vl:free"


def env_list(name, default):
    return [m.strip() for m in os.environ.get(name, default).split(",") if m.strip()]


def gemini_key():
    return os.environ.get("GEMINI_API_KEY", "").strip()


def openrouter_key():
    return os.environ.get("AI_API_KEY", "").strip()


def ai_key():
    """Có AI không (Gemini hoặc OpenRouter)."""
    return gemini_key() or openrouter_key()


def ai_models():
    """Các model OpenRouter (hoặc nhà cung cấp AI_API_URL)."""
    return env_list("AI_MODEL", AI_MODELS)


def ai_providers(vision=False):
    """[(tên, địa chỉ, key, các model)] theo thứ tự thử: Gemini trước, OpenRouter dự phòng.
    vision=True: model xem được ảnh."""
    out = []
    if gemini_key():
        out.append(("Gemini", GEMINI_URL, gemini_key(), env_list("GEMINI_MODEL", GEMINI_MODELS)))
    if openrouter_key():
        url = os.environ.get("AI_API_URL", AI_URL)
        models = env_list("AI_VISION_MODEL", AI_VISION_MODELS) if vision else ai_models()
        out.append(("OpenRouter" if "openrouter.ai" in url else "AI", url, openrouter_key(), models))
    return out


def ai_post(payload, url=None, key=None, timeout=AI_TIMEOUT):
    req = urllib.request.Request(url or os.environ.get("AI_API_URL", AI_URL), data=json.dumps(payload).encode(), headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {key or ai_key()}", "X-Title": "ban-tin-sang"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = (e.read() or b"").decode(errors="replace")
        try:
            message = json.loads(body)["error"]["message"]
        except (ValueError, KeyError, TypeError):
            message = body[:200]
        raise RuntimeError(f"AI báo lỗi {e.code}: {message}") from None


def ai_chat(system, user, max_tokens=2000, image=None, timeout=AI_TIMEOUT, budget=45):
    """Hỏi AI một lượt: (câu trả lời đã bỏ phần "suy nghĩ", model đã trả lời). Thử lần lượt từng nhà cung cấp,
    từng model; tất cả đều lỗi (mạng, bận, hết lượt...) thì báo lỗi. image=(bytes, kiểu ảnh) để gửi kèm ảnh.
    timeout: chờ mỗi model tối đa bao lâu; budget: tổng thời gian cho mọi lần thử (Vercel cắt hàm ở 60 giây)."""
    started = datetime.now()
    if image:
        data, mime = image
        user = [{"type": "text", "text": user}, {"type": "image_url", "image_url": {
            "url": f"data:{mime};base64,{base64.b64encode(data).decode()}"}}]
    errors = []
    for provider, url, key, models in ai_providers(vision=bool(image)):
        # OpenRouter tự chuyển model khi nhận danh sách "models"; nơi khác thì bot tự thử từng model
        tries = [(models[0], {"models": models})] if "openrouter.ai" in url and len(models) > 1 else \
            [(m, {}) for m in models]
        for model, extra in tries:
            left = budget - (datetime.now() - started).total_seconds()
            if left < 5:
                errors.append(f"{provider} {model}: hết thời gian chờ")
                continue
            payload = {
                # Model có "suy nghĩ" tiêu nhiều token trước khi trả lời; ít quá thì câu trả lời bị cắt rỗng
                "model": model, "temperature": 0, "max_tokens": max_tokens, **extra,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
            try:
                res = ai_post(payload, url, key, min(timeout, left))
                text = res["choices"][0]["message"].get("content") or ""
                return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip(), res.get("model", model)
            except Exception as e:
                print(f"[lỗi] AI {provider} {model}: {e!r}", file=sys.stderr)
                errors.append(f"{provider} {model}: {e}")
    raise RuntimeError("; ".join(errors) or "chưa bật AI (thiếu GEMINI_API_KEY hoặc AI_API_KEY)")


def first_json(text):
    """Đối tượng JSON đầu tiên trong câu trả lời của AI (bỏ qua chữ, khối ```json bao quanh)."""
    start = text.find("{")
    try:
        return json.JSONDecoder().raw_decode(text[start:])[0] if start >= 0 else None
    except ValueError:
        return None


def ai_prompt(learned=None):
    """Lời dặn cho AI: các nhóm đang dùng (kể cả nhóm tự tạo) kèm vài từ khóa gợi ý, và những khoản
    người dùng đã tự xếp làm ví dụ để AI đoán theo thói quen của người dùng."""
    active = {c: g for c, g in groups().items() if c != INCOME}
    lines = []
    for code, (label, own, builtin) in active.items():
        hint = ", ".join(list(dict.fromkeys(own + builtin))[:8])
        lines.append(f"{code}: {bare(label)}" + (f" (vd: {hint})" if hint else ""))
    examples = [f"{note} -> {code}" for note, code in list((learned or {}).items())[-30:] if code in active]
    return ("Bạn phân loại khoản chi tiêu cá nhân của người Việt. Các nhóm (mã: tên):\n" + "\n".join(lines)
            + ("\nNgười dùng này đã tự xếp như sau, hãy theo đúng thói quen đó:\n" + "\n".join(examples)
               if examples else "")
            + "\nTrả lời đúng một dòng JSON, khóa là số thứ tự, giá trị là mã nhóm, ví dụ "
            '{"1": "an", "2": "xe"}. Chỉ chọn nhóm khi khá chắc chắn; không chắc thì dùng "khac" '
            "(bot sẽ hỏi người dùng). Không giải thích.")


def ai_request(notes, learned=None):
    """Hỏi AI nhóm của các ghi chú: ({ghi chú: mã}, model đã trả lời). Lỗi mạng, hết lượt... thì báo lỗi."""
    numbered = "\n".join(f"{i}. {note}" for i, note in enumerate(notes, 1))
    text, model = ai_chat(ai_prompt(learned), numbered)
    found = first_json(text)
    if not isinstance(found, dict):
        raise RuntimeError(f"AI trả lời không đúng dạng: {text[:100]!r}")
    answer = {k: str(v).strip().lower() for k, v in found.items()}
    active = groups()
    return {note: answer[str(i)] for i, note in enumerate(notes, 1) if answer.get(str(i)) in active}, model


def ask_ai(entries, learned=None):
    """Khoản rơi vào Khác thì hỏi AI (có nhớ câu trả lời cũ); đánh dấu khoản do AI xếp. Trả về số khoản AI xếp."""
    unknown = [e for e in entries if pending(e) and e["ghichu"] and not e.get("_chon")]
    if not unknown or not ai_key():
        return 0
    cache = kho.get(K_AI, {})
    ask = list(dict.fromkeys(e["ghichu"] for e in unknown if learn_key(e["ghichu"]) not in cache))
    if ask:
        try:
            for note, code in ai_request(ask, learned)[0].items():
                cache[learn_key(note)] = code
            kho.put(K_AI, dict(list(cache.items())[-MAX_LEARNED:]))
        except Exception as e:
            print(f"[lỗi] xếp nhóm bằng AI: {e!r}", file=sys.stderr)
    active, done = groups(), 0
    for e in unknown:
        code = cache.get(learn_key(e["ghichu"]), OTHER)
        if code in active and code not in (OTHER, INCOME):  # khoản thu chỉ nhận khi người dùng tự ghi
            e["nhom"], e["ai"] = code, True
            done += 1
    if done:
        kho.command("HINCRBY", K_AI_STATS, "doan", done)
    return done


def ai_stats():
    """(số khoản AI đã xếp, số khoản người dùng phải sửa lại)."""
    flat = kho.command("HGETALL", K_AI_STATS) or []
    stats = dict(zip(flat[::2], flat[1::2]))
    return int(stats.get("doan", 0)), int(stats.get("sua", 0))


def ai_quota():
    """(đã dùng, giới hạn) lượt gọi model miễn phí hôm nay của key OpenRouter (không tốn lượt);
    None nếu không dùng OpenRouter. Lượt tính lại lúc 0h giờ quốc tế, tức 7h sáng ở Việt Nam."""
    if not openrouter_key() or "openrouter.ai" not in os.environ.get("AI_API_URL", AI_URL):
        return None
    req = urllib.request.Request("https://openrouter.ai/api/v1/key",
                                 headers={"Authorization": f"Bearer {openrouter_key()}"})
    with urllib.request.urlopen(req, timeout=10) as r:
        used = (json.loads(r.read())["data"].get("free_model_daily_requests") or {})
    return (used["used"], used["limit"]) if "used" in used and "limit" in used else None


def quota_text():
    """Lượt OpenRouter: 'đã dùng 12/50 lượt miễn phí hôm nay' hoặc báo hết lượt; rỗng nếu không dùng OpenRouter."""
    try:
        quota = ai_quota()
    except urllib.error.HTTPError as e:
        return "LỖI – key không hợp lệ, kiểm tra biến AI_API_KEY" if e.code == 401 else f"không xem được lượt dùng ({e})"
    except Exception as e:
        return f"không xem được lượt dùng ({e!r})"
    if not quota:
        return ""
    used, limit = quota
    return f"hôm nay đã dùng {used}/{limit} lượt miễn phí" + (
        " – HẾT LƯỢT, 7h sáng mai có lại" if used >= limit else "")


def ai_status(test=False):
    """Một dòng tình trạng AI cho trang cài đặt. test=True thì thử xếp một khoản mẫu (tốn 1 lượt)."""
    if not ai_key():
        return "AI xếp nhóm: tắt (chưa có biến GEMINI_API_KEY hoặc AI_API_KEY)"
    chain = " → ".join(f"{name_} ({', '.join(models)})" for name_, _, _, models in ai_providers())
    if not test:
        quota = quota_text()
        return (f"AI xếp nhóm: bật, thử lần lượt {chain}" + (f". OpenRouter {quota}" if quota else "")
                + ". Thêm ?thu=1 vào địa chỉ trang để thử gọi AI")
    start = datetime.now()
    try:
        got, model = ai_request(["thay má phanh"])
    except Exception as e:
        return f"AI xếp nhóm ({chain}): LỖI – {e}"
    seconds = (datetime.now() - start).total_seconds()
    return (f"AI xếp nhóm: hoạt động ({model}, {seconds:.1f} giây), thử 'thay má phanh' → "
            f"{name(got.get('thay má phanh', OTHER))}")


# ---- Lưu trữ: mỗi tháng một Redis hash, mỗi khoản một mục (id -> JSON) ---------------
# Ghi/sửa/xóa từng mục riêng nên hai tin nhắn tới cùng lúc không đè mất khoản của nhau.

def month_key(ym):
    return f"chitieu:{ym}"


def load(ym):
    flat = kho.command("HGETALL", month_key(ym)) or []  # [id1, json1, id2, json2, ...]
    return sorted((json.loads(v) for v in flat[1::2]), key=lambda e: e["id"])


def save(e):
    kept = {k: v for k, v in e.items() if not k.startswith("_")}  # khóa "_..." chỉ dùng tạm khi trả lời
    kho.command("HSET", month_key(e["ngay"][:7]), e["id"], json.dumps(kept, ensure_ascii=False))


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
    chosen = [(e["ghichu"], e["nhom"]) for e in entries if e.get("_chon") and e["nhom"] != OTHER]
    if chosen:
        learn_all(chosen)
    ask_ai(entries, learned)
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


# Số, ngày tháng trong ghi chú không giúp gì cho việc xếp nhóm: học "tiền đổ rác" thay vì
# "tiền đổ rác tháng 11", để tháng sau ghi "tiền đổ rác tháng 12" bot vẫn nhận ra.
NOISE = re.compile(r"(?<!\w)(?:(?:tháng|thang|quý|quy|năm|kỳ|ky|tuần|tuan|ngày|ngay|lần|đợt|dot|t|q)\s*)?"
                   r"\d+(?:[/.\-]\d+)*(?!\w)")


def learn_key(note):
    key = " ".join(NOISE.sub(" ", norm(note)).split()).strip(" ,.:;-–")
    return key if len(key) >= 2 else norm(note)


def learn_all(pairs):
    """Nhớ nhóm người dùng chọn cho các ghi chú [(ghi chú, mã)]."""
    pairs = [(learn_key(note), code) for note, code in pairs if note]
    if not pairs:
        return
    learned = kho.get(K_LEARN, {})
    for key, code in pairs:
        learned.pop(key, None)
        learned[key] = code
    kho.put(K_LEARN, dict(list(learned.items())[-MAX_LEARNED:]))


def learn(note, code):
    learn_all([(note, code)])


def pending(e):
    """Khoản đang ở Khác mà người dùng chưa chọn để nguyên: bot sẽ hỏi nhóm."""
    return e["nhom"] == OTHER and not e.get("dekhac")


def tidy(day):
    """Xếp lại các khoản đang ở Khác (tháng này và tháng trước) theo từ khóa, cụm từ đã học mới nhất.
    Trả về số khoản đã chuyển nhóm."""
    table = rules(kho.get(K_LEARN, {}))
    prev = (day.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    moved = 0
    for e in load(prev) + load(day.strftime("%Y-%m")):
        if pending(e) and e["ghichu"]:
            code = pick(e["ghichu"], table)
            if code != OTHER:
                e["nhom"] = code
                save(e)
                moved += 1
    return moved


# ---- Hiển thị ---------------------------------------------------------------------

def vnd(x):
    return f"{vn_num(x, 0)}đ"


def entry_text(e, day):
    when = "" if e["ngay"] == day.isoformat() else (
        " · hôm qua" if e["ngay"] == (day - timedelta(days=1)).isoformat() else f" · {e['ngay'][8:]}/{e['ngay'][5:7]}")
    note = html.escape(e["ghichu"]) if e["ghichu"] else "<i>không ghi chú</i>"
    robot = " 🤖" if e.get("ai") else ""  # nhóm do AI đoán
    return f"<b>{vnd(e['tien'])}</b> · {name(e['nhom'])}{robot} — {note}{when}"


def budget_label(code):
    return {"tong": "Tổng chi", "hangngay": "Chi hằng ngày"}.get(code) or name(code)


def budget_lines(codes, day):
    """Tiến độ ngân sách tháng của các nhóm vừa ghi (và ngân sách tổng)."""
    budgets = kho.get(K_BUDGET, {})
    if not budgets:
        return []
    items = [e for e in load(day.strftime("%Y-%m")) if e["nhom"] != INCOME]
    lines = []
    daily = phantich().daily_groups() if "hangngay" in budgets else []
    extra = (["hangngay"] if daily and set(codes) & set(daily + ["hangngay"]) else []) + (["tong"] if "tong" in budgets else [])
    for code in list(dict.fromkeys([c for c in codes if c in budgets and c not in ("tong", "hangngay")] + extra)):
        if code == "hangngay":  # chi tiêu hằng ngày, không tính khoản đột biến
            spent = phantich().daily_spent(day)
        else:
            spent = sum(e["tien"] for e in items if code == "tong" or e["nhom"] == code)
        limit = budgets[code]
        pct = spent / limit * 100
        label = budget_label(code)
        mark = "🚨" if pct >= 100 else "⚠️" if pct >= 80 else "🎯"
        extra = f", vượt {vnd(spent - limit)}" if pct > 100 else ""
        lines.append(f"{mark} {label} tháng {day.month}: {vnd(spent)} / {vnd(limit)} ({pct:.0f}%{extra})")
    return lines


SORT_TITLE = "🗂"  # tin /chuaxep bắt đầu bằng biểu tượng này, vẽ lại vẫn giữ kiểu tin


def entries_message(entries, day, sorting=False, focus=None, extra=()):
    """Tin báo các khoản vừa ghi, kèm nút ✏️ đổi nhóm và ❌ xóa từng khoản. Khoản chưa rõ nhóm (Khác)
    thì hiện luôn nút chọn nhóm, từng khoản một, để ít khoản phải nằm ở Khác. focus: khoản vừa bấm ✏️."""
    if not entries:
        return "🗑 Đã xóa", None
    ask = next((e for e in entries if ref(e) == focus), None) or next((e for e in entries if pending(e)), None)
    notes = [] if sorting else budget_lines([e["nhom"] for e in entries if e["nhom"] != INCOME], day)
    for tag in dict.fromkeys(e["_tag"] for e in entries if e.get("_tag")):
        notes.append(f"⚠️ Chưa có nhóm «{html.escape(tag)}», tạo bằng: /nhom them {html.escape(tag)}")
    what = html.escape((ask["ghichu"] or vnd(ask["tien"])) if ask else "")
    if ask and pending(ask):
        notes.append(f"❓ Chưa rõ nhóm của «{what}»: chọn nhóm bên dưới, lần sau bot tự xếp")
    elif ask:
        notes.append(f"✏️ Chọn nhóm đúng cho «{what}»")
    notes += list(extra)
    if any(e.get("ai") for e in entries):
        notes.append("<i>🤖 nhóm do AI đoán, sai thì bấm ✏️ để sửa, lần sau bot tự nhớ</i>")
    if sorting:
        left = sum(pending(e) for e in entries)
        lines = [f"{SORT_TITLE} <b>{'Còn ' + str(left) + ' khoản chưa rõ nhóm' if left else 'Đã xếp xong'}</b>"]
        lines += [f"{i}. {entry_text(e, day)}" for i, e in enumerate(entries, 1)]
        rows = [[(f"✏️ {i}. {e['ghichu'][:12] or vnd(e['tien'])}", f"doi:{ref(e)}"), (f"❌ {i}", f"xoa:{ref(e)}")]
                for i, e in enumerate(entries, 1)]
    elif len(entries) == 1:
        e = entries[0]
        lines = [f"✅ Đã ghi {entry_text(e, day)}"]
        rows = [[("✏️ Đổi nhóm", f"doi:{ref(e)}"), ("❌ Xóa", f"xoa:{ref(e)}")]]
    else:
        total = sum(e["tien"] for e in entries if e["nhom"] != INCOME)
        lines = [f"✅ Đã ghi {len(entries)} khoản" + (f", chi <b>{vnd(total)}</b>" if total else "")]
        lines += [f"{i}. {entry_text(e, day)}" for i, e in enumerate(entries, 1)]
        rows = [[(f"✏️ {i}. {e['ghichu'][:12] or vnd(e['tien'])}", f"doi:{ref(e)}"), (f"❌ {i}", f"xoa:{ref(e)}")]
                for i, e in enumerate(entries, 1)]
    if ask:
        rows = with_picker(rows, ref(ask), "📦 Để ở Khác" if pending(ask) else "↩️ Thôi")
    return "\n".join(lines + notes), rows


def picker(reference, keep="↩️ Thôi"):
    """Nút chọn nhóm cho một khoản: mọi nhóm đang dùng (kể cả nhóm tự tạo), rồi nút giữ nguyên/xóa."""
    choices = [(label, f"nhom:{reference}:{code}") for code, (label, _, _) in groups().items()]
    rows = [choices[i:i + 2] for i in range(0, len(choices), 2)]
    return rows + [[(keep, f"giu:{reference}"), ("❌ Xóa", f"xoa:{reference}")]]


def with_picker(rows, reference, keep="↩️ Thôi"):
    """Thay hàng nút của một khoản bằng nút chọn nhóm, ngay tại chỗ; nút của khoản khác giữ nguyên."""
    out, done = [], False
    for row in rows:
        if any(button_ref(data) == reference for _, data in row):
            if not done:
                out += picker(reference, keep)
                done = True
        else:
            out.append(row)
    return out if done else picker(reference, keep) + rows


# ---- Báo cáo ------------------------------------------------------------------------

REPORT_BUTTONS = [[("Hôm nay", "bc:ngay"), ("Tuần này", "bc:tuan"), ("Tháng này", "bc:thang"),
                   ("Tháng trước", "bc:thangtruoc")],
                  [("📈 Biểu đồ", "bd:thang"), ("🔮 Dự báo", "db"), ("💬 Nhận xét", "nx:thang")]]
BACK = ("⬅️ Menu", "m:home")  # nút quay về màn hình tổng quan (menu.py)
CHI_BUTTONS = REPORT_BUTTONS + [[("🧾 Lịch sử", "m:ls"), ("🗂 Chưa xếp", "m:cx"), ("🎯 Ngân sách", "m:ns")], [BACK]]


def from_menu(message):
    """Tin này mở từ menu (có nút ⬅️ Menu): vẽ lại thì giữ nút menu."""
    return any(data.startswith("m:") for row in keyboard_rows(message) for _, data in row)


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
        kinds = income_kinds([e for e in items if e["nhom"] == INCOME])
        detail = f" ({' · '.join(f'{k} {vnd(v)}' for k, v in kinds)})" if len(kinds) > 1 else ""
        lines.append(f"💰 Thu: {vnd(income)}{detail} · còn lại <b>{vnd(income - total)}</b>")
    biggest = sorted(spend, key=lambda e: -e["tien"])[:3]
    if biggest and len(spend) > 3:
        lines.append("Khoản lớn nhất: " + " · ".join(
            f"{html.escape(e['ghichu'] or name(e['nhom']))} {vnd(e['tien'])}" for e in biggest))
    unsorted = sum(pending(e) for e in spend)
    if unsorted:
        lines.append(f"❓ {unsorted} khoản chưa rõ nhóm, gõ /chuaxep để xếp")
    status = budget_status(day) if kind == "thang" else []
    if status:
        lines += ["", "<b>Ngân sách</b>"] + status
    return "\n".join(lines), len(spend)


INCOME_KINDS = [("📈 Đầu tư", ["lãi bán", "cổ tức", "lãi tiết kiệm", "tiền lãi", "lãi"]), ("💼 Lương", ["lương"]),
                ("🎁 Thưởng", ["thưởng"]), ("🧑‍💻 Làm thêm", ["làm thêm", "freelance", "hoa hồng", "dự án", "bán hàng",
                                                             "kinh doanh", "cho thuê"])]


def income_kind(note):
    """Loại thu nhập theo ghi chú: lương, thưởng, đầu tư (lãi bán cổ phiếu, cổ tức, lãi tiết kiệm), làm thêm, khác."""
    bare = plain(note or "")
    for label, words in INCOME_KINDS:
        if any(re.search(rf"(?<!\w){re.escape(plain(w))}(?!\w)", bare) for w in words):
            return label
    return "💰 Khác"


def income_kinds(items):
    sums = {}
    for e in items:
        sums[income_kind(e["ghichu"])] = sums.get(income_kind(e["ghichu"]), 0) + e["tien"]
    return sorted(sums.items(), key=lambda x: -x[1])


def budget_status(day):
    """Tiến độ mọi ngân sách đã đặt (từng nhóm và tổng) trong tháng này."""
    return budget_lines([c for c in kho.get(K_BUDGET, {}) if c != "tong"], day)


# ---- Lệnh ---------------------------------------------------------------------------

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
        if gone.get("no"):  # khoản trả nợ: cộng lại dư nợ
            try:
                sono().undo(gone)
            except Exception as e:
                print(f"[lỗi] hoàn dư nợ khi xóa khoản: {e!r}", file=sys.stderr)
    return gone


def xoa_cuoi(args):
    items = recent(today(), 1)
    if not items:
        return "Chưa có khoản nào để xóa"
    gone = delete(ref(items[0]))
    return f"🗑 Đã xóa: {entry_text(gone, today())}"


def find_category(text):
    """Tên nhóm người dùng gõ ('ăn uống', 'di lai', 'tổng') -> mã, None nếu không rõ."""
    if plain(text).strip() in ("tong", "tat ca", "tong chi"):
        return "tong"
    if plain(text).strip() in ("hang ngay", "hangngay", "sinh hoat", "thuong ngay", "chi hang ngay"):
        return "hangngay"
    code = find_group(text) or classify(text)
    return None if code == OTHER else code


def ngansach(args):
    usage = ("Đặt ngân sách tháng: /ngansach ăn uống 3tr · /ngansach tổng 15tr\n"
             "Chi tiêu hằng ngày (ăn uống, đi chợ, đi lại…): /ngansach hằng ngày 9tr\n"
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
        return f"Đã bỏ ngân sách {budget_label(code)}"
    found = parse_amount(args[-1])
    if found is None:
        return usage
    budgets[code] = found[0]
    kho.put(K_BUDGET, budgets)
    label = budget_label(code)
    return "\n".join([f"🎯 Ngân sách {label}: {vnd(found[0])}/tháng"] + budget_lines([code], today()))


NHOM_USAGE = ("<b>Tự chỉnh nhóm</b>\n"
              "• Tạo nhóm: /nhom them 🏦 Trả nợ: trả nợ, trả góp, vay\n"
              "• Thêm từ khóa: /nhom tukhoa Ăn uống: bún chả, bánh tráng\n"
              "• Đổi tên: /nhom doiten Đi lại: 🚗 Xe cộ\n"
              "• Ẩn nhóm không dùng: /nhom xoa Học tập\n"
              "• Chọn nhóm ngay khi ghi: đóng họ 1tr #trả nợ\n"
              "• Xếp các khoản đang ở Khác: /chuaxep")


def split_spec(text):
    """'Ăn uống: bún chả, bánh tráng' -> ('Ăn uống', ['bún chả', 'bánh tráng'])."""
    head, sep, tail = text.partition(":")
    words = [norm(w).strip(" .") for w in re.split(r"[,;\n]", tail)] if sep else []
    return head.strip(), list(dict.fromkeys(w for w in words if 0 < len(w) <= 40))


def make_label(text, old=None):
    """'🏦 Trả nợ' giữ nguyên; 'Trả nợ' thì thêm biểu tượng (của tên cũ nếu đổi tên)."""
    text = " ".join(re.sub(r"[<>&\"]", "", unicodedata.normalize("NFC", text)).split())[:40]  # tên an toàn cho HTML
    m = re.match(r"([^\w\s]+)\s*(\w.*)$", text)
    if m:
        return f"{m[1]} {m[2]}"
    emoji = old.split(" ", 1)[0] if old and " " in old else "🏷️"
    return f"{emoji} {text}" if text else None


def add_words(cfg, code, words):
    """Thêm từ khóa cho một nhóm; từ khóa đó có ở nhóm tự chỉnh khác thì chuyển sang nhóm này,
    cụm từ đã học trùng hẳn từ khóa đó (học từ lần sửa cũ) thì bỏ để từ khóa mới có tác dụng."""
    if words:
        learned = kho.get(K_LEARN, {})
        kept = {k: c for k, c in learned.items() if k not in words or c == code}
        if len(kept) != len(learned):
            kho.put(K_LEARN, kept)
    cfg.setdefault("tu", {})
    for other, own in cfg["tu"].items():
        if other != code:
            own[:] = [w for w in own if w not in words]
    cfg["tu"][code] = list(dict.fromkeys(cfg["tu"].get(code, []) + words))[-MAX_WORDS:]
    cfg["tu"] = {c: w for c, w in cfg["tu"].items() if w}


def after_change(cfg, text):
    save_config(cfg)
    moved = tidy(today())
    return text + (f"\n↪️ Đã xếp lại {moved} khoản đang ở Khác theo nhóm mới" if moved else "")


def nhom_them(rest):
    head, words = split_spec(rest)
    cfg = json.loads(json.dumps(config()))  # bản sao để sửa
    label = make_label(head) if head else None
    code = find_group(head, include_hidden=True, cfg=cfg) if label else None
    if code and plain(bare(name(code, cfg))) != plain(bare(label)):
        code = None  # chỉ khớp một phần tên ("Ăn" với "Ăn uống"): tạo nhóm mới
    if code:
        was_hidden = code in cfg.get("an", [])
        cfg["an"] = [c for c in cfg.get("an", []) if c != code]
        add_words(cfg, code, words)
        text = (f"✅ Đã dùng lại nhóm {name(code, cfg)}" if was_hidden else f"Nhóm {name(code, cfg)} đã có")
        return after_change(cfg, text + (f", thêm từ khóa: {html.escape(', '.join(words))}" if words else ""))
    if not label:
        return NHOM_USAGE
    if len(cfg.get("moi", [])) >= MAX_GROUPS:
        return f"Đã có {MAX_GROUPS} nhóm tự tạo, ẩn bớt nhóm không dùng (/nhom xoa tên nhóm) rồi tạo tiếp"
    cfg["dem"] = cfg.get("dem", 0) + 1
    code = f"r{cfg['dem']}"
    cfg.setdefault("moi", []).append(code)
    cfg.setdefault("ten", {})[code] = label
    add_words(cfg, code, words)
    text = f"✅ Đã tạo nhóm {html.escape(label)}" + (
        f", từ khóa: {html.escape(', '.join(words))}" if words else
        f"\nThêm từ khóa để bot tự xếp: /nhom tukhoa {html.escape(bare(label))}: từ khóa 1, từ khóa 2")
    return after_change(cfg, text)


def nhom_tukhoa(rest):
    head, words = split_spec(rest)
    cfg = json.loads(json.dumps(config()))
    code = find_group(head, cfg=cfg) if head else None
    if not code or not words:
        return "Thêm từ khóa: /nhom tukhoa Ăn uống: bún chả, bánh tráng\n(tên nhóm, dấu hai chấm, các từ khóa cách nhau dấu phẩy)"
    if code == OTHER:
        return "Nhóm Khác dành cho khoản không khớp nhóm nào, không thêm từ khóa được"
    add_words(cfg, code, words)
    return after_change(cfg, f"✅ {name(code, cfg)} thêm từ khóa: {html.escape(', '.join(words))}")


def nhom_doiten(rest):
    head, _, new = rest.partition(":")
    cfg = json.loads(json.dumps(config()))
    code = find_group(head, cfg=cfg) if head.strip() else None
    label = make_label(new, name(code, cfg)) if code and new.strip() else None
    if not label:
        return "Đổi tên: /nhom doiten Đi lại: 🚗 Xe cộ"
    old = name(code, cfg)
    cfg.setdefault("ten", {})[code] = label
    save_config(cfg)
    return f"✅ Đã đổi {html.escape(old)} thành {html.escape(label)}"


def nhom_xoa(rest):
    cfg = json.loads(json.dumps(config()))
    code = find_group(rest, cfg=cfg) if rest.strip() else None
    if not code:
        return "Ẩn nhóm: /nhom xoa Học tập"
    if code in (OTHER, INCOME):
        return "Không ẩn được nhóm Khác và Thu nhập"
    cfg.setdefault("an", []).append(code)
    save_config(cfg)
    return (f"✅ Đã ẩn nhóm {name(code, cfg)}: không còn trên nút chọn, bot không xếp vào nữa. Khoản cũ giữ "
            f"nguyên. Dùng lại: /nhom them {html.escape(bare(name(code, cfg)))}")


def nhom_cmd(args):
    action = plain(args[0]) if args else ""
    rest = " ".join(args[1:])
    for words, handler in [(("them", "tao", "moi"), nhom_them), (("tukhoa", "tu", "tk"), nhom_tukhoa),
                           (("doiten", "ten", "sua"), nhom_doiten), (("xoa",), nhom_xoa)]:
        if action in words:
            return handler(rest)
    learned = kho.get(K_LEARN, {})
    cfg = config()
    lines = ["🗂 <b>Các nhóm và vài từ khóa</b>"]
    for code, (label, own, builtin) in groups().items():
        sample = ", ".join(list(dict.fromkeys(own + builtin))[:6])
        if code == OTHER:
            sample = "những khoản không khớp nhóm nào"
        mine = " (nhóm bạn tạo)" if code in cfg.get("moi", []) else ""
        lines.append(f"{html.escape(label)}{mine}: <i>{html.escape(sample) or 'chưa có từ khóa'}</i>")
    hidden = [name(c) for c in cfg.get("an", [])]
    if hidden:
        lines.append("Đã ẩn: " + html.escape(", ".join(hidden)))
    lines.append(f"\nBot đã học {len(learned)} cụm từ từ những lần bạn tự chọn nhóm.")
    guessed, fixed = ai_stats()
    accuracy = f"; đã đoán {guessed} khoản, bạn sửa {fixed}" + (
        f" (đúng {100 - fixed / guessed * 100:.0f}%)" if guessed else "") if guessed or fixed else ""
    quota = quota_text() if ai_key() else ""
    lines.append(f"🤖 AI xếp nhóm cho khoản lạ: {'bật' if ai_key() else 'tắt'}{accuracy}"
                 + (f"\n🤖 AI {html.escape(quota)}" if quota else ""))
    return "\n".join(lines + ["", NHOM_USAGE])


def chuaxep(args):
    """Các khoản đang ở Khác: xếp lại theo từ khóa, hỏi lại AI, còn lại thì hiện nút chọn từng khoản."""
    day = today()
    tidy(day)
    items = [e for e in recent(day, 1000) if pending(e)][:8]
    if not items:
        return "✅ Không còn khoản nào chưa rõ nhóm. Khoản mới chưa rõ nhóm thì bot hỏi ngay khi ghi."
    if ask_ai(items, kho.get(K_LEARN, {})):
        for e in items:
            if e.get("ai"):
                save(e)
    return entries_message(items, day, sorting=True)


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
                         "Thu" if e["nhom"] == INCOME else "Chi", bare(name(e["nhom"])), e["ghichu"]])
    # BOM để Excel nhận đúng tiếng Việt
    return {"file": ("\ufeff" + buf.getvalue()).encode("utf-8"), "name": f"chitieu-{year}-{month:02d}.csv",
            "caption": f"Chi tiêu tháng {month}/{year}: {len(items)} khoản"}


def taisan():
    import taisan as module  # tài sản, mua bán cổ phiếu, khám sức khỏe tài chính
    return module


def duphong():
    import duphong as module  # quỹ dự phòng
    return module


def phantich():
    import phantich as module  # nạp khi cần: phantich.py cũng dùng các hàm trong file này
    return module


def sono():
    import sono as module  # sổ nợ
    return module


def kehoach():
    import kehoach as module  # lộ trình tài chính, chia lương
    return module


def menu():
    import menu as module  # menu nút bấm, tổng quan, hướng dẫn
    return module


def dautu():
    import dautu as module  # đầu tư quỹ mở hằng tháng (Value Averaging)
    return module


def tietkiem():
    import tietkiem as module  # tiết kiệm từ khi dùng bot, chuỗi ngày ghi chép
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
    "menu": ("Tổng quan và menu nút bấm", lambda args: menu().menu_cmd(args)),
    "start": ("Bắt đầu", lambda args: menu().start(args)),
    "huongdan": ("Cách dùng và mọi lệnh", lambda args: menu().guide(args)),
    "no": ("Sổ nợ: còn bao nhiêu, mỗi tháng trả, nhắc trả", lambda args: sono().no_cmd(args)),
    "kehoach": ("Lộ trình xây tài sản, chia lương mỗi tháng", lambda args: kehoach().kehoach(args)),
    "dautu": ("Đầu tư quỹ mở hằng tháng: tháng này nên mua bao nhiêu", lambda args: dautu().dautu(args)),
    "tietkiem": ("Tiết kiệm từ khi dùng bot, chuỗi ngày ghi chép", lambda args: tietkiem().tietkiem(args)),
}
COMMANDS["help"] = COMMANDS["huongdan"]
# Danh sách lệnh hiện ở nút Menu của Telegram: chỉ các lệnh chính, lệnh khác vẫn gõ được (/huongdan)
VISIBLE = ["menu", "baocao", "tietkiem", "no", "kehoach", "dautu", "taisan", "duphong", "hoi", "huongdan"]
MENU = [{"command": n, "description": COMMANDS[n][0]} for n in VISIBLE]


def answer(text, now, chat=None):
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
        extra += tietkiem().after_record(entries, now.date())  # chuỗi ngày ghi, hôm nay so với mốc, đã bớt
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
            kho.command("HINCRBY", K_AI_STATS, "sua", 1)  # AI đoán sai
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
