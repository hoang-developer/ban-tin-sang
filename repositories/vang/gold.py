"""GoldRepo: ví vàng (khóa keys.GOLD, dùng chung với bot bản tin). Thứ tự danh sách là mã dòng ("v0", "v1"…)
ở màn hình tài sản, nên mọi thao tác giữ nguyên thứ tự."""
from domain.vang.gold import GoldLot
from repositories import keys, store


def load():
    return [GoldLot.from_dict(d) for d in store.get(keys.GOLD, []) or []]


def save(lots):
    store.put(keys.GOLD, [g.to_dict() for g in lots])


def add(lot):
    lots = load()
    lots.append(lot)
    save(lots)


def remove_at(index):
    """Xóa lô thứ index; False nếu không có."""
    lots = load()
    if not 0 <= index < len(lots):
        return False
    lots.pop(index)
    save(lots)
    return True


def clear():
    save([])
