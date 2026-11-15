"""Bản tin sáng gửi qua Telegram: thời tiết Hà Nội, giá vàng, chứng khoán, tin tức.

Chạy: python -m interface.bantin.bulletin
Cần biến môi trường TELEGRAM_BOT_TOKEN và TELEGRAM_CHAT_ID (hoặc file .env ở thư mục gốc).
Thiếu thì chỉ in bản tin ra màn hình để xem thử.
Các hàm giữ tên cũ (weather, gold, stocks, news...) để bot và lịch chạy dùng lại.
"""
import os
import sys
from pathlib import Path

from domain.bantin.weather import HANOI
from infrastructure import clock
from infrastructure import telegram as tg
from presentation.bantin import view
from presentation.bantin.view import BUTTONS, lunar_line, section  # noqa: F401
from services.bantin import data


def weather(place=HANOI, day=0):
    """Thời tiết một ngày ở tọa độ place: day=0 là hôm nay (kèm nhiệt độ lúc này và AQI), 1 là ngày mai."""
    w, air = data.weather_data(place, day)
    return view.weather_lines(w, day) + (view.air_lines(air) if air else [])


def gold():
    return view.gold_lines(data.gold_prices())


def stocks():
    return view.stock_lines(data.index_rows())


def news():
    return view.news_lines(data.news_feeds())


def build_message():
    return "\n\n".join([
        view.header(clock.now_vn()),
        section("🌤️ Thời tiết Hà Nội", weather),
        section("💡 Gợi ý hôm nay", data.today_tips),
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
    env_file = Path(__file__).resolve().parents[2] / ".env"
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
