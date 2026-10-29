"""Thời tiết theo nơi cho bot: /thoitiet, /thoitiet Đà Nẵng, hoặc gửi vị trí.

Xem thử: python thoitiet.py Đà Nẵng
"""
import sys
import urllib.parse
from datetime import datetime

from bantin import HANOI, VN_TZ, fetch_json, hourly, section, tips, weather
from canhbao import rain_outlook


def find_place(name):
    """Tên địa danh -> ((vĩ độ, kinh độ), tên hiển thị); None nếu không tìm thấy. Ưu tiên Việt Nam."""
    for extra in ({"countryCode": "VN"}, {}):
        q = urllib.parse.urlencode({"name": name, "count": 1, "language": "vi", **extra})
        found = fetch_json(f"https://geocoding-api.open-meteo.com/v1/search?{q}").get("results")
        if found:
            r = found[0]
            label = r["name"]
            if r.get("admin1") and r["admin1"] != r["name"]:
                label += f", {r['admin1']}"
            if r.get("country_code") != "VN":
                label += f", {r.get('country', '')}"
            return (r["latitude"], r["longitude"]), label
    return None


def rain_line(now, place, name):
    raining, start, desc = rain_outlook(now, place, name)
    return "🌧️ Đang mưa" if raining else f"⚠️ Sắp mưa {desc}" if start else "🌂 2 tiếng tới không mưa"


def report(place=HANOI, name="Hà Nội"):
    """Thời tiết lúc này, mưa 2 tiếng tới và gợi ý trong ngày ở một nơi."""
    now = datetime.now(VN_TZ)

    def body():
        lines = weather(place)
        for name_, part in [("mưa 2 tiếng tới", lambda: [rain_line(now, place, name)]),
                            ("gợi ý", lambda: tips(hourly(place), now.date(), now.replace(tzinfo=None)))]:
            try:
                lines += part()
            except Exception as e:  # thiếu một phần thì vẫn gửi phần còn lại
                print(f"[lỗi] {name_}: {e!r}", file=sys.stderr)
        return lines

    return section(f"🌤️ Thời tiết {name} – {now:%H:%M}", body)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    name = " ".join(sys.argv[1:])
    found = find_place(name) if name else (HANOI, "Hà Nội")
    print(report(*found) if found else f"Không tìm thấy nơi nào tên {name}")


if __name__ == "__main__":
    main()
