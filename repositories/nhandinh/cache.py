"""Nhận định trong phiên: dữ liệu ít đổi giữ tạm trong kho, và công tắc tắt/bật tự gửi."""
import sys

from infrastructure import kho
from repositories import keys


def remembered(key, seconds, fetch):
    """Dữ liệu ít đổi (danh sách ngành, mã HOSE, khuyến nghị): giữ trong kho một lúc; không có kho thì lấy luôn."""
    if kho.ready():
        try:
            saved = kho.get(key)
            if saved is not None:
                return saved
        except Exception as e:
            print(f"[lỗi] đọc kho {key}: {e!r}", file=sys.stderr)
    value = fetch()
    if kho.ready():
        try:
            kho.put(key, value, seconds)
        except Exception as e:
            print(f"[lỗi] ghi kho {key}: {e!r}", file=sys.stderr)
    return value


def auto_off():
    """Đã tắt nhận định tự gửi trong phiên (không có kho thì coi như chưa tắt)."""
    return bool(kho.ready() and kho.get(keys.ANALYSIS_OFF))


def set_auto(on):
    if on:
        kho.delete(keys.ANALYSIS_OFF)
    else:
        kho.put(keys.ANALYSIS_OFF, True)
