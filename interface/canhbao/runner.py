"""Cảnh báo tức thì qua Telegram: sắp mưa, không khí xấu đi, vàng và chứng khoán biến động,
tin tức có từ khóa bạn quan tâm.

Chạy mỗi 30 phút (6h–22h) bằng GitHub Actions và chỉ nhắn khi có chuyện.
Những gì đã báo được ghi vào state.json để không báo lặp lại.

Xem thử (không gửi, không ghi state.json): python -m interface.canhbao.runner --xem
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from domain.bantin.weather import HANOI
from domain.canhbao.rules import KEYWORD_FEEDS, KEYWORDS, WATCHLIST, normalize  # noqa: F401
from infrastructure.clock import VN_TZ
from interface.bantin.bulletin import load_env, send_telegram
from presentation.canhbao import view
from services.canhbao import checks

STATE_FILE = Path(__file__).resolve().parents[2] / "state.json"


def rain_outlook(now, place=HANOI, name="Hà Nội"):
    """Mưa trong 2 tiếng tới: (đang mưa, giờ cơn mưa tới bắt đầu, mô tả cơn mưa tới); khô thì hai giá trị sau là None."""
    raining, start, info = checks.rain_outlook(now, place)
    return raining, start, (view.rain_desc(info, start, name) if start else None)


def run(state, now, watchlist=None, keywords=None):
    """Chạy mọi bước kiểm tra, cập nhật state tại chỗ; trả về các tin cảnh báo cần gửi.

    watchlist, keywords thay cho WATCHLIST, KEYWORDS khi lấy từ kho dữ liệu của bot.
    """
    return [view.alert_text(a) for a in checks.run(state, now, watchlist, keywords)]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    preview = "--xem" in sys.argv
    load_env()
    state = json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else {}
    alerts = run(state, datetime.now(VN_TZ))

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
