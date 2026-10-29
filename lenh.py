"""Các lệnh bot Telegram trả lời; phần nhận tin nhắn nằm ở api/telegram.py.

Xem thử: python lenh.py /vang
         python lenh.py /stock FPT
"""
import sys
from datetime import datetime

from bantin import VN_TZ, build_message, gold, section, weather
from canhbao import rain_outlook
from chungkhoan import stock_command


def weather_now():
    lines = weather()
    try:
        raining, start, desc = rain_outlook(datetime.now(VN_TZ))
        lines.append("🌧️ Đang mưa" if raining else f"⚠️ Sắp mưa {desc}" if start
                     else "🌂 2 tiếng tới không mưa")
    except Exception as e:
        print(f"[lỗi] mưa 2 tiếng tới: {e!r}", file=sys.stderr)
    return lines


def thoitiet(args):
    return section(f"🌤️ Thời tiết Hà Nội – {datetime.now(VN_TZ):%H:%M}", weather_now)


# tên lệnh -> (mô tả trong menu Telegram, hàm nhận các tham số sau lệnh và trả về tin nhắn HTML)
COMMANDS = {
    "stock": ("Phiên chứng khoán; /stock FPT để xem một mã", stock_command),
    "vang": ("Giá vàng SJC", lambda args: section("🪙 Giá vàng", gold)),
    "thoitiet": ("Thời tiết, không khí, mưa 2 tiếng tới ở Hà Nội", thoitiet),
    "bantin": ("Gửi lại bản tin sáng", lambda args: build_message()),
}
HELP = "Lệnh của bot:\n" + "\n".join(f"/{name} – {desc}" for name, (desc, _) in COMMANDS.items())
MENU = [{"command": name, "description": desc} for name, (desc, _) in COMMANDS.items()]


def answer(text):
    """Tin trả lời cho một tin nhắn của chủ bot; None nếu tin đó không phải lệnh."""
    parts = text.split()
    if not parts or not parts[0].startswith("/"):
        return None
    name = parts[0][1:].split("@")[0].lower()  # trong nhóm chat lệnh có dạng /stock@TenBot
    if name in COMMANDS:
        return COMMANDS[name][1](parts[1:])
    return HELP  # /start, /help hay gõ sai tên lệnh thì gửi hướng dẫn


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    print(answer(" ".join(sys.argv[1:])) or "(không phải lệnh)")


if __name__ == "__main__":
    main()
