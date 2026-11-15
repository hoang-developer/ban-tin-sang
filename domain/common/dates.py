"""Tính ngày dùng chung."""
from calendar import monthrange
from datetime import date, timedelta, timezone

VN_TZ = timezone(timedelta(hours=7))  # Việt Nam không đổi giờ mùa hè


def add_months(d, months):
    """Ngày d cộng months tháng; ngày vượt cuối tháng thì lấy ngày cuối tháng (31/01 + 1 tháng = 28/02)."""
    m = d.month - 1 + months
    year, month = d.year + m // 12, m % 12 + 1
    return date(year, month, min(d.day, monthrange(year, month)[1]))


WEEKDAYS = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]
