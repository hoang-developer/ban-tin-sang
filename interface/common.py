"""Phần dùng chung của lớp interface: chặn khi chưa nối kho, đọc nút bấm, bỏ nút đã bấm."""
import functools
import re

import sochitieu as ct  # module cũ ở gốc: NEED_STORE, hàng nút của tin
from infrastructure import kho

TOAST_MAX = 190  # Telegram chỉ cho thông báo nhỏ khi bấm nút dài tối đa chừng này ký tự


def ready():
    return kho.ready()


def needs_store(fn):
    """Chưa nối kho dữ liệu thì trả câu hướng dẫn thay vì chạy hàm."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if not kho.ready():
            return ct.NEED_STORE
        return fn(*args, **kwargs)
    return wrapper


def title_starts(message, *prefixes):
    """Tin chứa nút bấm có chữ đầu là một trong prefixes không (biết nút nằm trên tin nào)."""
    return (message.get("text") or "").startswith(prefixes)


def without_buttons(message, prefix):
    """Hàng nút của tin sau khi bỏ các nút có callback bắt đầu bằng prefix (hàng rỗng bỏ luôn)."""
    rows = [[b for b in row if not b[1].startswith(prefix)] for row in ct.keyboard_rows(message)]
    return [row for row in rows if row]


def without_rows(message, prefixes):
    """Hàng nút của tin sau khi bỏ cả hàng nếu có nút nào bắt đầu bằng prefixes."""
    return [row for row in ct.keyboard_rows(message) if not any(d.startswith(prefixes) for _, d in row)]


def clip(text):
    return text[:TOAST_MAX]


def strip_tags(text):
    return re.sub(r"<[^>]+>", "", text)
