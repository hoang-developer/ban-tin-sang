"""Quy tắc thuần của tài sản: lãi tiết kiệm, tài khoản chính, tên trùng nhau."""
from datetime import date

from domain.chitieu.kinds import INCOME
from domain.common.dates import add_months
from domain.common.money import number, parse_amount
from domain.common.text import plain


def accrued(it, day):
    """(lãi tới hôm nay hoặc tới ngày đáo hạn, ngày đáo hạn hoặc None nếu không kỳ hạn) của sổ tiết kiệm."""
    start = date.fromisoformat(it["ngay"])
    maturity = add_months(start, it["ky"]) if it.get("ky") else None
    end = min(day, maturity) if maturity else day
    return it["tien"] * it["lai"] / 100 * max((end - start).days, 0) / 365, maturity


DEMAND_RATE = 0.5  # %/năm: lãi không kỳ hạn mặc định khi tất toán sổ có kỳ hạn trước hạn (sổ có `lai_kkh` thì dùng số đó)


def payout(it, day):
    """(tiền nhận về nếu tất toán hôm nay, phần lãi, rút trước hạn?, ngày đáo hạn hoặc None) của sổ tiết kiệm. Sổ có kỳ hạn
    mà chưa tới hạn thì chỉ được lãi không kỳ hạn (lỗi cũ: bot cộng đủ lãi có kỳ hạn, vài triệu không có thật vào thu nhập
    và tài khoản chính). Tới hạn hoặc sổ không kỳ hạn thì lãi như `accrued`."""
    start = date.fromisoformat(it["ngay"])
    maturity = add_months(start, it["ky"]) if it.get("ky") else None
    if maturity and day < maturity:
        interest = it["tien"] * it.get("lai_kkh", DEMAND_RATE) / 100 * max((day - start).days, 0) / 365
        return it["tien"] + interest, interest, True, maturity
    interest, _ = accrued(it, day)
    return it["tien"] + interest, interest, False, maturity


def renewed(it, day):
    """Sổ sau khi tái tục từ ngày đáo hạn: gốc mới = gốc + lãi tới hạn, cùng kỳ hạn và lãi suất, tính từ ngày đáo hạn."""
    interest, maturity = accrued(it, day)
    return {**it, "tien": round(it["tien"] + interest), "ngay": maturity.isoformat()}


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


def stock_price(text):
    """Giá cổ phiếu/ccq: '95' hay '95k' là 95.000đ, '95500' là 95.500đ."""
    text = text.lower().rstrip("kđ")
    value = number(text)
    return value * 1000 if value < 1000 else value


def is_etf(code):
    """Mã chứng chỉ quỹ ETF trên HOSE: E1VFVN30 (DCVFMVN30 của Dragon Capital), FUEVFVND, FUESSVFL..."""
    return code.upper().startswith(("E1VF", "FUE"))


def money_and_name(args):
    """'VCB 25tr' -> ('VCB', 25000000); None nếu không có số tiền."""
    text = " ".join(args)
    found = parse_amount(text)
    if not found:
        return None
    amount, start, end = found
    name = " ".join((text[:start] + " " + text[end:]).split()).strip(" ,.:-") or "Chưa đặt tên"
    return name[:30], amount
