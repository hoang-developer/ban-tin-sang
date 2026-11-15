"""Thời tiết theo nơi cho bot: /thoitiet, /thoitiet Đà Nẵng, hoặc gửi vị trí.

Xem thử: python -m interface.thoitiet.report Đà Nẵng
"""
import sys

from domain.bantin.weather import HANOI, tips
from infrastructure import clock
from interface.bantin.bulletin import section, weather
from interface.canhbao.runner import rain_outlook
from presentation.thoitiet import view
from services.bantin.data import hourly
from services.thoitiet.place import find_place  # noqa: F401


def rain_line(now, place, name):
    return view.rain_line(*rain_outlook(now, place, name))


def report(place=HANOI, name="Hà Nội"):
    """Thời tiết lúc này, mưa 2 tiếng tới và gợi ý trong ngày ở một nơi."""
    now = clock.now_vn()

    def body():
        lines = weather(place)
        for name_, part in [("mưa 2 tiếng tới", lambda: [rain_line(now, place, name)]),
                            ("gợi ý", lambda: tips(hourly(place), now.date(), now.replace(tzinfo=None)))]:
            try:
                lines += part()
            except Exception as e:  # thiếu một phần thì vẫn gửi phần còn lại
                print(f"[lỗi] {name_}: {e!r}", file=sys.stderr)
        return lines

    return section(view.title(name, now), body)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    name = " ".join(sys.argv[1:])
    found = find_place(name) if name else (HANOI, "Hà Nội")
    print(report(*found) if found else f"Không tìm thấy nơi nào tên {name}")


if __name__ == "__main__":
    main()
