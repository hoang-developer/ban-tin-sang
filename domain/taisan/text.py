"""Chữ hiển thị số lượng, số tiền, tên loại vàng trong tài sản."""
from domain.common.format import short as short_vnd, vn_num, vnd


def qty_text(x):
    """1000 -> '1.000'; 0.05 -> '0,05'; 1234.5 -> '1.234,5'."""
    x = float(x)
    if x.is_integer():
        return vn_num(x, 0)
    whole, frac = vn_num(x, 6).split(",")
    return f"{whole},{frac.rstrip('0')}"


def gold_amount(taels):
    chi = round(taels * 10, 2)  # 0,02 lượng = 0,2 chỉ (vàng ép vỉ 0,1 chỉ)
    whole = int(chi // 10)
    rest = round(chi - whole * 10, 2)
    rest_text = f"{rest:g}".replace(".", ",")
    return " ".join(([f"{whole} lượng"] if whole else []) + ([f"{rest_text} chỉ"] if rest else [])) or "0 chỉ"


def gold_name(kind):
    return "Miếng SJC" if kind == "sjc" else "Nhẫn"


def short(x):
    return ("−" if x < 0 else "") + short_vnd(abs(x))


def gain_line(gain, cost):
    return (f"{'🟢 lãi' if gain >= 0 else '🔴 lỗ'} {vnd(round(abs(gain)))}"
            + (f" ({gain / cost * 100:+.1f}%)".replace(".", ",").replace("-", "−") if cost else ""))
