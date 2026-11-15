"""Chữ của lệnh /thoitiet."""


def rain_line(raining, start, desc):
    return "🌧️ Đang mưa" if raining else f"⚠️ Sắp mưa {desc}" if start else "🌂 2 tiếng tới không mưa"


def title(name, now):
    return f"🌤️ Thời tiết {name} – {now:%H:%M}"
