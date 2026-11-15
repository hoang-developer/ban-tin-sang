"""Tìm tin theo từ khóa: Google News, lỗi thì tìm trong tiêu đề RSS các báo."""
import sys

from domain.canhbao.rules import KEYWORD_FEEDS, normalize
from domain.chungkhoan.rules import published_at
from domain.tintuc import rules
from infrastructure import marketdata
from services.chungkhoan.market import google_news


def search(keyword, hours):
    """Tin mới nhất về từ khóa trên Google News: [(tiêu đề, link, tên báo, giờ đăng)]."""
    return rules.clean_google(google_news(rules.google_query(keyword, hours)))


def search_feeds(keyword):
    """Dự phòng khi Google News lỗi: tìm trong tiêu đề RSS các báo trong KEYWORD_FEEDS."""
    word = normalize(keyword.strip('"'))
    found = []
    for source, url in KEYWORD_FEEDS:
        try:
            items = marketdata.feed_items(url, None)
        except Exception as e:
            print(f"[lỗi] tin {source}: {e!r}", file=sys.stderr)
            continue
        for item in items:
            title = (item.findtext("title") or "").strip()
            if word in normalize(title):
                found.append((title, (item.findtext("link") or "").strip(), source,
                              published_at(item.findtext("pubDate"))))
    return rules.newest_first(found)[:rules.RESULTS]


def results(keyword, hours):
    """(tin tìm được, đang dùng RSS dự phòng không)."""
    try:
        return search(keyword, hours), False
    except Exception as e:
        print(f"[lỗi] Google News, chuyển sang RSS các báo: {e!r}", file=sys.stderr)
        return search_feeds(keyword), True

