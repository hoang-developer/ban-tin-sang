"""Thông tin chứng khoán cho lệnh /stock của bot Telegram.

Xem thử: python chungkhoan.py           (tổng quan phiên hiện tại)
         python chungkhoan.py FPT VNM   (chi tiết từng mã)
"""
import gzip
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from bantin import UA, VN_TZ, WEEKDAYS, index_history, stocks, vn_num

# ---- Cấu hình -------------------------------------------------------------
# Mã chỉ số bên VPS -> tên hiển thị
VPS_INDICES = {"10": "VN-Index", "11": "VN30", "02": "HNX", "03": "UPCoM"}
TOP_MOVERS = 3   # số mã VN30 tăng/giảm mạnh nhất trong tổng quan
NEWS_COUNT = 3   # số tin về mỗi mã
MAX_SYMBOLS = 3  # số mã tối đa trong một lệnh
# ---------------------------------------------------------------------------

VPS = "https://bgapidatafeed.vps.com.vn"
VCI = "https://trading.vietcap.com.vn/api/price/symbols"
EXCHANGES = {"HSX": "HOSE", "HNX": "HNX", "UPCOM": "UPCoM"}
SYMBOL = re.compile(r"[A-Z0-9]{3,10}")
TIMEOUT = 8  # lệnh cần trả lời nhanh, nguồn nào chậm quá thì bỏ


def get(url, payload=None):
    headers = {"User-Agent": UA}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        body = r.read()
    return gzip.decompress(body) if body[:2] == b"\x1f\x8b" else body  # VCI luôn nén gzip


def get_json(url, payload=None):
    return json.loads(get(url, payload))


def safe(fn, *args):
    try:
        return fn(*args)
    except Exception as e:
        print(f"[lỗi] {fn.__name__}: {e!r}", file=sys.stderr)
        return None


# ---- Định dạng ------------------------------------------------------------------

def dong(x):
    """53000 -> '53.000'; chưa có giá -> '–'."""
    return vn_num(x, 0) if x else "–"


def ty(vnd):
    """Tiền đồng -> '332 tỷ' (dưới 10 tỷ thì lấy 1 số lẻ)."""
    return f"{vn_num(vnd / 1e9, 1 if abs(vnd) < 1e10 else 0)} tỷ"


def volume(shares):
    if shares >= 1e6:
        return f"{vn_num(shares / 1e6)} triệu cp"
    return f"{vn_num(shares, 0)} cp"


def change(now, ref, decimals):
    diff = now - ref
    pct = diff / ref * 100 if ref else 0
    return f"{vn_num(diff, decimals, sign=True)} ({vn_num(pct, sign=True)}%)"


def color(now, ref):
    return "🟢" if now > ref else "🔴" if now < ref else "🟡"


def session_label(now):
    if now.weekday() >= 5:
        return "Cuối tuần, không giao dịch"
    for end, label in [((9, 0), "Chưa mở cửa, số liệu phiên trước"), ((11, 30), "Phiên sáng"),
                       ((13, 0), "Nghỉ trưa"), ((14, 30), "Phiên chiều"),
                       ((14, 45), "Khớp lệnh đóng cửa (ATC)")]:
        if (now.hour, now.minute) < end:
            return label
    return "Đã đóng cửa"


# ---- Giá một mã: VCI, dự phòng VPS (cùng một dạng, đơn vị đồng và cổ phiếu) ----------

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


def quotes(symbols):
    """Giá nhiều mã trong một lần gọi VCI: {mã: giá}; mã không tồn tại thì bỏ qua."""
    rows = get_json(f"{VCI}/getList", {"symbols": list(symbols)}) if symbols else []
    return {q["symbol"]: q for q in map(from_vci, rows) if q}


def quote(symbol):
    """Giá của mã, None nếu mã không tồn tại."""
    try:
        rows = get_json(f"{VCI}/getList", {"symbols": [symbol]})
        return from_vci(rows[0]) if rows else None
    except Exception as e:
        print(f"[lỗi] giá VCI {symbol}, chuyển sang VPS: {e!r}", file=sys.stderr)
    rows = get_json(f"{VPS}/getliststockdata/{symbol}")
    return from_vps(rows[0]) if rows else None


