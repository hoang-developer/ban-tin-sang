"""Đọc số tiền trong câu nhắn: 35k, 1tr2, 1tr287k, 35.000đ, "2 củ"... Phân biệt tiền và số lượng (0,1 chỉ, 6 tháng, 5%)."""
import re

MONEY = re.compile(
    r"(?<![\w.,])(\d+(?:[.,]\d+)*)\s*"                                   # 35 | 35.000 | 1,5
    r"(?:(k|nghìn|nghin|ngàn|ngan|tr|triệu|trieu|củ|cu|tỷ|ty|tỏi)(\d{1,3})?(k|nghìn|nghin|ngàn|ngan)?)?"
    # đơn vị, phần lẻ: 1tr2, 1k5, 1tr287k (= 1.287.000). Phần lẻ chỉ đi sau đơn vị: "tháng 11 19,1tr" là 19,1 triệu
    r"\s*(đ|đồng|dong|vnđ|vnd)?(?!\w)", re.IGNORECASE)
# Số trơn đứng trước các chữ này là số lượng, không phải tiền: "0.1 chỉ", "2 vỉ", "6 tháng", "5%", "100 cp"
QUANTITY = re.compile(r"\s*(?:%|chỉ|chi|lượng|luong|cây|cay|vỉ|ccq|cp|cổ phiếu|co phieu|tháng|thang|năm|nam|ngày|ngay|"
                      r"tuần|tuan|lần|lan|cái|cai|kg|gram|gr|người|nguoi|ly|cốc|coc|hộp|hop|chai|gói|goi)(?!\w)",
                      re.IGNORECASE)
UNITS = {"k": 1e3, "nghìn": 1e3, "nghin": 1e3, "ngàn": 1e3, "ngan": 1e3, "tr": 1e6, "triệu": 1e6, "trieu": 1e6,
         "củ": 1e6, "cu": 1e6, "tỷ": 1e9, "ty": 1e9, "tỏi": 1e9}

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
    if unit and match[3] and match[4]:  # 1tr287k: phần lẻ có đơn vị riêng
        number = number * unit + int(match[3]) * UNITS[match[4].lower()]
    elif unit:
        number = number * unit + (int(match[3]) / 10 ** len(match[3]) * unit if match[3] else 0)
    elif not match[5] and QUANTITY.match(match.string, match.end()):
        return None, False  # số lượng (0.1 chỉ, 6 tháng, 5%), không phải tiền
    elif not match[5] and number < 1000:
        number *= 1000  # "cà phê 35" hiểu là 35 nghìn
    return round(number), bool(unit or match[5])


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


def money_count(text):
    """Số khoản tiền có ghi đơn vị (35k, 1tr, 35.000đ) trong câu: từ 2 trở lên thường là câu nhiều việc."""
    return sum(1 for m in MONEY.finditer(text) if money(m)[0] and money(m)[1])
