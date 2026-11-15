"""Kỳ báo cáo: hôm nay, tuần này, tháng này, tháng trước, tháng bất kỳ, kèm kỳ trước để so sánh."""
from calendar import monthrange
from datetime import date, timedelta


def period(kind, day):
    """(từ ngày, tới ngày, tên kỳ, từ ngày kỳ trước, tới ngày kỳ trước, tên kỳ trước)."""
    first = day.replace(day=1)
    if kind == "ngay":
        y = day - timedelta(days=1)
        return day, day, "hôm nay", y, y, "hôm qua"
    if kind == "tuan":
        start = day - timedelta(days=day.weekday())
        return start, day, "tuần này", start - timedelta(days=7), day - timedelta(days=7), "tuần trước, cùng số ngày"
    if kind == "thang":
        prev_first = (first - timedelta(days=1)).replace(day=1)
        prev_end = min(prev_first + timedelta(days=day.day - 1), first - timedelta(days=1))
        return first, day, f"tháng {day.month}/{day.year}", prev_first, prev_end, "cùng kỳ tháng trước"
    if kind == "thangtruoc":
        end = first - timedelta(days=1)
        return full_month(end.year, end.month, day)
    month = int(kind)  # /thang 10
    year = day.year if month <= day.month else day.year - 1
    return full_month(year, month, day)


def full_month(year, month, day):
    start = date(year, month, 1)
    end = min(date(year, month, monthrange(year, month)[1]), day)
    prev_end = start - timedelta(days=1)
    return (start, end, f"tháng {month}/{year}", prev_end.replace(day=1), prev_end,
            f"tháng {prev_end.month}/{prev_end.year}")
