"""Bản tin sáng gửi qua Telegram: thời tiết Hà Nội, giá vàng, chứng khoán, tin tức.

Chạy: python bantin.py
Cần biến môi trường TELEGRAM_BOT_TOKEN và TELEGRAM_CHAT_ID (hoặc file .env cạnh script).
Thiếu thì chỉ in bản tin ra màn hình để xem thử.
"""
import html
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---- Cấu hình -------------------------------------------------------------
VN_TZ = timezone(timedelta(hours=7))  # Việt Nam không đổi giờ mùa hè
HANOI = (21.0285, 105.8542)

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
# ---------------------------------------------------------------------------

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
PNJ_GOLD_URL = "https://edge-api.pnj.io/ecom-frontend/v1/get-gold-price?zone=00"

WEEKDAYS = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]

# Mã thời tiết WMO -> (biểu tượng, mô tả)
WEATHER = {
    0: ("☀️", "Trời quang"), 1: ("🌤️", "Ít mây"), 2: ("⛅", "Có mây"), 3: ("☁️", "Nhiều mây"),
    45: ("🌫️", "Sương mù"), 48: ("🌫️", "Sương mù"),
    51: ("🌦️", "Mưa phùn nhẹ"), 53: ("🌦️", "Mưa phùn"), 55: ("🌦️", "Mưa phùn dày"),
    61: ("🌧️", "Mưa nhỏ"), 63: ("🌧️", "Mưa vừa"), 65: ("🌧️", "Mưa to"),
    80: ("🌦️", "Mưa rào nhẹ"), 81: ("🌧️", "Mưa rào"), 82: ("⛈️", "Mưa rào rất to"),
    95: ("⛈️", "Có dông"), 96: ("⛈️", "Dông kèm mưa đá"), 99: ("⛈️", "Dông kèm mưa đá"),
}

# Ngưỡng AQI (chuẩn Mỹ) -> (biểu tượng, mức)
AQI_LEVELS = [
    (50, "🟢", "Tốt"), (100, "🟡", "Trung bình"), (150, "🟠", "Kém"),
    (200, "🔴", "Xấu"), (300, "🟣", "Rất xấu"), (float("inf"), "🟤", "Nguy hại"),
]


def fetch(url, data=None):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


def fetch_json(url, data=None):
    return json.loads(fetch(url, data))


def vn_num(x, decimals=2, sign=False):
    """1766.65 -> '1.766,65' (kiểu số Việt Nam)."""
    s = f"{x:{'+' if sign else ''},.{decimals}f}"
    return s.replace(",", "_").replace(".", ",").replace("_", ".")


# ---- Các mục trong bản tin ---------------------------------------------------

def weather():
    lat, lon = HANOI
    q = urllib.parse.urlencode({
        "latitude": lat, "longitude": lon,
        "current": "temperature_2m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "timezone": "Asia/Bangkok", "forecast_days": 1,
    })
    w = fetch_json(f"https://api.open-meteo.com/v1/forecast?{q}")
    d = w["daily"]
    icon, desc = WEATHER.get(d["weather_code"][0], ("🌡️", "Không rõ"))
    rain = d["precipitation_probability_max"][0]
    lines = [
        f"{icon} {desc}, {d['temperature_2m_min'][0]:.0f}–{d['temperature_2m_max'][0]:.0f}°C "
        f"(bây giờ {w['current']['temperature_2m']:.0f}°C)",
        f"☔ Khả năng mưa: {rain}%" + (" – nhớ mang ô!" if rain >= 50 else ""),
    ]
    try:
        lines += air_quality()
    except Exception as e:
        print(f"[lỗi] không khí: {e!r}", file=sys.stderr)
    return lines


def air_quality():
    lat, lon = HANOI
    q = urllib.parse.urlencode({"latitude": lat, "longitude": lon,
                                "current": "us_aqi,pm2_5", "timezone": "Asia/Bangkok"})
    c = fetch_json(f"https://air-quality-api.open-meteo.com/v1/air-quality?{q}")["current"]
    aqi = c["us_aqi"]
    icon, label = next((i, lbl) for limit, i, lbl in AQI_LEVELS if aqi <= limit)
    lines = [f"{icon} Không khí: AQI {aqi:.0f} – {label} (PM2.5: {c['pm2_5']:.0f} µg/m³)"]
    if aqi > 100:
        lines.append("😷 Nên đeo khẩu trang khi ra ngoài")
    return lines


def gold():
    try:
        return gold_sjc()
    except Exception as e:
        print(f"[lỗi] giá vàng SJC, chuyển sang PNJ: {e!r}", file=sys.stderr)
        return gold_pnj()


def gold_sjc():
    body = urllib.parse.urlencode({"method": "GetCurrentGoldPricesByBranch", "BranchId": 2}).encode()
    res = fetch_json("https://sjc.com.vn/GoldPrice/Services/PriceService.ashx", data=body)
    rows = res["data"]
    bar = next(r for r in rows if r["TypeName"].startswith("Vàng SJC 1L"))
    ring = next(r for r in rows if r["TypeName"].startswith("Vàng nhẫn SJC"))

    def row(name, r):
        return (f"{name}: mua <b>{vn_num(r['BuyValue'] / 1e6, 1)}</b> – "
                f"bán <b>{vn_num(r['SellValue'] / 1e6, 1)}</b>")

    return [
        row("Miếng SJC", bar),
        row("Nhẫn SJC 9999", ring),
        f"<i>triệu đồng/lượng · SJC Hà Nội, cập nhật {res['latestDate']}</i>",
    ]