# ---- Tổng quan phiên --------------------------------------------------------------

def index_rows():
    """{tên chỉ số: (điểm, tham chiếu, giá trị giao dịch đồng, số mã tăng, giảm, đứng)} từ VPS."""
    rows = {r["mc"]: r for r in get_json(f"{VPS}/getlistindexdetail/{','.join(VPS_INDICES)}")}
    out = {}
    for code, name in VPS_INDICES.items():
        r = rows[code]
        _, _, value, up, down, same = r["ot"].split("|")  # thay đổi|%|giá trị|tăng|giảm|đứng
        out[name] = (r["cIndex"], r["oIndex"], float(value) * 1e6, up, down, same)
    return out


def indices():
    lines = []
    for name, (now, ref, value, up, down, same) in index_rows().items():
        lines.append(f"{color(now, ref)} {name}: <b>{vn_num(now)}</b>  {change(now, ref, 2)}\n"
                     f"      GT {ty(value)} · ▲{up} ▼{down} ■{same}")
    return lines


def vn30_movers():
    symbols = [r["symbol"] for r in get_json(f"{VCI}/getByGroup?group=VN30")]
    quotes = [q for q in map(from_vci, get_json(f"{VCI}/getList", {"symbols": symbols}))
              if q and q["price"] and q["ref"]]
    quotes.sort(key=lambda q: q["price"] / q["ref"], reverse=True)

    def row(qs):
        return " · ".join(f"<b>{q['symbol']}</b> {vn_num((q['price'] / q['ref'] - 1) * 100, sign=True)}%"
                          for q in qs)

    lines = []
    up = [q for q in quotes if q["price"] > q["ref"]][:TOP_MOVERS]
    down = [q for q in reversed(quotes) if q["price"] < q["ref"]][:TOP_MOVERS]
    if up:
        lines.append(f"🟢 Tăng mạnh: {row(up)}")
    if down:
        lines.append(f"🔴 Giảm mạnh: {row(down)}")
    net = sum(q["f_buy"] - q["f_sell"] for q in quotes)
    lines.append(f"🌏 Khối ngoại {'mua' if net >= 0 else 'bán'} ròng {ty(abs(net))}")
    return lines


def market_summary():
    now = datetime.now(VN_TZ)
    with ThreadPoolExecutor() as pool:
        idx = pool.submit(safe, indices)
        movers = pool.submit(safe, vn30_movers)
    parts = [f"📈 <b>Chứng khoán – {WEEKDAYS[now.weekday()]} {now:%d/%m}, {now:%H:%M}</b>\n"
             f"<i>{session_label(now)}</i>",
             "\n".join(idx.result() or stocks())]  # VPS lỗi thì lấy giá theo ngày của VNDirect
    if movers.result():
        parts.append("<b>Trong rổ VN30</b>\n" + "\n".join(movers.result()))
    parts.append("<i>Xem một mã: /stock FPT</i>")
    return "\n\n".join(parts)


# ---- Chi tiết một mã -------------------------------------------------------------

def performance(symbol):
    t, c = index_history(symbol, symbol, days=370)
    c = [x * 1000 for x in c]  # VNDirect tính nghìn đồng
    last, year = c[-1], datetime.now(VN_TZ).year

    def pct(old):
        return f"{vn_num((last - old) / old * 100, 1, sign=True)}%"

    parts = [f"{label} {pct(c[-1 - n])}" for label, n in [("1 tuần", 5), ("1 tháng", 21)] if len(c) > n]
    before = [x for ts, x in zip(t, c) if datetime.fromtimestamp(ts, timezone.utc).year < year]
    if before:
        parts.append(f"từ đầu năm {pct(before[-1])}")
    year_ago = time.time() - 365 * 86400
    closes = [x for ts, x in zip(t, c) if ts >= year_ago]
    return [" · ".join(parts),
            f"52 tuần: thấp {dong(min(closes))} – cao {dong(max(closes))} <i>(giá đã điều chỉnh)</i>"]


