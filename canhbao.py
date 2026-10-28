"""Cảnh báo tức thì qua Telegram: sắp mưa, không khí xấu đi, vàng và chứng khoán biến động,
tin tức có từ khóa bạn quan tâm.

Chạy mỗi 30 phút (6h–22h) bằng GitHub Actions và chỉ nhắn khi có chuyện.
Những gì đã báo được ghi vào state.json để không báo lặp lại.

Xem thử (không gửi, không ghi state.json): python canhbao.py --xem
"""
import html
import json
import os
import sys
import unicodedata
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from bantin import (AQI_LEVELS, HANOI, PNJ_GOLD_URL, VN_TZ, fetch, fetch_json, index_history,
                    load_env, send_telegram, vn_num)

# ---- Cấu hình -------------------------------------------------------------
RAIN_LOOKAHEAD_SLOTS = 8   # nhìn trước 8 × 15 phút = 2 tiếng
RAIN_MIN_MM = 0.3          # từ 0,3 mm trong 15 phút (≈1,2 mm/giờ) thì tính là mưa
RAIN_COOLDOWN_HOURS = 3    # báo mưa xong thì im 3 tiếng
AQI_ALERT = 150            # chỉ báo khi AQI vượt mức này và xấu hơn đầu ngày
GOLD_STEP = 1.0            # báo khi giá bán vàng SJC đổi từ 1 triệu đồng/lượng trở lên
INDEX_STEP_PCT = 1.5       # báo khi VN-Index tăng/giảm mỗi 1,5% trong phiên

# Mã cổ phiếu -> (báo khi giá ≤ mức, báo khi giá ≥ mức), đơn vị nghìn đồng; None = bỏ qua
WATCHLIST = {
    # "FPT": (50, 60),
}

KEYWORDS = ["giá xăng", "lãi suất"]
KEYWORD_FEEDS = [
    ("VnExpress", "https://vnexpress.net/rss/tin-moi-nhat.rss"),
    ("Dân trí", "https://dantri.com.vn/rss/home.rss"),
    ("Tuổi Trẻ", "https://tuoitre.vn/rss/tin-moi-nhat.rss"),
    ("Thanh Niên", "https://thanhnien.vn/rss/home.rss"),
]
# ---------------------------------------------------------------------------

STATE_FILE = Path(__file__).with_name("state.json")


def rain_label(mm_per_hour):
    if mm_per_hour < 2.5:
        return "mưa nhỏ"
    if mm_per_hour < 8:
        return "mưa vừa"
    if mm_per_hour < 30:
        return "mưa to"
    return "mưa rất to"


def check_rain(state, now):
    if now.timestamp() - state.get("rain_alert_at", 0) < RAIN_COOLDOWN_HOURS * 3600:
        return [], "mưa: vừa báo, đang chờ"
    lat, lon = HANOI
    q = urllib.parse.urlencode({
        "latitude": lat, "longitude": lon,
        "minutely_15": "precipitation,weather_code",
        "forecast_minutely_15": RAIN_LOOKAHEAD_SLOTS + 1, "timezone": "Asia/Bangkok",
    })
    m = fetch_json(f"https://api.open-meteo.com/v1/forecast?{q}")["minutely_15"]
    slots = list(zip(m["time"], m["precipitation"], m["weather_code"]))

    def wet(mm, code):
        return mm >= RAIN_MIN_MM or code >= 95  # 95+ là dông

    if wet(*slots[0][1:]):
        return [], "mưa: đang mưa"
    for i, (t, mm, code) in enumerate(slots[1:], start=1):
        if wet(mm, code):
            start = datetime.fromisoformat(t).replace(tzinfo=VN_TZ)
            ahead = slots[i:]
            peak = max(s[1] for s in ahead) * 4  # mm/15 phút -> mm/giờ
            storm = any(s[2] >= 95 for s in ahead)
            minutes = max(5, round((start - now).total_seconds() / 300) * 5)
            state["rain_alert_at"] = now.timestamp()
            text = (f"☔ <b>Sắp mưa</b>: khoảng {start:%H:%M} (~{minutes} phút nữa) Hà Nội có "
                    f"{rain_label(peak)}{' kèm dông ⛈️' if storm else ''}. Nhớ mang áo mưa!")
            return [text], f"mưa: báo mưa lúc {start:%H:%M}"
    return [], "mưa: không có trong 2 tiếng tới"


def check_air(state, now):
    lat, lon = HANOI
    q = urllib.parse.urlencode({"latitude": lat, "longitude": lon,
                                "current": "us_aqi", "timezone": "Asia/Bangkok"})
    aqi = fetch_json(f"https://air-quality-api.open-meteo.com/v1/air-quality?{q}")["current"]["us_aqi"]
    level = next(i for i, (limit, _, _) in enumerate(AQI_LEVELS) if aqi <= limit)
    today = now.date().isoformat()
    if state.get("aqi_day") != today:
        # Lần đầu trong ngày chỉ lấy mốc, vì bản tin sáng đã báo AQI rồi
        state["aqi_day"], state["aqi_level"] = today, level
        return [], f"AQI {aqi:.0f}: lấy mốc đầu ngày"
    if aqi <= AQI_ALERT or level <= state["aqi_level"]:
        return [], f"AQI {aqi:.0f}"
    state["aqi_level"] = level
    _, icon, label = AQI_LEVELS[level]
    return ([f"{icon} <b>Không khí chuyển sang mức {label.lower()}</b>: AQI {aqi:.0f}. "
             "Nên đeo khẩu trang, hạn chế ra ngoài."], f"AQI {aqi:.0f}: đã báo")