def gold_pnj():
    rows = fetch_json(PNJ_GOLD_URL)["data"]
    by_code = {r["masp"]: r for r in rows}

    def row(name, r):  # PNJ báo nghìn đồng/chỉ -> đổi sang triệu đồng/lượng
        return (f"{name}: mua <b>{vn_num(r['giamua'] / 100, 1)}</b> – "
                f"bán <b>{vn_num(r['giaban'] / 100, 1)}</b>")

    return [
        row("Miếng SJC", by_code["SJC"]),
        row("Nhẫn trơn 9999", by_code["N24K"]),
        "<i>triệu đồng/lượng · nguồn PNJ</i>",
    ]


def index_history(vnd_symbol, ssi_symbol, days=15):
    now = int(time.time())
    start = now - days * 86400
    try:
        d = fetch_json("https://dchart-api.vndirect.com.vn/dchart/history"
                       f"?resolution=D&symbol={vnd_symbol}&from={start}&to={now}")
        if d.get("c"):
            return d["t"], d["c"]
    except Exception as e:
        print(f"[lỗi] VNDirect {vnd_symbol}: {e!r}", file=sys.stderr)
    if not ssi_symbol:
        raise RuntimeError(f"không có dữ liệu {vnd_symbol}")
    d = fetch_json("https://iboard-api.ssi.com.vn/statistics/charts/history"
                   f"?resolution=1D&symbol={ssi_symbol}&from={start}&to={now}")["data"]
    return d["t"], d["c"]


def stocks():
    lines, session = [], None
    for name, vnd_symbol, ssi_symbol in INDICES:
        try:
            t, c = index_history(vnd_symbol, ssi_symbol)
            change = c[-1] - c[-2]
            pct = change / c[-2] * 100
            icon = "🟢" if change > 0 else "🔴" if change < 0 else "🟡"
            lines.append(f"{icon} {name}: <b>{vn_num(c[-1])}</b>  "
                         f"{vn_num(change, sign=True)} ({vn_num(pct, sign=True)}%)")
            # Mốc thời gian là 0h UTC của ngày giao dịch
            session = session or datetime.fromtimestamp(t[-1], timezone.utc).strftime("%d/%m")
        except Exception as e:
            print(f"[lỗi] chỉ số {name}: {e!r}", file=sys.stderr)
            lines.append(f"⚪ {name}: <i>không lấy được</i>")
    if session:
        lines.insert(0, f"<i>Phiên {session}</i>")
    return lines


def news():
    lines = []
    for source, url, count in NEWS_FEEDS:
        try:
            items = ET.fromstring(fetch(url)).findall(".//item")[:count]
        except Exception as e:
            print(f"[lỗi] tin {source}: {e!r}", file=sys.stderr)
            lines.append(f"<i>{source}: không lấy được tin</i>")
            continue
        lines.append(f"<u>{source}</u>")
        for item in items:
            title = html.escape((item.findtext("title") or "").strip(), quote=False)
            link = html.escape((item.findtext("link") or "").strip(), quote=True)
            lines.append(f'• <a href="{link}">{title}</a>')
    return lines


# ---- Ghép và gửi ----------------------------------------------------------------

def section(title, fn):
    try:
        body = fn()
    except Exception as e:
        print(f"[lỗi] {title}: {e!r}", file=sys.stderr)
        body = ["<i>Không lấy được dữ liệu</i>"]
    return f"<b>{title}</b>\n" + "\n".join(body)


def build_message():
    today = datetime.now(VN_TZ)
    header = f"☀️ <b>Bản tin sáng – {WEEKDAYS[today.weekday()]}, {today:%d/%m/%Y}</b>"
    return "\n\n".join([
        header,
        section("🌤️ Thời tiết Hà Nội", weather),
        section("🪙 Giá vàng", gold),
        section("📈 Chứng khoán", stocks),
        section("📰 Tin nổi bật", news),
    ])


def send_telegram(token, chat_id, text):
    payload = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "link_preview_options": {"is_disabled": True},
    }).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage",
                                 data=payload, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=20)
    except urllib.error.HTTPError as e:
        detail = json.loads(e.read() or b"{}").get("description", "")
        raise SystemExit(f"Telegram từ chối tin nhắn ({e.code}): {detail}")


def load_env():
    env_file = Path(__file__).with_name(".env")
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    load_env()
    text = build_message()
    if os.environ.get("GITHUB_EVENT_NAME") == "schedule":
        # Lịch chính là cron-job.org; lịch của GitHub chỉ tới lượt khi nó không gọi được
        text += "\n\n<i>⚠️ Gửi từ lịch dự phòng của GitHub: cron-job.org không gọi được (xem README)</i>"
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat_id):
        print(text)
        print("\n(Chưa có TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID nên chỉ in ra màn hình.)")
        return
    send_telegram(token, chat_id, text)
    print("Đã gửi bản tin qua Telegram.")


if __name__ == "__main__":
    main()
