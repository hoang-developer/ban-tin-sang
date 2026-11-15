"""Luật cảnh báo tức thì: khi nào báo mưa, không khí xấu đi, vàng và VN-Index biến động, mã chạm giá, tin có từ khóa.

Mỗi hàm nhận trạng thái đã báo (state, một dict lưu giữa các lần chạy) và sửa tại chỗ; không gọi mạng, không in.
"""
import unicodedata
from datetime import datetime, timezone

from domain.bantin.weather import AQI_LEVELS
from domain.common.dates import VN_TZ

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


def rain_label(mm_per_hour):
    if mm_per_hour < 2.5:
        return "mưa nhỏ"
    if mm_per_hour < 8:
        return "mưa vừa"
    if mm_per_hour < 30:
        return "mưa to"
    return "mưa rất to"


def rain_outlook(slots, now):
    """Từ các mốc 15 phút [(giờ, mm, mã)]: (đang mưa, giờ cơn mưa tới bắt đầu, {minutes, peak, storm}).

    Trời khô cả 2 tiếng thì hai giá trị sau là None; peak tính mm/giờ.
    """
    def wet(mm, code):
        return mm >= RAIN_MIN_MM or code >= 95  # 95+ là dông

    if wet(*slots[0][1:]):
        return True, None, None
    for i, (t, mm, code) in enumerate(slots[1:], start=1):
        if wet(mm, code):
            start = datetime.fromisoformat(t).replace(tzinfo=VN_TZ)
            ahead = slots[i:]
            peak = max(s[1] for s in ahead) * 4  # mm/15 phút -> mm/giờ
            storm = any(s[2] >= 95 for s in ahead)
            minutes = max(5, round((start - now).total_seconds() / 300) * 5)
            return False, start, {"minutes": minutes, "peak": peak, "storm": storm}
    return False, None, None


def rain_cooling(state, now):
    """Vừa báo mưa chưa đủ giờ nghỉ."""
    return now.timestamp() - state.get("rain_alert_at", 0) < RAIN_COOLDOWN_HOURS * 3600


def mark_rain(state, now):
    state["rain_alert_at"] = now.timestamp()


def air_level(aqi):
    """Chỉ số mức trong AQI_LEVELS ứng với AQI."""
    return next(i for i, (limit, _, _) in enumerate(AQI_LEVELS) if aqi <= limit)


def air_step(state, now, aqi):
    """('mốc', mức) lần đầu trong ngày (chỉ lấy mốc, vì bản tin sáng đã báo AQI); ('im', mức) hoặc ('báo', mức)."""
    level = air_level(aqi)
    today = now.date().isoformat()
    if state.get("aqi_day") != today:
        state["aqi_day"], state["aqi_level"] = today, level
        return "mốc", level
    if aqi <= AQI_ALERT or level <= state["aqi_level"]:
        return "im", level
    state["aqi_level"] = level
    return "báo", level


def gold_step(state, price):
    """(mốc, đổi so với mốc, có báo không); đã báo thì dời mốc về giá mới."""
    base = state.setdefault("gold_base", price)
    change = price - base
    if abs(change) < GOLD_STEP:
        return base, change, False
    state["gold_base"] = price
    return base, change, True


def in_session(now):
    return now.weekday() < 5 and (9, 0) <= (now.hour, now.minute) <= (15, 0)


def index_alert(state, now, t, c):
    """(% đổi trong phiên, có báo không) với lịch sử đóng cửa (t, c); None nếu hôm nay chưa có phiên."""
    if datetime.fromtimestamp(t[-1], timezone.utc).date() != now.date():
        return None
    pct = (c[-1] - c[-2]) / c[-2] * 100
    step = int(abs(pct) // INDEX_STEP_PCT)
    today = now.date().isoformat()
    if state.get("index_day") != today:
        state["index_day"], state["index_step"] = today, 0
    if step <= state["index_step"]:
        return pct, False
    state["index_step"] = step
    return pct, True


def watch_hits(state, symbol, price, low, high):
    """Các mức vừa chạm của một mã: [("xuống"|"lên", mức)]. Chỉ báo lúc giá vừa chạm;
    giá quay lại rồi chạm lần nữa thì báo tiếp."""
    flags = state.setdefault("watch", {})
    hits = []
    for key, hit, target in [(f"{symbol}:low", low is not None and price <= low, low),
                             (f"{symbol}:high", high is not None and price >= high, high)]:
        if hit and not flags.get(key):
            hits.append(("xuống" if key.endswith("low") else "lên", target))
        flags[key] = hit
    return hits


def normalize(text):
    return unicodedata.normalize("NFC", text).lower()


def news_hits(state, source, items, keywords):
    """Tin trong `items` [(tiêu đề, link)] khớp từ khóa chưa báo: [(từ khóa, nguồn, link, tiêu đề)].
    keywords là [(từ khóa, dạng chuẩn hóa)]; link đã báo được ghi vào state['news_seen']."""
    seen = state.setdefault("news_seen", [])
    hits = []
    for title, link in items:
        keyword = next((k for k, nk in keywords if nk in normalize(title)), None)
        if keyword and link not in seen:
            seen.append(link)
            hits.append((keyword, source, link, title))
    return hits


def trim_seen(state):
    del state.setdefault("news_seen", [])[:-300]