def check_gold(state, now):
    rows = fetch_json(PNJ_GOLD_URL)["data"]
    price = next(r for r in rows if r["masp"] == "SJC")["giaban"] / 100  # triệu đồng/lượng
    base = state.setdefault("gold_base", price)
    change = price - base
    if abs(change) < GOLD_STEP:
        return [], f"vàng SJC {vn_num(price, 1)} (mốc {vn_num(base, 1)})"
    state["gold_base"] = price
    word, icon = ("tăng", "📈") if change > 0 else ("giảm", "📉")
    return ([f"🪙 <b>Vàng SJC {word} {vn_num(abs(change), 1)} triệu</b> {icon}: giá bán "
             f"{vn_num(base, 1)} → {vn_num(price, 1)} triệu đồng/lượng"],
            f"vàng SJC {vn_num(price, 1)}: đã báo")


def in_session(now):
    return now.weekday() < 5 and (9, 0) <= (now.hour, now.minute) <= (15, 0)


def check_index(state, now):
    if not in_session(now):
        return [], "VN-Index: ngoài giờ giao dịch"
    t, c = index_history("VNINDEX", "VNINDEX")
    if datetime.fromtimestamp(t[-1], timezone.utc).date() != now.date():
        return [], "VN-Index: hôm nay chưa có phiên"
    pct = (c[-1] - c[-2]) / c[-2] * 100
    step = int(abs(pct) // INDEX_STEP_PCT)
    today = now.date().isoformat()
    if state.get("index_day") != today:
        state["index_day"], state["index_step"] = today, 0
    if step <= state["index_step"]:
        return [], f"VN-Index {pct:+.2f}%"
    state["index_step"] = step
    word, icon = ("tăng", "🚀") if pct > 0 else ("giảm", "🔻")
    return ([f"{icon} <b>VN-Index {word} mạnh</b>: {vn_num(c[-1])} điểm "
             f"({vn_num(pct, sign=True)}%)"], f"VN-Index {pct:+.2f}%: đã báo")


def check_watchlist(state, now):
    if not WATCHLIST:
        return [], "cổ phiếu: chưa có mã theo dõi"
    flags = state.setdefault("watch", {})
    alerts, notes = [], []
    for symbol, (low, high) in WATCHLIST.items():
        price = index_history(symbol, symbol)[1][-1]
        notes.append(f"{symbol} {price}")
        for key, hit, target in [(f"{symbol}:low", low is not None and price <= low, low),
                                 (f"{symbol}:high", high is not None and price >= high, high)]:
            # Chỉ báo lúc giá vừa chạm mức; giá quay lại rồi chạm lần nữa thì báo tiếp
            if hit and not flags.get(key):
                word = "xuống" if key.endswith("low") else "lên"
                alerts.append(f"🎯 <b>{symbol} {word} {vn_num(target * 1000, 0)}đ</b>: "
                              f"giá hiện tại {vn_num(price * 1000, 0)}đ")
            flags[key] = hit
    return alerts, "cổ phiếu: " + ", ".join(notes)


def normalize(text):
    return unicodedata.normalize("NFC", text).lower()


def check_news(state, now):
    seen = state.setdefault("news_seen", [])
    keywords = [(k, normalize(k)) for k in KEYWORDS]
    alerts = []
    for source, url in KEYWORD_FEEDS:
        try:
            items = ET.fromstring(fetch(url)).findall(".//item")
        except Exception as e:
            print(f"[lỗi] tin {source}: {e!r}", file=sys.stderr)
            continue
        for item in items:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            keyword = next((k for k, nk in keywords if nk in normalize(title)), None)
            if keyword and link not in seen:
                seen.append(link)
                alerts.append(f"📰 <b>{html.escape(keyword)}</b> · {source}: "
                              f'<a href="{html.escape(link)}">{html.escape(title, quote=False)}</a>')
    del seen[:-300]
    return alerts[:5], f"tin: {len(alerts)} tin mới khớp từ khóa"  # tối đa 5 tin/lần cho đỡ phiền


CHECKS = [check_rain, check_air, check_gold, check_index, check_watchlist, check_news]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    preview = "--xem" in sys.argv
    load_env()
    state = json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else {}
    now = datetime.now(VN_TZ)
    alerts = []
    for check in CHECKS:
        try:
            found, note = check(state, now)
            alerts += found
            print(f"- {note}")
        except Exception as e:
            print(f"[lỗi] {check.__name__}: {e!r}", file=sys.stderr)

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if alerts:
        text = "\n\n".join(alerts)
        if preview or not (token and chat_id):
            print("\n" + text)
        else:
            send_telegram(token, chat_id, text)
            print(f"Đã gửi {len(alerts)} cảnh báo.")
    if not preview:
        STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
