"""Lấy số liệu chứng khoán: giá từng mã (VCI, dự phòng VPS), tổng quan phiên, biến động giá, tin Google News."""
import sys
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

from domain.chungkhoan import rules
from infrastructure import clock, stockfeeds
from services.bantin.data import index_history


def safe(fn, *args):
    try:
        return fn(*args)
    except Exception as e:
        print(f"[lỗi] {fn.__name__}: {e!r}", file=sys.stderr)
        return None


def quotes(symbols):
    """Giá nhiều mã trong một lần gọi VCI: {mã: giá}; mã không tồn tại thì bỏ qua."""
    rows = stockfeeds.vci_quotes(symbols) if symbols else []
    return {q["symbol"]: q for q in map(rules.from_vci, rows) if q}


def quote(symbol):
    """Giá của mã, None nếu mã không tồn tại."""
    try:
        rows = stockfeeds.vci_quotes([symbol])
        return rules.from_vci(rows[0]) if rows else None
    except Exception as e:
        print(f"[lỗi] giá VCI {symbol}, chuyển sang VPS: {e!r}", file=sys.stderr)
    rows = stockfeeds.vps_quote(symbol)
    return rules.from_vps(rows[0]) if rows else None


def index_rows():
    """{tên chỉ số: (điểm, tham chiếu, giá trị giao dịch đồng, số mã tăng, giảm, đứng)} từ VPS."""
    return rules.index_table(stockfeeds.vps_indices(rules.VPS_INDICES))


def indices():
    return index_rows()


def vn30_movers():
    """(mã tăng mạnh, mã giảm mạnh, khối ngoại ròng) trong rổ VN30."""
    symbols = [r["symbol"] for r in stockfeeds.vci_group("VN30")]
    return rules.movers(list(map(rules.from_vci, stockfeeds.vci_quotes(symbols))))


def summary_data():
    """(chỉ số hoặc None nếu VPS lỗi, rổ VN30 hoặc None) lấy song song."""
    with ThreadPoolExecutor() as pool:
        idx = pool.submit(safe, indices)
        movers = pool.submit(safe, vn30_movers)
    return idx.result(), movers.result()


def performance(symbol):
    t, c = index_history(symbol, symbol, days=370)
    return rules.performance(t, c, clock.now_vn().year)


def google_news(query):
    """Các tin Google News (tiếng Việt) khớp truy vấn: [(tiêu đề, link, tên báo, giờ đăng)].

    Tiêu đề Google để kèm tên báo ở cuối (" - VnExpress"); giờ đăng None nếu thiếu.
    """
    items = ET.fromstring(stockfeeds.google_news_xml(query))
    return [((item.findtext("title") or "").strip(), (item.findtext("link") or "").strip(),
             (item.findtext("source") or "").strip(), rules.published_at(item.findtext("pubDate")))
            for item in items.findall(".//item")]


def news(symbol, count=rules.NEWS_COUNT):
    """Tin 7 ngày qua về mã: [(tiêu đề, link)]."""
    return [(title, link) for title, link, *_ in google_news(f'"cổ phiếu {symbol}" when:7d')[:count]]


def detail(symbol):
    """Số liệu chi tiết một mã: (giá | lỗi, biến động giá hoặc None, tin hoặc None).

    Giá là dict, None nếu mã không tồn tại, hoặc Exception khi không lấy được.
    """
    with ThreadPoolExecutor() as pool:
        q = pool.submit(quote, symbol)
        perf = pool.submit(safe, performance, symbol)
        articles = pool.submit(safe, news, symbol)
    try:
        q = q.result()
    except Exception as e:
        print(f"[lỗi] giá {symbol}: {e!r}", file=sys.stderr)
        return e, None, None
    return q, perf.result(), articles.result()
