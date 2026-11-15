"""Các bước kiểm tra cảnh báo: lấy số liệu, hỏi luật, ghi nhớ điều đã báo vào state.

Mỗi bước trả (danh sách cảnh báo dạng dict, dòng ghi chú để in nhật ký); dạng chữ do presentation lo.
"""
import sys
from datetime import datetime

from domain.bantin.weather import AQI_LEVELS, HANOI
from domain.canhbao import rules
from domain.common.format import vn_num
from infrastructure import marketdata, openmeteo
from services.bantin.data import index_history


def rain_outlook(now, place=HANOI):
    """Mưa trong 2 tiếng tới: (đang mưa, giờ cơn mưa tới bắt đầu, {minutes, peak, storm})."""
    slots = openmeteo.minutely(place, rules.RAIN_LOOKAHEAD_SLOTS + 1)
    return rules.rain_outlook(slots, now)


def check_rain(state, now):
    if rules.rain_cooling(state, now):
        return [], "mưa: vừa báo, đang chờ"
    raining, start, info = rain_outlook(now)
    if raining:
        return [], "mưa: đang mưa"
    if not start:
        return [], "mưa: không có trong 2 tiếng tới"
    rules.mark_rain(state, now)
    return [{"kind": "rain", "start": start, **info}], f"mưa: báo mưa lúc {start:%H:%M}"


def check_air(state, now):
    aqi = openmeteo.air_now(HANOI, "us_aqi")["us_aqi"]
    what, level = rules.air_step(state, now, aqi)
    if what == "mốc":
        return [], f"AQI {aqi:.0f}: lấy mốc đầu ngày"
    if what == "im":
        return [], f"AQI {aqi:.0f}"
    _, icon, label = AQI_LEVELS[level]
    return [{"kind": "air", "icon": icon, "label": label, "aqi": aqi}], f"AQI {aqi:.0f}: đã báo"


def check_gold(state, now):
    price = marketdata.pnj_gold()["SJC"]["giaban"] / 100  # triệu đồng/lượng
    base, change, alert = rules.gold_step(state, price)
    if not alert:
        return [], f"vàng SJC {vn_num(price, 1)} (mốc {vn_num(base, 1)})"
    return [{"kind": "gold", "base": base, "price": price, "change": change}], f"vàng SJC {vn_num(price, 1)}: đã báo"


def check_index(state, now):
    if not rules.in_session(now):
        return [], "VN-Index: ngoài giờ giao dịch"
    t, c = index_history("VNINDEX", "VNINDEX")
    got = rules.index_alert(state, now, t, c)
    if got is None:
        return [], "VN-Index: hôm nay chưa có phiên"
    pct, alert = got
    if not alert:
        return [], f"VN-Index {pct:+.2f}%"
    return [{"kind": "index", "close": c[-1], "pct": pct}], f"VN-Index {pct:+.2f}%: đã báo"


def check_watchlist(state, now, watchlist=None):
    watchlist = rules.WATCHLIST if watchlist is None else watchlist
    if not watchlist:
        return [], "cổ phiếu: chưa có mã theo dõi"
    alerts, notes = [], []
    for symbol, (low, high) in watchlist.items():
        price = index_history(symbol, symbol)[1][-1]
        notes.append(f"{symbol} {price}")
        alerts += [{"kind": "watch", "symbol": symbol, "word": word, "target": target, "price": price}
                   for word, target in rules.watch_hits(state, symbol, price, low, high)]
    return alerts, "cổ phiếu: " + ", ".join(notes)


def check_news(state, now, keywords=None):
    state.setdefault("news_seen", [])
    keywords = [(k, rules.normalize(k)) for k in (rules.KEYWORDS if keywords is None else keywords)]
    alerts = []
    for source, url in rules.KEYWORD_FEEDS:
        try:
            items = marketdata.feed_items(url, None)
        except Exception as e:
            print(f"[lỗi] tin {source}: {e!r}", file=sys.stderr)
            continue
        found = [((i.findtext("title") or "").strip(), (i.findtext("link") or "").strip()) for i in items]
        alerts += [{"kind": "news", "keyword": k, "source": s, "link": link, "title": title}
                   for k, s, link, title in rules.news_hits(state, source, found, keywords)]
    rules.trim_seen(state)
    return alerts[:5], f"tin: {len(alerts)} tin mới khớp từ khóa"  # tối đa 5 tin/lần cho đỡ phiền


CHECKS = [check_rain, check_air, check_gold, check_index, check_watchlist, check_news]


def run(state, now, watchlist=None, keywords=None):
    """Chạy mọi bước kiểm tra, cập nhật state tại chỗ; trả về các cảnh báo (dict) cần gửi.

    watchlist, keywords thay cho WATCHLIST, KEYWORDS khi lấy từ kho dữ liệu của bot.
    """
    extra = {}
    if watchlist is not None:
        extra[check_watchlist] = {"watchlist": watchlist}
    if keywords is not None:
        extra[check_news] = {"keywords": keywords}
    alerts = []
    for check in CHECKS:
        try:
            found, note = check(state, now, **extra.get(check, {}))
            alerts += found
            print(f"- {note}")
        except Exception as e:
            print(f"[lỗi] {check.__name__}: {e!r}", file=sys.stderr)
    return alerts
