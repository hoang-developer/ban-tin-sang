"""Tìm tin tức theo từ khóa cho bot: /tin giá vàng, /tin giá vàng 24h.

Xem thử: python tintuc.py giá vàng 24h
"""
import html
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from bantin import fetch
from bantin import news as headlines
from canhbao import KEYWORD_FEEDS, normalize
from chungkhoan import google_news, published_at

# ---- Cấu hình -------------------------------------------------------------
RESULTS = 8                                       # số tin mỗi lần tìm
DEFAULT_HOURS = 7 * 24                            # mặc định tìm trong 7 ngày qua
SKIP_SOURCES = {"facebook", "youtube", "tiktok"}  # mạng xã hội, không phải báo
# ---------------------------------------------------------------------------

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


def search(keyword, hours):
    """Tin mới nhất về từ khóa trên Google News: [(tiêu đề, link, tên báo, giờ đăng)]."""
    phrase = keyword if '"' in keyword else f'"{keyword}"'  # tìm đúng cụm từ
    when = f"when:{hours}h" if by_hours(hours) else f"when:{hours // 24}d"
    seen, found = set(), []
    for title, link, source, published in google_news(f"{phrase} {when}")[:40]:
        if normalize(source) in SKIP_SOURCES:
            continue
        if source and title.endswith(f" - {source}"):
            title = title[:-len(source) - 3]
        if normalize(title) in seen:  # nhiều báo đăng lại cùng một tin
            continue
        seen.add(normalize(title))
        found.append((title, link, source, published))
    # Google xếp theo độ liên quan; lấy 40 tin đầu rồi đưa tin mới nhất lên trước
    return newest_first(found)[:RESULTS]


def search_feeds(keyword):
    """Dự phòng khi Google News lỗi: tìm trong tiêu đề RSS các báo của canhbao.py."""
    word = normalize(keyword.strip('"'))
    found = []
    for source, url in KEYWORD_FEEDS:
        try:
            items = ET.fromstring(fetch(url)).findall(".//item")
        except Exception as e:
            print(f"[lỗi] tin {source}: {e!r}", file=sys.stderr)
            continue
        for item in items:
            title = (item.findtext("title") or "").strip()
            if word in normalize(title):
                found.append((title, (item.findtext("link") or "").strip(), source,
                              published_at(item.findtext("pubDate"))))
    return newest_first(found)[:RESULTS]


def results_text(keyword, hours):
    try:
        found, backup = search(keyword, hours), False
    except Exception as e:
        print(f"[lỗi] Google News, chuyển sang RSS các báo: {e!r}", file=sys.stderr)
        found, backup = search_feeds(keyword), True
    lines = [f"🔎 <b>Tin về “{html.escape(keyword)}”</b> · {window_label(hours)}"]
    if not found:
        lines.append(f"<i>Không có tin nào. Thử từ khóa ngắn hơn hoặc tìm xa hơn: "
                     f"/tin {html.escape(keyword)} 30ngay</i>")
    now = datetime.now(timezone.utc)
    for title, link, source, published in found:
        meta = " · ".join(x for x in [source, ago(published, now) if published else ""] if x)
        lines.append(f'• <a href="{html.escape(link)}">{html.escape(title, quote=False)}</a>'
                     + (f"\n   <i>{html.escape(meta)}</i>" if meta else ""))
    if backup:
        lines.append("<i>Google News đang lỗi, kết quả lấy từ VnExpress, Dân trí, Tuổi Trẻ, Thanh Niên</i>")
    return "\n".join(lines)


def headlines_text():
    return "📰 <b>Tin nổi bật</b>\n" + "\n".join(headlines()) + "\n\n<i>Tìm theo từ khóa: /tin giá vàng</i>"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    keyword, hours = parse_query(sys.argv[1:])
    print(results_text(keyword, hours) if keyword else headlines_text())


if __name__ == "__main__":
    main()
