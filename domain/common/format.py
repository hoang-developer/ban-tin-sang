"""Định dạng số kiểu Việt Nam, dùng chung mọi lớp."""


def vn_num(x, decimals=2, sign=False):
    """1766.65 -> '1.766,65' (kiểu số Việt Nam)."""
    s = f"{x:{'+' if sign else ''},.{decimals}f}"
    return s.replace(",", "_").replace(".", ",").replace("_", ".")


def short(x):
    """Số tiền gọn: 1.250.000 -> '1,25tr', 35.000 -> '35k'."""
    if abs(x) >= 999_500:  # 999.800đ làm tròn thành 1tr, không thành "1000k"
        return f"{x / 1e6:.2f}".rstrip("0").rstrip(".").replace(".", ",") + "tr"
    return f"{round(x / 1000)}k"


def vnd(x):
    return f"{vn_num(x, 0)}đ"
