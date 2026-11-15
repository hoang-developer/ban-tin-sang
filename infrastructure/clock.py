"""Đồng hồ giờ Việt Nam: một chỗ duy nhất để lấy "bây giờ" (bài test thay đồng hồ ở đây)."""
from datetime import datetime, timedelta, timezone

VN_TZ = timezone(timedelta(hours=7))  # Việt Nam không đổi giờ mùa hè


def now_vn():
    return datetime.now(VN_TZ)
