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
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

import amlich
import tg

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

def weather(place=HANOI, day=0):
    """Thời tiết một ngày ở tọa độ place: day=0 là hôm nay (kèm nhiệt độ lúc này và AQI), 1 là ngày mai."""
    lat, lon = place
    q = urllib.parse.urlencode({
        "latitude": lat, "longitude": lon,
        "current": "temperature_2m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "timezone": "Asia/Bangkok", "forecast_days": day + 1,
    })
    w = fetch_json(f"https://api.open-meteo.com/v1/forecast?{q}")
    d = w["daily"]
    icon, desc = WEATHER.get(d["weather_code"][day], ("🌡️", "Không rõ"))
    rain = d["precipitation_probability_max"][day]
    now = f" (bây giờ {w['current']['temperature_2m']:.0f}°C)" if day == 0 else ""
    lines = [
        f"{icon} {desc}, {d['temperature_2m_min'][day]:.0f}–{d['temperature_2m_max'][day]:.0f}°C{now}",
        f"☔ Khả năng mưa: {rain}%" + (" – nhớ mang ô!" if rain >= 50 else ""),
    ]
    if day == 0:
        try:
            lines += air_quality(place)
        except Exception as e:
            print(f"[lỗi] không khí: {e!r}", file=sys.stderr)
    return lines


def air_quality(place=HANOI):
    lat, lon = place
    q = urllib.parse.urlencode({"latitude": lat, "longitude": lon,
                                "current": "us_aqi,pm2_5", "timezone": "Asia/Bangkok"})
    c = fetch_json(f"https://air-quality-api.open-meteo.com/v1/air-quality?{q}")["current"]
    aqi = c["us_aqi"]
    icon, label = next((i, lbl) for limit, i, lbl in AQI_LEVELS if aqi <= limit)
    lines = [f"{icon} Không khí: AQI {aqi:.0f} – {label} (PM2.5: {c['pm2_5']:.0f} µg/m³)"]
    if aqi > 100:
        lines.append("😷 Nên đeo khẩu trang khi ra ngoài")
    return lines


def hourly(place=HANOI, days=2):
    """Dự báo theo giờ: mỗi giờ một dict time/feel/rain_prob/rain/humid/uv/aqi (aqi None nếu lỗi)."""
    lat, lon = place
    q = urllib.parse.urlencode({
        "latitude": lat, "longitude": lon, "forecast_days": days, "timezone": "Asia/Bangkok",
        "hourly": "apparent_temperature,precipitation_probability,precipitation,relative_humidity_2m,uv_index",
    })
    h = fetch_json(f"https://api.open-meteo.com/v1/forecast?{q}")["hourly"]
    try:
        q = urllib.parse.urlencode({"latitude": lat, "longitude": lon, "hourly": "us_aqi",
                                    "forecast_days": days, "timezone": "Asia/Bangkok"})
        a = fetch_json(f"https://air-quality-api.open-meteo.com/v1/air-quality?{q}")["hourly"]
        aqi = dict(zip(a["time"], a["us_aqi"]))
    except Exception as e:
        print(f"[lỗi] AQI theo giờ: {e!r}", file=sys.stderr)
        aqi = {}
    return [{"time": datetime.fromisoformat(t), "feel": feel, "rain_prob": prob or 0, "rain": rain or 0,
             "humid": humid or 0, "uv": uv or 0, "aqi": aqi.get(t)}
            for t, feel, prob, rain, humid, uv in zip(
                h["time"], h["apparent_temperature"], h["precipitation_probability"], h["precipitation"],
                h["relative_humidity_2m"], h["uv_index"])]


# Nhiệt độ cảm nhận buổi sáng dưới mức này -> nên mặc gì
CLOTHES = [(12, "áo khoác dày, khăn quàng"), (17, "áo khoác ấm"), (21, "áo khoác mỏng"),
           (25, "áo dài tay mỏng"), (30, "áo cộc tay"), (float("inf"), "đồ mỏng thoáng mát")]


def wet(h):
    return h["rain_prob"] >= 40 or h["rain"] >= 0.2


