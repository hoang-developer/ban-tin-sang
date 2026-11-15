"""DebtRepo: khoản nợ nằm trong cục tài sản (mục loại "no", khóa keys.ASSETS) nên đọc/ghi qua repo tài sản; thêm cờ nhắc trả nợ."""
from repositories import keys, store
from repositories.taisan import assets as assets_repo

FORTY_DAYS = 40 * 86400


def load():
    """Cục tài sản {"items", "dem", "lailo"}; khoản nợ là các mục có loai == "no"."""
    return assets_repo.load()


def save(data):
    assets_repo.save(data)


def new_id(data):
    return assets_repo.new_id(data)


def claim_reminder(debt_id, ym, stage):
    """True nếu đây là lần đầu nhắc khoản nợ này ở giai đoạn stage (1: ngày hạn, 2: 5 ngày sau) của tháng ym."""
    return store.put_new(keys.debt_reminder(debt_id, ym, stage), True, FORTY_DAYS)
