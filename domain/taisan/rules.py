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


def find_item(data, name, kinds):
    """Mục tài sản theo tên/mã (trùng, không thì chứa nhau), trong các loại kinds; None nếu không thấy hoặc nhiều."""
    key = plain(name or "").strip()
    pool = [it for it in data["items"] if it["loai"] in kinds]
    if not key:
        return pool[0] if len(pool) == 1 else None
    label = lambda it: plain(it.get("ten") or it.get("ma") or "")
    exact = [it for it in pool if label(it).strip() == key]
    near = exact or [it for it in pool if key in label(it) or label(it).strip() in key]
    return near[0] if len(near) == 1 else None


def removable(data, name):
    """Mục tài sản có thể xóa theo tên/mã (mọi loại trừ nợ, nợ xóa ở sổ nợ)."""
    return find_item(data, name, ("tien", "tietkiem", "khac", "cp", "etf", "quy", "coin", "ngoaite"))
