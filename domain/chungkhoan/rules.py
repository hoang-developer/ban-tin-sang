"""Chứng khoán: đổi dòng giá của VCI/VPS về một dạng chung, nhãn phiên giao dịch, tính tăng giảm, biến động giá."""
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

# Mã chỉ số bên VPS -> tên hiển thị
VPS_INDICES = {"10": "VN-Index", "11": "VN30", "02": "HNX", "03": "UPCoM"}
TOP_MOVERS = 3   # số mã VN30 tăng/giảm mạnh nhất trong tổng quan
NEWS_COUNT = 3   # số tin về mỗi mã
MAX_SYMBOLS = 3  # số mã tối đa trong một lệnh
EXCHANGES = {"HSX": "HOSE", "HNX": "HNX", "UPCOM": "UPCoM"}
SYMBOL = re.compile(r"[A-Z0-9]{3,10}")


def session_label(now):
    if now.weekday() >= 5:
        return "Cuối tuần, không giao dịch"
    for end, label in [((9, 0), "Chưa mở cửa, số liệu phiên trước"), ((11, 30), "Phiên sáng"),
                       ((13, 0), "Nghỉ trưa"), ((14, 30), "Phiên chiều"),
                       ((14, 45), "Khớp lệnh đóng cửa (ATC)")]:
        if (now.hour, now.minute) < end:
            return label
    return "Đã đóng cửa"


def from_vci(row):
    info, m = row.get("listingInfo"), row["matchPrice"]
    if not info:
        return None  # VCI trả listingInfo rỗng khi mã không tồn tại
    book = row.get("bidAsk") or {}
    return {
        "symbol": info["symbol"], "name": info.get("organName"),
        "exchange": EXCHANGES.get(info.get("board"), info.get("board")),
        "listed": info.get("listedShare"),
        "price": m["matchPrice"], "ref": m["referencePrice"],
        "ceiling": m["ceilingPrice"], "floor": m["floorPrice"],
        "open": m["openPrice"], "high": m["highest"], "low": m["lowest"],
        # `or 0` phòng khi VCI để trống; giá trị giao dịch VCI tính theo triệu đồng
        "volume": m["accumulatedVolume"], "value": (m["accumulatedValue"] or 0) * 1e6,
        "f_buy": m["foreignBuyValue"] or 0, "f_sell": m["foreignSellValue"] or 0,
        "bids": [(b["price"], b["volume"]) for b in book.get("bidPrices") or []],
        "asks": [(a["price"], a["volume"]) for a in book.get("askPrices") or []],
    }


def from_vps(r):
    k = 1000  # VPS tính giá theo nghìn đồng, khối lượng theo lô 10 cổ phiếu

    def levels(keys):
        out = []
        for key in keys:
            price, vol, _ = r[key].split("|")
            if float(price):
                out.append((float(price) * k, int(vol) * 10))
        return out

    return {
        "symbol": r["sym"], "name": None, "exchange": None, "listed": None,
        "price": r["lastPrice"] * k, "ref": r["r"] * k, "ceiling": r["c"] * k, "floor": r["f"] * k,
        "open": float(r["openPrice"] or 0) * k, "high": float(r["highPrice"] or 0) * k,
        "low": float(r["lowPrice"] or 0) * k,
        "volume": r["lot"] * 10, "value": None,
        "f_buy": float(r["fBValue"] or 0) * k, "f_sell": float(r["fSValue"] or 0) * k,
        "bids": levels(["g1", "g2", "g3"]), "asks": levels(["g4", "g5", "g6"]),
    }


def index_table(rows):
    """Dòng chỉ số của VPS -> {tên chỉ số: (điểm, tham chiếu, giá trị giao dịch đồng, số mã tăng, giảm, đứng)}."""
    by_code = {r["mc"]: r for r in rows}
    out = {}
    for code, name in VPS_INDICES.items():
        r = by_code[code]
        _, _, value, up, down, same = r["ot"].split("|")  # thay đổi|%|giá trị|tăng|giảm|đứng
        out[name] = (r["cIndex"], r["oIndex"], float(value) * 1e6, up, down, same)
    return out


def movers(quotes):
    """Các mã VN30 (đã có giá và tham chiếu): (tăng mạnh nhất, giảm mạnh nhất, khối ngoại ròng đồng)."""
    quotes = [q for q in quotes if q and q["price"] and q["ref"]]
    quotes.sort(key=lambda q: q["price"] / q["ref"], reverse=True)
    up = [q for q in quotes if q["price"] > q["ref"]][:TOP_MOVERS]
    down = [q for q in reversed(quotes) if q["price"] < q["ref"]][:TOP_MOVERS]
    return up, down, sum(q["f_buy"] - q["f_sell"] for q in quotes)


def performance(t, c, year, now_ts=None):
    """Biến động giá từ lịch sử đóng cửa (t mốc giây, c giá nghìn đồng):
    ({'1 tuần'|'1 tháng'|'từ đầu năm': % đổi}, thấp 52 tuần, cao 52 tuần), giá đổi ra đồng."""
    c = [x * 1000 for x in c]  # VNDirect tính nghìn đồng
    last = c[-1]

    def pct(old):
        return (last - old) / old * 100

    changes = [(label, pct(c[-1 - n])) for label, n in [("1 tuần", 5), ("1 tháng", 21)] if len(c) > n]
    before = [x for ts, x in zip(t, c) if datetime.fromtimestamp(ts, timezone.utc).year < year]
    if before:
        changes.append(("từ đầu năm", pct(before[-1])))
    year_ago = (time.time() if now_ts is None else now_ts) - 365 * 86400
    closes = [x for ts, x in zip(t, c) if ts >= year_ago]
    return changes, min(closes), max(closes)


def published_at(text):
    """Giờ đăng trong RSS ('Sun, 01 Nov 2026 02:23:43 GMT') -> datetime; None nếu không đọc được."""
    try:
        return parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return None
