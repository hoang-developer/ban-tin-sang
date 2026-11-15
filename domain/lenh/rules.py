"""Lệnh của bot bản tin: giới hạn, mẫu nhận số tiền và thời gian, đơn vị vàng, đổi tiền ra chữ gọn (tính thuần)."""
import re

from domain.common.format import vn_num
MAX_WATCH = 10            # số mã theo dõi tối đa
MAX_KEYWORDS = 20         # số từ khóa báo tin mới tối đa
MAX_REMINDERS = 30        # số ngày cần nhớ tối đa
SAVINGS_RATE = 0.05       # lãi gửi tiết kiệm/năm để so sánh trong /neu
GUESS_DEADLINE = (9, 15)  # nhận đoán xanh/đỏ tới giờ này (hết đợt khớp lệnh mở cửa)
DATE = re.compile(r"(\d{1,2})/(\d{1,2})")
LUNAR_WORDS = {"âm", "am", "al", "âl"}
AMOUNT = re.compile(r"(\d+(?:[.,]\d+)?)(tr|triệu|trieu|k|ty|tỷ|tỉ|ti)?")
PERIOD = re.compile(r"(\d+)(nam|năm|thang|tháng|tuan|tuần|ngay|ngày)")
UNIT_MONEY = {None: 1, "k": 1e3, "tr": 1e6, "triệu": 1e6, "trieu": 1e6, "ty": 1e9, "tỷ": 1e9, "tỉ": 1e9, "ti": 1e9}
UNIT_DAYS = {"nam": 365, "năm": 365, "thang": 30, "tháng": 30, "tuan": 7, "tuần": 7, "ngay": 1, "ngày": 1}
INDEX_NAMES = {"VNINDEX": "VN-Index", "VN30": "VN30", "HNX": "HNX", "UPCOM": "UPCoM"}
KINDS = {"sjc": "sjc", "mieng": "sjc", "miếng": "sjc", "nhan": "nhan", "nhẫn": "nhan"}
UNITS = {"chi": 0.1, "chỉ": 0.1, "luong": 1, "lượng": 1, "cay": 1, "cây": 1}


def rows_of(buttons, size=3):
    return [buttons[i:i + size] for i in range(0, len(buttons), size)]


def parse_level(text):
    return None if text == "-" else float(text.replace(",", "."))


def when_text(r):
    return f"{r['ngay']}/{r['thang']}{' âm lịch' if r['am'] else ''}"


def money(vnd):
    for unit, name in [(1e9, "tỷ"), (1e6, "triệu")]:
        if abs(vnd) >= unit:
            x = vnd / unit
            return f"{vn_num(x, 0 if abs(x - round(x)) < 0.005 else 2)} {name}"  # số tròn thì bỏ ",00"
    return f"{vn_num(vnd, 0)}đ"


def amount_text(taels):
    chi = round(taels * 10, 2)  # 0,02 lượng = 0,2 chỉ (vàng ép vỉ 0,1 chỉ)
    whole = int(chi // 10)
    rest = round(chi - whole * 10, 2)
    rest_text = f"{rest:g}".replace(".", ",")
    return " ".join(([f"{whole} lượng"] if whole else []) + ([f"{rest_text} chỉ"] if rest else [])) or "0 chỉ"