def tips(hours, day, now):
    """Gợi ý mặc gì, phơi đồ, chạy bộ cho ngày `day`, chỉ xét những giờ chưa qua."""
    hs = {h["time"].hour: h for h in hours if h["time"].date() == day}
    if not hs:
        return []
    past = now.hour if day == now.date() else -1
    lines = []

    # Mặc gì: theo giờ sắp ra đường (7h, hoặc giờ tới nếu đã quá 7h)
    start = 7 if past < 7 else min((h for h in hs if h > past), default=max(hs))
    morning = hs.get(start) or hs[min(hs)]
    noon = max((hs[h]["feel"] for h in range(max(11, start), 16) if h in hs), default=morning["feel"])
    wear = next(text for limit, text in CLOTHES if morning["feel"] < limit)
    extra = []
    if noon - morning["feel"] >= 7:
        extra.append(f"trưa lên {noon:.0f}°C nên mặc nhiều lớp dễ cởi")
    if any(wet(hs[h]) for h in range(max(7, past + 1), 20) if h in hs):
        extra.append("mang áo mưa")
    uv = max(h["uv"] for h in hs.values())
    if uv >= 8:
        extra.append(f"nắng gắt (UV {uv:.0f}), che chắn kỹ")
    when = "Sáng" if start == 7 else f"{start}h"
    lines.append(f"👕 {when} {morning['feel']:.0f}°C: {wear}" + "".join(f"; {e}" for e in extra))

    window = [h for h in range(8, 18) if h in hs and h > past]
    rest = "cả ngày" if past < 8 else "phần còn lại trong ngày"
    if len(window) >= 2:
        streaks, start = [], None  # các quãng giờ khô liền nhau: (từ giờ, tới giờ)
        for h in window + [None]:
            if h is not None and not wet(hs[h]):
                start = h if start is None else start
            elif start is not None:
                streaks.append((start, h if h is not None else window[-1] + 1))
                start = None
        if not streaks:
            text = f"mưa {rest}, nên phơi trong nhà"
        else:
            begin, end = max(streaks, key=lambda s: s[1] - s[0])
            if (begin, end) == (window[0], window[-1] + 1):
                text = f"khô ráo {rest}, phơi thoải mái"
                if sum(hs[h]["humid"] for h in window) / len(window) >= 85:
                    text += ", nhưng trời ẩm nên đồ lâu khô"
            elif end - begin < 3:
                text = "ít giờ khô ráo, nên phơi trong nhà"
            elif begin == window[0]:
                text = f"phơi sớm, cất trước {end}h"
            elif end > window[-1]:
                text = f"đợi tới {begin}h hãy phơi"
            else:
                text = f"phơi từ {begin}h, cất trước {end}h"
        lines.append(f"🧺 Phơi đồ: {text}")

    slots = [h for h in (5, 6, 7, 17, 18, 19) if h in hs and h > past]
    if slots:
        def blockers(h):
            x = hs[h]
            return [why for why, bad in [("aqi", x["aqi"] is not None and x["aqi"] > 100),
                                         ("mưa", wet(x)), ("nóng", x["feel"] > 32)] if bad]

        good = [h for h in slots if not blockers(h)]
        if good:
            best = hs[min(good, key=lambda h: (hs[h]["aqi"] or 0, abs(hs[h]["feel"] - 22)))]
            aqi = f", AQI {best['aqi']:.0f}" if best["aqi"] is not None else ""
            text = f"hợp nhất lúc {best['time'].hour}h ({best['feel']:.0f}°C{aqi})"
        else:
            reasons = [why for h in slots for why in blockers(h)]
            why = max(set(reasons), key=reasons.count)
            if why == "aqi":
                low = min(hs[h]["aqi"] for h in slots)
                text = f"không khí xấu (AQI thấp nhất {low:.0f}), nên tập trong nhà"
            elif why == "mưa":
                text = "giờ chạy đều có mưa, nên tập trong nhà"
            else:
                text = "trời nóng, nên tập trong nhà cho mát"
        lines.append(f"🏃 Chạy bộ: {text}")
    return lines


def today_tips():
    now = datetime.now(VN_TZ)
    return tips(hourly(), now.date(), now.replace(tzinfo=None))


