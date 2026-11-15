"""Chữ hiển thị số tiền/số ccq trong /dautu."""
from domain.common.format import short, vn_num


def money(x):
    return short(x) if abs(x) >= 1000 else "0đ"


def units_text(x):
    return vn_num(x, 2).rstrip("0").rstrip(",") if x % 1 else vn_num(x, 0)
