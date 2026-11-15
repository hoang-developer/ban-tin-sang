"""Tìm tin theo từ khóa: hiểu cửa sổ thời gian, lọc và sắp xếp kết quả (tính thuần)."""
import re
from datetime import datetime, timezone

from domain.canhbao.rules import normalize

RESULTS = 8                                       # số tin mỗi lần tìm
DEFAULT_HOURS = 7 * 24                            # mặc định tìm trong 7 ngày qua
SKIP_SOURCES = {"facebook", "youtube", "tiktok"}  # mạng xã hội, không phải báo
WINDOW = re.compile(r"(\d{1,3})(h|giờ|gio|d|ngày|ngay|tuần|tuan)")
UNIT_HOURS = {"h": 1, "giờ": 1, "gio": 1, "d": 24, "ngày": 24, "ngay": 24, "tuần": 168, "tuan": 168}


def parse_query(args):
    """['giá', 'vàng', '24h'] -> ('giá vàng', 24): từ khóa và số giờ tìm ngược lại (tối đa 30 ngày)."""
    hours = DEFAULT_HOURS
    if args and (m := WINDOW.fullmatch(args[-1].lower())):
        hours = int(m[1]) * UNIT_HOURS[m[2]]
        args = args[:-1]
    return " ".join(args).strip(), max(1, min(hours, 30 * 24))


def by_hours(hours):
    return hours <= 24 or hours % 24  # 24h, 36h ghi theo giờ; 48h, 7 ngày ghi theo ngày


def window_label(hours):
    return f"{hours} giờ qua" if by_hours(hours) else f"{hours // 24} ngày qua"


def ago(published, now):
    minutes = int((now - published).total_seconds() // 60)
    if minutes < 60:
        return f"{max(minutes, 1)} phút trước"
    if minutes < 24 * 60:
        return f"{minutes // 60} giờ trước"
    return f"{minutes // (24 * 60)} ngày trước"


def newest_first(items):
    oldest = datetime.min.replace(tzinfo=timezone.utc)
    return sorted(items, key=lambda x: x[3] or oldest, reverse=True)


def google_query(keyword, hours):
    """Truy vấn Google News: đúng cụm từ, trong cửa sổ `hours`."""
    phrase = keyword if '"' in keyword else f'"{keyword}"'  # tìm đúng cụm từ
    when = f"when:{hours}h" if by_hours(hours) else f"when:{hours // 24}d"
    return f"{phrase} {when}"


def clean_google(raw):
    """Bỏ mạng xã hội, bỏ tên báo ở cuối tiêu đề, bỏ tin trùng; đưa tin mới nhất lên trước.

    raw: [(tiêu đề, link, tên báo, giờ đăng)]; Google xếp theo độ liên quan nên chỉ lấy 40 tin đầu.
    """
    seen, found = set(), []
    for title, link, source, published in raw[:40]:
        if normalize(source) in SKIP_SOURCES:
            continue
        if source and title.endswith(f" - {source}"):
            title = title[:-len(source) - 3]
        if normalize(title) in seen:  # nhiều báo đăng lại cùng một tin
            continue
        seen.add(normalize(title))
        found.append((title, link, source, published))
    return newest_first(found)[:RESULTS]