def gold_prices():
    """Giá vàng triệu đồng/lượng: {"sjc": (mua, bán), "nhan": (mua, bán), "nhan_ten", "nguon"}."""
    try:
        body = urllib.parse.urlencode({"method": "GetCurrentGoldPricesByBranch", "BranchId": 2}).encode()
        res = fetch_json("https://sjc.com.vn/GoldPrice/Services/PriceService.ashx", data=body)
        rows = res["data"]
        bar = next(r for r in rows if r["TypeName"].startswith("Vàng SJC 1L"))
        ring = next(r for r in rows if r["TypeName"].startswith("Vàng nhẫn SJC"))
        return {"sjc": (bar["BuyValue"] / 1e6, bar["SellValue"] / 1e6),
                "nhan": (ring["BuyValue"] / 1e6, ring["SellValue"] / 1e6),
                "nhan_ten": "Nhẫn SJC 9999", "nguon": f"SJC Hà Nội, cập nhật {res['latestDate']}"}
    except Exception as e:
        print(f"[lỗi] giá vàng SJC, chuyển sang PNJ: {e!r}", file=sys.stderr)
    by_code = {r["masp"]: r for r in fetch_json(PNJ_GOLD_URL)["data"]}
    # PNJ báo nghìn đồng/chỉ -> đổi sang triệu đồng/lượng
    return {"sjc": (by_code["SJC"]["giamua"] / 100, by_code["SJC"]["giaban"] / 100),
            "nhan": (by_code["N24K"]["giamua"] / 100, by_code["N24K"]["giaban"] / 100),
            "nhan_ten": "Nhẫn trơn 9999", "nguon": "nguồn PNJ"}


def gold():
    p = gold_prices()

    def row(name, prices):
        buy, sell = prices
        return f"{name}: mua <b>{vn_num(buy, 1)}</b> – bán <b>{vn_num(sell, 1)}</b>"

    return [row("Miếng SJC", p["sjc"]), row(p["nhan_ten"], p["nhan"]),
            f"<i>triệu đồng/lượng · {p['nguon']}</i>"]


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


def lunar_line(day):
    """'🌙 Âm lịch 20/9 Bính Ngọ', kèm nhắc khi hôm nay hoặc mai là mùng 1, rằm."""
    note = {1: " · hôm nay mùng 1", 15: " · hôm nay rằm"}.get(amlich.to_lunar(day)[0], "")
    note += {1: " · mai là mùng 1", 15: " · mai là rằm"}.get(amlich.to_lunar(day + timedelta(days=1))[0], "")
    return f"🌙 Âm lịch {amlich.label(day)}{note}"


# Nút dưới bản tin; bấm thì bot trên Vercel xử lý (lenh.py)
BUTTONS = [[("🔄 Cập nhật", "bantin")], [("📈 VN30", "vn30"), ("🌧️ Mưa lúc nào?", "mua")]]


def build_message():
    today = datetime.now(VN_TZ)
    header = (f"☀️ <b>Bản tin sáng – {WEEKDAYS[today.weekday()]}, {today:%d/%m/%Y}</b>\n"
              f"{lunar_line(today.date())}")
    return "\n\n".join([
        header,
        section("🌤️ Thời tiết Hà Nội", weather),
        section("💡 Gợi ý hôm nay", today_tips),
        section("🪙 Giá vàng", gold),
        section("📈 Chứng khoán", stocks),
        section("📰 Tin nổi bật", news),
    ])


def send_telegram(token, chat_id, text, buttons=None):
    try:
        tg.send(chat_id, text, buttons, tok=token)
    except tg.TelegramError as e:
        raise SystemExit(f"Telegram từ chối tin nhắn ({e.code}): {e.description}")


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
        # Lịch chính là bot trên Vercel; lịch của GitHub chỉ tới lượt khi Vercel không chạy được
        text += "\n\n<i>⚠️ Gửi từ lịch dự phòng của GitHub: bot trên Vercel không chạy được (gõ /caidat để xem)</i>"
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat_id):
        print(text)
        print("\n(Chưa có TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID nên chỉ in ra màn hình.)")
        return
    send_telegram(token, chat_id, text, BUTTONS)
    print("Đã gửi bản tin qua Telegram.")


if __name__ == "__main__":
    main()
