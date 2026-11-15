"""Đọc tin mua/bán cổ phiếu: "mua 1000 FPT giá 95", "bán 500 FPT giá 120"."""
import re

from domain.common.money import number
from domain.common.text import plain
from domain.taisan.rules import stock_price

SELL_TAX = 0.001  # thuế thu nhập cá nhân khi bán chứng khoán: 0,1% giá trị bán
BROKER_FEE = 0.0  # DNSE miễn phí giao dịch; công ty khác thường thu 0,1–0,35% mỗi chiều
TRADE = re.compile(r"^\s*(mua|ban)\s+(\d[\d.,]*)\s*(?:cp|ccq|co phieu|cổ phiếu|chung chi quy)?\s+([A-Za-z0-9]{3,8})\s*"
                   r"(?:gia|giá|@)?\s*"
                   r"(\d[\d.,]*)\s*(k|nghin|nghìn|đ|d|dong|đồng)?\s*$", re.IGNORECASE)


def parse_trade(text):
    """'bán 500 FPT giá 120' -> ("ban", 500, "FPT", 120000); None nếu không phải lệnh mua bán cổ phiếu."""
    if "\n" in text.strip():
        return None
    m = TRADE.match(plain(text))
    if not m:
        return None
    try:
        qty, price = number(m[2]), stock_price(m[4])
    except ValueError:
        return None
    raw_code = re.search(rf"(?i)(?<![\w]){m[3]}(?![\w])", text)
    code = m[3].upper()
    looks_like_stock = (raw_code and raw_code[0].isupper()) or re.search(r"(?i)\b(gia|giá|cp|cổ phiếu|co phieu)\b", text)
    if not looks_like_stock or qty <= 0 or not qty.is_integer():
        return None
    return m[1].lower(), int(qty), code, price
