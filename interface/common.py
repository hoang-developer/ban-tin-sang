"""Phần dùng chung của lớp interface: chặn khi chưa nối kho, đọc nút bấm, bỏ nút đã bấm."""
import functools
import re

from infrastructure import kho
from presentation.chitieu.view import NEED_STORE

TOAST_MAX = 190  # Telegram chỉ cho thông báo nhỏ khi bấm nút dài tối đa chừng này ký tự


def ready():
    return kho.ready()


def needs_store(fn):
    """Chưa nối kho dữ liệu thì trả câu hướng dẫn thay vì chạy hàm."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if not kho.ready():
            return NEED_STORE
        return fn(*args, **kwargs)
    return wrapper


def title_starts(message, *prefixes):
    """Tin chứa nút bấm có chữ đầu là một trong prefixes không (biết nút nằm trên tin nào)."""
    return (message.get("text") or "").startswith(prefixes)


def without_buttons(message, prefix):
    """Hàng nút của tin sau khi bỏ các nút có callback bắt đầu bằng prefix (hàng rỗng bỏ luôn)."""
    rows = [[b for b in row if not b[1].startswith(prefix)] for row in keyboard_rows(message)]
    return [row for row in rows if row]


def without_rows(message, prefixes):
    """Hàng nút của tin sau khi bỏ cả hàng nếu có nút nào bắt đầu bằng prefixes."""
    return [row for row in keyboard_rows(message) if not any(d.startswith(prefixes) for _, d in row)]


def clip(text):
    return text[:TOAST_MAX]


def strip_tags(text):
    return re.sub(r"<[^>]+>", "", text)


def keyboard_rows(message):
    return [[(b["text"], b.get("callback_data", "")) for b in row]
            for row in (message.get("reply_markup") or {}).get("inline_keyboard", [])]


def from_menu(message):
    """Tin này mở từ menu (có nút ⬅️ Menu): vẽ lại thì giữ nút menu."""
    return any(data.startswith("m:") for row in keyboard_rows(message) for _, data in row)
