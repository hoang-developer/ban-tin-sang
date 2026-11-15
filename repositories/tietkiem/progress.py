"""ProgressRepo: cấu hình "tiết kiệm từ khi dùng bot" (khóa keys.SAVINGS) và cờ mừng mốc thành tích.

{"moc", "bat_dau", "khong_tieu": [ngày ISO], "nhac": bool, "da_chuyen": đồng}
"""
from domain.tietkiem.progress import with_defaults
from repositories import keys, store

FIVE_YEARS = 5 * 365 * 86400


def load():
    return with_defaults(store.get(keys.SAVINGS, {}))


def save(cfg):
    store.put(keys.SAVINGS, cfg)


def claim_streak_mark(n):
    """True nếu đây là lần đầu báo mốc chuỗi n ngày (và đánh dấu đã báo)."""
    return store.put_new(keys.savings_streak_milestone(n), True, FIVE_YEARS)


def claim_saved_mark(m):
    """True nếu đây là lần đầu báo mốc đã bớt m đồng (và đánh dấu đã báo)."""
    return store.put_new(keys.savings_saved_milestone(m), True, FIVE_YEARS)
