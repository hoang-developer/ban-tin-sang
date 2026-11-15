"""Đầu tư quỹ mở: tháng ('YYYY-MM'), phiên giao dịch và giờ đóng sổ lệnh. Luật thuần.

Hạn đặt lệnh: trước 14:40 ngày làm việc liền trước phiên khớp (chưa tính ngày lễ khi không có lịch NAV thật).
"""
import re
from datetime import date, datetime, timedelta

from domain.common.dates import VN_TZ

CLOSING_HOUR, CLOSING_MINUTE = 14, 40


def ym_of(d):
    return f"{d.year}-{d.month:02d}"


def ym_add(ym, n):
    y, m = map(int, ym.split("-"))
    m += n - 1
    return f"{y + m // 12}-{m % 12 + 1:02d}"


def ym_text(ym):
    return f"{int(ym[5:])}/{ym[:4]}"


def months(start, end):
    """Các tháng từ start tới end (cả hai đầu), dạng 'YYYY-MM'."""
    out, ym = [], start
    while ym <= end:
        out.append(ym)
        ym = ym_add(ym, 1)
    return out


def weekdays_after(d, n):
    while n:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def cutoff_day(trading):
    """Ngày đóng sổ của phiên `trading`: ngày giao dịch liền trước (thứ Hai–thứ Sáu, chưa tính ngày lễ)."""
    d = trading - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def next_trading_from(navs, d, include=False):
    """Ngày giao dịch đầu tiên sau d (include: tính cả d). Theo lịch NAV thật nếu có (bỏ ngày lễ), không thì theo các thứ
    quỹ có NAV gần đây (không có NAV: thứ Hai–thứ Sáu). navs: [(ngày, NAV)]."""
    known = [x for x, _ in navs if (x >= d if include else x > d)]
    if known:
        return known[0]
    days = {x.weekday() for x, _ in navs[-20:]} if len(navs) >= 5 else {0, 1, 2, 3, 4}
    x = d if include else d + timedelta(days=1)
    while x.weekday() not in days:
        x += timedelta(days=1)
    return x


def parse_session(phien):
    """(ngày khớp, lúc đóng sổ) từ phiên Fmarket {"tradingTimeString", "closedOrderBookTimeString"};
    KeyError, TypeError hoặc ValueError nếu thiếu hay sai dạng."""
    trading = datetime.strptime(phien["tradingTimeString"], "%d/%m/%Y").date()
    closing = datetime.strptime(phien["closedOrderBookTimeString"], "%H:%M %d/%m/%Y").replace(tzinfo=VN_TZ)
    return trading, closing


def earliest_order_day(now):
    """Ngày đóng sổ sớm nhất còn kịp: hôm nay trước 14:40, cuối tuần hoặc sau 14:40 thì ngày làm việc kế tiếp."""
    day = now.date()
    if day.weekday() >= 5 or (now.hour, now.minute) >= (CLOSING_HOUR, CLOSING_MINUTE):
        day = weekdays_after(day, 1)
    return day


def guessed_session(trading):
    """Phiên tự đoán khi không có dữ liệu Fmarket: đóng sổ 14:40 ngày làm việc trước phiên."""
    close = cutoff_day(trading)
    return {"phien": trading, "dong": datetime(close.year, close.month, close.day, CLOSING_HOUR, CLOSING_MINUTE, tzinfo=VN_TZ),
            "du_phong": True}


DATE = re.compile(r"(?<![\d/])(\d{1,2})/(\d{1,2})(?:/(\d{4}))?(?![\d/])")


def read_date(text, day):
    """'9/11' -> ngày (năm nay; xa hơn 6 tháng tới thì là năm trước); None nếu không có ngày."""
    m = DATE.search(text)
    if not m:
        return None
    try:
        d = date(int(m[3] or day.year), int(m[2]), int(m[1]))
    except ValueError:
        return None
    if not m[3] and (d - day).days > 180:
        d = d.replace(year=d.year - 1)
    return d
