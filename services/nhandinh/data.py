"""Lấy dữ liệu cho nhận định trong phiên: ngành, mã HOSE, khuyến nghị CTCK, tin tài chính, giá và chỉ số."""
import html
import re
import sys
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from domain.chungkhoan.rules import published_at
from domain.nhandinh import rules
from infrastructure import clock, stockfeeds
from repositories import keys
from repositories.nhandinh.cache import remembered
from services.chungkhoan import market

FEEDS = [("CafeF", "https://cafef.vn/thi-truong-chung-khoan.rss"),
         ("CafeF", "https://cafef.vn/doanh-nghiep.rss"),
         ("Vietstock", "https://vietstock.vn/830/chung-khoan/co-phieu.rss"),
         ("Vietstock", "https://vietstock.vn/1636/nhan-dinh-phan-tich/nhan-dinh-thi-truong.rss"),
         ("Vietstock", "https://vietstock.vn/582/nhan-dinh-phan-tich/phan-tich-co-ban.rss"),
         ("VnExpress", "https://vnexpress.net/rss/kinh-doanh.rss")]


def industry_map():
    """{mã: tên ngành} theo phân ngành ICB cấp 3 của VNDirect (giữ 7 ngày)."""
    return remembered(keys.CACHE_SECTORS, 7 * 86400, lambda: rules.industry_names(stockfeeds.industries()))


def hose_symbols():
    return remembered(keys.CACHE_HOSE, 86400, lambda: [x["symbol"] for x in stockfeeds.vci_group("HOSE")])


def recommendations(days=30):
    """{mã: [khuyến nghị mới nhất trước]} trong `days` ngày qua (giữ 3 giờ)."""
    since = (clock.now_vn().date() - timedelta(days=days)).isoformat()
    return remembered(keys.cache_foreign(days, since), 3 * 3600,
                      lambda: rules.recommendations_by_code(stockfeeds.recommendations(since).get("data", [])))


def text_of(node, tag):
    return re.sub(r"<[^>]+>", " ", html.unescape(node.findtext(tag) or "")).strip()



def feed(source, url):
    items = []
    for item in ET.fromstring(stockfeeds.get(url)).iter("item"):
        title = " ".join(text_of(item, "title").split())
        if title:
            items.append({"nguon": source, "tieu_de": title, "link": (item.findtext("link") or "").strip(),
                          "luc": published_at(item.findtext("pubDate")),
                          "tom_tat": " ".join(text_of(item, "description").split())[:220]})
    return items


def safe(fn, *args):
    try:
        return fn(*args)
    except Exception as e:
        print(f"[lỗi] {fn.__name__}{args[:1]}: {e!r}", file=sys.stderr)
        return None


def news(hours=18):
    """Tin tài chính mới trong `hours` giờ qua, mới nhất trước, bỏ tin trùng tiêu đề."""
    with ThreadPoolExecutor(len(FEEDS)) as ex:
        results = list(ex.map(lambda f: safe(feed, *f), FEEDS))
    return rules.merge_news(results, hours)


def gather(hours=18):
    """Lấy song song mọi dữ liệu cần cho nhận định."""
    with ThreadPoolExecutor(5) as ex:
        f_names = ex.submit(safe, industry_map)
        f_syms = ex.submit(safe, hose_symbols)
        f_index = ex.submit(safe, market.index_rows)
        f_recs = ex.submit(safe, recommendations)
        f_news = ex.submit(safe, news, hours)
        names, syms = f_names.result() or {}, f_syms.result() or []
        quotes = safe(market.quotes, syms) or {} if syms else {}
        recs = f_recs.result() or {}
        missing = [c for c in recs if c not in quotes]
        if missing:  # mã có khuyến nghị nhưng không ở HOSE (HNX, UPCoM)
            quotes_other = safe(market.quotes, missing) or {}
        else:
            quotes_other = {}
        index = f_index.result() or {}
        items = f_news.result() or []
    stocks, sectors = rules.board(quotes, names)
    prices = {c: (q["price"] or q["ref"]) for c, q in {**quotes_other, **quotes}.items() if q.get("ref")}
    return {"index": index, "stocks": stocks, "sectors": sectors, "recs": rules.rec_rows(recs, prices), "news": items,
            "symbols": set(syms) | set(recs) | set(quotes_other)}
