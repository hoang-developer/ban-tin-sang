"""Thời tiết cho bản tin: mã thời tiết, mức không khí, gợi ý mặc gì / phơi đồ / chạy bộ (tính thuần)."""
HANOI = (21.0285, 105.8542)

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

# Nhiệt độ cảm nhận buổi sáng dưới mức này -> nên mặc gì
CLOTHES = [(12, "áo khoác dày, khăn quàng"), (17, "áo khoác ấm"), (21, "áo khoác mỏng"),
           (25, "áo dài tay mỏng"), (30, "áo cộc tay"), (float("inf"), "đồ mỏng thoáng mát")]


def describe(code):
    """Mã thời tiết -> (biểu tượng, mô tả)."""
    return WEATHER.get(code, ("🌡️", "Không rõ"))


def aqi_level(aqi):
    """AQI -> (biểu tượng, mức)."""
    return next((i, lbl) for limit, i, lbl in AQI_LEVELS if aqi <= limit)


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
