"""Chữ của bản tin sáng: thời tiết, giá vàng, chứng khoán, tin nổi bật, dòng âm lịch, các mục ghép lại."""
import html
import sys
from datetime import timedelta

from domain.amlich import lunar as amlich
from domain.bantin import weather as rules
from domain.common.dates import WEEKDAYS
from domain.common.format import vn_num

# Nút dưới bản tin; bấm thì bot trên Vercel xử lý (interface/bot)
BUTTONS = [[("🔄 Cập nhật", "bantin")], [("📈 VN30", "vn30"), ("🌧️ Mưa lúc nào?", "mua")]]


def weather_lines(w, day=0):
    """Dòng thời tiết một ngày từ dữ liệu dự báo; day=0 kèm nhiệt độ lúc này."""
    d = w["daily"]
    icon, desc = rules.describe(d["weather_code"][day])
    rain = d["precipitation_probability_max"][day]
    now = f" (bây giờ {w['current']['temperature_2m']:.0f}°C)" if day == 0 else ""
    return [
        f"{icon} {desc}, {d['temperature_2m_min'][day]:.0f}–{d['temperature_2m_max'][day]:.0f}°C{now}",
        f"☔ Khả năng mưa: {rain}%" + (" – nhớ mang ô!" if rain >= 50 else ""),
    ]


def air_lines(c):
    aqi = c["us_aqi"]
    icon, label = rules.aqi_level(aqi)
    lines = [f"{icon} Không khí: AQI {aqi:.0f} – {label} (PM2.5: {c['pm2_5']:.0f} µg/m³)"]
    if aqi > 100:
        lines.append("😷 Nên đeo khẩu trang khi ra ngoài")
    return lines


def gold_lines(p):
    def row(name, prices):
        buy, sell = prices
        return f"{name}: mua <b>{vn_num(buy, 1)}</b> – bán <b>{vn_num(sell, 1)}</b>"

    return [row("Miếng SJC", p["sjc"]), row(p["nhan_ten"], p["nhan"]),
            f"<i>triệu đồng/lượng · {p['nguon']}</i>"]


def stock_lines(rows):
    lines, session = [], None
    for name, close, change, pct, day in rows:
        if close is None:
            lines.append(f"⚪ {name}: <i>không lấy được</i>")
            continue
        icon = "🟢" if change > 0 else "🔴" if change < 0 else "🟡"
        lines.append(f"{icon} {name}: <b>{vn_num(close)}</b>  "
                     f"{vn_num(change, sign=True)} ({vn_num(pct, sign=True)}%)")
        session = session or day
    if session:
        lines.insert(0, f"<i>Phiên {session}</i>")
    return lines


def news_lines(feeds):
    lines = []
    for source, items in feeds:
        if items is None:
            lines.append(f"<i>{source}: không lấy được tin</i>")
            continue
        lines.append(f"<u>{source}</u>")
        for title, link in items:
            lines.append(f'• <a href="{html.escape(link, quote=True)}">{html.escape(title, quote=False)}</a>')
    return lines


def section(title, fn):
    """Một mục của bản tin; lấy dữ liệu lỗi thì mục đó báo không lấy được, các mục khác vẫn gửi."""
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


def header(today):
    return (f"☀️ <b>Bản tin sáng – {WEEKDAYS[today.weekday()]}, {today:%d/%m/%Y}</b>\n"
            f"{lunar_line(today.date())}")
