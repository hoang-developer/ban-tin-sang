"""Chữ của bot bản tin: lời nhắc cần kho, câu hỏi đoán xanh/đỏ, mức giá báo."""
from domain.lenh.rules import GUESS_DEADLINE
from presentation.chungkhoan.view import dong
NEED_STORE = "⚠️ Tính năng này cần kho dữ liệu. Gõ /caidat để xem cách cài."
GUESS_TEXT = ("🎯 <b>Đoán nhanh</b>: hôm nay VN-Index đóng cửa <b>xanh</b> hay <b>đỏ</b>?\n"
              f"<i>Nhận đoán tới {GUESS_DEADLINE[0]}:{GUESS_DEADLINE[1]:02d} · 15h bot chấm điểm</i>")
GUESS_BUTTONS = [[("🟢 Xanh", "doan:xanh"), ("🔴 Đỏ", "doan:do")]]
GUESS_LABEL = {"xanh": "🟢 Xanh", "do": "🔴 Đỏ"}


def level_text(levels):
    low, high = levels
    parts = ([f"≤ {dong(low * 1000)}"] if low is not None else []) + \
            ([f"≥ {dong(high * 1000)}"] if high is not None else [])
    return f" · báo khi {' hoặc '.join(parts)}" if parts else ""
