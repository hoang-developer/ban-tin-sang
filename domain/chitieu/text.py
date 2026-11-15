"""Chữ số tiền gọn của sổ chi tiêu (khác taisan.short ở chỗ dưới 1.000đ hiện đủ số và có dấu − cho số âm)."""


def short(x):
    """Số tiền gọn: 1.250.000 -> '1,25tr', 35.000 -> '35k' (âm thì có dấu −)."""
    sign, x = ("−" if x < 0 else ""), abs(x)
    if x >= 999_500:
        return sign + f"{x / 1e6:.2f}".rstrip("0").rstrip(".").replace(".", ",") + "tr"
    return sign + (f"{round(x / 1000)}k" if x >= 1000 else f"{round(x)}đ")