def google_news(query):
    """Các tin Google News (tiếng Việt) khớp truy vấn: [(tiêu đề, link)]."""
    q = urllib.parse.quote(query)
    items = ET.fromstring(get(f"https://news.google.com/rss/search?q={q}&hl=vi&gl=VN&ceid=VN:vi"))
    return [((item.findtext("title") or "").strip(), (item.findtext("link") or "").strip())
            for item in items.findall(".//item")]


def news(symbol, count=NEWS_COUNT):
    lines = []
    for title, link in google_news(f'"cổ phiếu {symbol}" when:7d')[:count]:
        lines.append(f'• <a href="{html.escape(link)}">{html.escape(title, quote=False)}</a>')
    return lines or ["<i>Không có tin trong 7 ngày qua</i>"]


def stock_detail(symbol):
    with ThreadPoolExecutor() as pool:
        q = pool.submit(quote, symbol)
        perf = pool.submit(safe, performance, symbol)
        articles = pool.submit(safe, news, symbol)
    try:
        q = q.result()
    except Exception as e:
        print(f"[lỗi] giá {symbol}: {e!r}", file=sys.stderr)
        return f"⚪ <b>{symbol}</b>: không lấy được giá, thử lại sau nhé"
    if not q:
        return f"❓ Không tìm thấy mã <b>{symbol}</b>"

    price = q["price"] or q["ref"]  # chưa khớp lệnh nào thì lấy giá tham chiếu
    if q["ceiling"] and price >= q["ceiling"]:
        icon = "🟣"
    elif q["floor"] and price <= q["floor"]:
        icon = "🔵"
    else:
        icon = color(price, q["ref"])
    head = " · ".join(x for x in [f"<b>{symbol}</b>", q["exchange"], html.escape(q["name"] or "")] if x)
    lines = [head,
             f"{icon} <b>{dong(price)}</b>  {change(price, q['ref'], 0)}"
             + ("" if q["price"] else "  <i>(chưa khớp lệnh)</i>"),
             f"Tham chiếu {dong(q['ref'])} · Trần {dong(q['ceiling'])} · Sàn {dong(q['floor'])}"]
    if q["volume"]:
        net = q["f_buy"] - q["f_sell"]
        lines += [f"Mở {dong(q['open'])} · Cao {dong(q['high'])} · Thấp {dong(q['low'])}",
                  f"KL {volume(q['volume'])}" + (f" · GT {ty(q['value'])}" if q["value"] else ""),
                  f"Khối ngoại: mua {ty(q['f_buy'])} · bán {ty(q['f_sell'])} · "
                  f"{'mua' if net >= 0 else 'bán'} ròng {ty(abs(net))}"]
    for label, book in [("Dư mua", q["bids"]), ("Dư bán", q["asks"])]:
        if book:
            lines.append(f"{label}: " + " · ".join(f"{dong(p)} ({vn_num(v, 0)})" for p, v in book))

    stats = (perf.result() or []) + ([f"Vốn hóa {ty(q['listed'] * price)}"] if q["listed"] else [])
    parts = ["\n".join(lines)]
    if stats:
        parts.append("<b>📊 Biến động giá</b>\n" + "\n".join(stats))
    parts.append("<b>📰 Tin 7 ngày qua</b>\n" + "\n".join(articles.result() or ["<i>Không lấy được tin</i>"]))
    return "\n\n".join(parts)


# ---- Lệnh /stock -------------------------------------------------------------------

def stock_command(args):
    """/stock -> tổng quan phiên; /stock FPT VNM -> chi tiết từng mã."""
    if not args:
        return market_summary()
    symbols = list(dict.fromkeys(a.upper() for a in args))
    bad = [s for s in symbols if not SYMBOL.fullmatch(s)]
    if bad:
        return f"Mã không hợp lệ: {html.escape(' '.join(bad))}. Ví dụ: /stock FPT"
    with ThreadPoolExecutor() as pool:
        text = "\n\n━━━━━━━━━━\n\n".join(pool.map(stock_detail, symbols[:MAX_SYMBOLS]))
    if len(symbols) > MAX_SYMBOLS:
        text += f"\n\n<i>Mỗi lần xem tối đa {MAX_SYMBOLS} mã.</i>"
    return text


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    print(stock_command(sys.argv[1:]))


if __name__ == "__main__":
    main()
