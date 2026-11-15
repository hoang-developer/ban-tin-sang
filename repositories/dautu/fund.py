"""FundRepo: cấu hình đầu tư quỹ mở định kỳ (khóa keys.FUND): mã quỹ, kế hoạch, lệnh. Dạng dict tạm thời;
NAV và thông tin quỹ thêm vào đây ở bước 6 (plan.md)."""
from repositories import keys, store


def load():
    return store.get(keys.FUND, {}) or {}


def save(cfg):
    store.put(keys.FUND, cfg)
