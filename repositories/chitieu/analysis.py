"""AnalysisRepo: nhóm tính là chi tiêu hằng ngày (keys.DAILY_GROUPS) và đánh dấu đã báo cảnh báo tối (mỗi chuyện một lần
mỗi tuần)."""
from infrastructure import kho
from repositories import keys

WEEK = 7 * 86400


def daily_groups():
    """Các nhóm người dùng chọn làm chi tiêu hằng ngày, None nếu chưa chọn hoặc chưa nối kho."""
    return kho.get(keys.DAILY_GROUPS) if kho.ready() else None


def save_daily_groups(codes):
    kho.put(keys.DAILY_GROUPS, codes)


def reset_daily_groups():
    kho.delete(keys.DAILY_GROUPS)


def claim_rise(code):
    """True nếu tuần này chưa báo nhóm này tăng vọt (đánh dấu đã báo)."""
    return kho.put_new(keys.alert_rise(code), True, WEEK)


def claim_budget(code, month):
    """True nếu tuần này chưa báo nhóm này sắp vượt ngân sách của tháng month ("2026-10")."""
    return kho.put_new(keys.alert_budget(code, month), True, WEEK)
