"""Lấy số liệu cho bản tin: thời tiết, giá vàng, chỉ số chứng khoán, tin nổi bật, gợi ý hôm nay."""
import sys
from datetime import datetime, timezone

from domain.bantin import weather as rules
from infrastructure import clock, marketdata, openmeteo

# (tên báo, link RSS, số tin lấy)
NEWS_FEEDS = [
    ("VnExpress", "https://vnexpress.net/rss/tin-noi-bat.rss", 5),
    ("Dân trí", "https://dantri.com.vn/rss/home.rss", 3),
]

# (tên hiển thị, mã bên VNDirect, mã bên SSI dùng dự phòng)
INDICES = [
    ("VN-Index", "VNINDEX", "VNINDEX"),
    ("VN30", "VN30", "VN30"),
    ("HNX", "HNX", "HNXINDEX"),
    ("UPCoM", "UPCOM", None),
]


def weather_data(place=rules.HANOI, day=0):
    """(dự báo ngày `day`, không khí hiện tại hoặc None): không khí chỉ lấy cho hôm nay, lỗi thì bỏ qua."""
    w = openmeteo.daily(place, day)
    air = None
    if day == 0:
        try:
            air = openmeteo.air_now(place)
        except Exception as e:
            print(f"[lỗi] không khí: {e!r}", file=sys.stderr)
    return w, air


def hourly(place=rules.HANOI, days=2):
    return openmeteo.hourly(place, days)


def today_tips():
    now = clock.now_vn()
    return rules.tips(hourly(), now.date(), now.replace(tzinfo=None))


def gold_prices():
    """Giá vàng triệu đồng/lượng: {"sjc": (mua, bán), "nhan": (mua, bán), "nhan_ten", "nguon"}."""
    try:
        res = marketdata.sjc_gold()
        rows = res["data"]
        bar = next(r for r in rows if r["TypeName"].startswith("Vàng SJC 1L"))
        ring = next(r for r in rows if r["TypeName"].startswith("Vàng nhẫn SJC"))
        return {"sjc": (bar["BuyValue"] / 1e6, bar["SellValue"] / 1e6),
                "nhan": (ring["BuyValue"] / 1e6, ring["SellValue"] / 1e6),
                "nhan_ten": "Nhẫn SJC 9999", "nguon": f"SJC Hà Nội, cập nhật {res['latestDate']}"}
    except Exception as e:
        print(f"[lỗi] giá vàng SJC, chuyển sang PNJ: {e!r}", file=sys.stderr)
    by_code = marketdata.pnj_gold()
    # PNJ báo nghìn đồng/chỉ -> đổi sang triệu đồng/lượng
    return {"sjc": (by_code["SJC"]["giamua"] / 100, by_code["SJC"]["giaban"] / 100),
            "nhan": (by_code["N24K"]["giamua"] / 100, by_code["N24K"]["giaban"] / 100),
            "nhan_ten": "Nhẫn trơn 9999", "nguon": "nguồn PNJ"}


def index_history(vnd_symbol, ssi_symbol, days=15):
    return marketdata.index_history(vnd_symbol, ssi_symbol, days)


def index_rows():
    """Mỗi chỉ số: (tên, điểm đóng cửa, chênh, % chênh, ngày phiên dd/mm) hoặc (tên, None...) nếu không lấy được."""
    rows = []
    for name, vnd_symbol, ssi_symbol in INDICES:
        try:
            t, c = index_history(vnd_symbol, ssi_symbol)
            change = c[-1] - c[-2]
            pct = change / c[-2] * 100
            # Mốc thời gian là 0h UTC của ngày giao dịch
            rows.append((name, c[-1], change, pct, datetime.fromtimestamp(t[-1], timezone.utc).strftime("%d/%m")))
        except Exception as e:
            print(f"[lỗi] chỉ số {name}: {e!r}", file=sys.stderr)
            rows.append((name, None, None, None, None))
    return rows


def news_feeds():
    """Mỗi nguồn: (tên báo, [(tiêu đề, link)]) hoặc (tên báo, None) nếu không lấy được."""
    feeds = []
    for source, url, count in NEWS_FEEDS:
        try:
            items = marketdata.feed_items(url, count)
        except Exception as e:
            print(f"[lỗi] tin {source}: {e!r}", file=sys.stderr)
            feeds.append((source, None))
            continue
        feeds.append((source, [((i.findtext("title") or "").strip(), (i.findtext("link") or "").strip())
                               for i in items]))
    return feeds
