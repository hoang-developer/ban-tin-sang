"""Quy tắc thuần của tài sản: lãi tiết kiệm, tài khoản chính, tên trùng nhau."""
from datetime import date

from domain.chitieu.kinds import INCOME
from domain.common.dates import add_months
from domain.common.text import plain


def accrued(it, day):
    """(lãi tới hôm nay hoặc tới ngày đáo hạn, ngày đáo hạn hoặc None nếu không kỳ hạn) của sổ tiết kiệm."""
    start = date.fromisoformat(it["ngay"])
    maturity = add_months(start, it["ky"]) if it.get("ky") else None
    end = min(day, maturity) if maturity else day
    return it["tien"] * it["lai"] / 100 * max((end - start).days, 0) / 365, maturity


def can_be_main(it):
    """Tài khoản tiền thường (không phải quỹ dự phòng, quỹ chờ đầu tư, tài khoản chứng khoán)."""
    return it["loai"] == "tien" and not it.get("duphong") and not it.get("dautu") and "dnse" not in plain(it["ten"])


def same_name(a, b):
    return plain(a).strip() == plain(b).strip()


def main_flows(it, day, entries):
    """(thu, chi) ghi sổ từ lúc chốt số dư tài khoản chính. entries: các khoản từ ngày chốt tới day."""
    income = spend = 0
    for e in entries:
        if e["id"] <= it.get("moc", 0) or e.get("khong_tk"):
            continue
        if e["nhom"] == INCOME:
            income += e["tien"]
        else:
            spend += e["tien"]
    return income, spend


def main_balance(it, income, spend):
    return it["tien"] + income - spend + sum(x["tien"] for x in it.get("chuyen", []))
