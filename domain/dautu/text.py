"""Chữ hiển thị số tiền/số ccq trong /dautu."""
from domain.common.format import short, vn_num


def money(x):
    return short(x) if abs(x) >= 1000 else "0đ"


def units_text(x):
    return vn_num(x, 2).rstrip("0").rstrip(",") if x % 1 else vn_num(x, 0)


def pct(x):
    return "0,0%" if abs(x) < 0.0005 else f"{x * 100:+.1f}%".replace(".", ",")


def arrow(x):
    """+1,2% -> '🔺1,2%', −0,8% -> '🔻0,8%'."""
    return "0,0%" if abs(x) < 0.0005 else f"{'🔺' if x > 0 else '🔻'}{abs(x) * 100:.1f}%".replace(".", ",")


def gain_text(gain, cost):
    """'🟢 +22k (+0,6%)', '🔴 −22k (−0,6%)' hoặc '⚪ hòa vốn' (chênh dưới 1.000đ)."""
    if abs(gain) < 1000:
        return "⚪ hòa vốn"
    sign = "+" if gain > 0 else "−"
    return f"{'🟢' if gain > 0 else '🔴'} {sign}{money(abs(gain))}" + (f" ({pct(gain / cost).replace('-', '−')})"
                                                                     if cost else "")
