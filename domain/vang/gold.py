"""Ví vàng: các lần mua (lô) và quy tắc bán lấy lô cũ trước."""
from dataclasses import dataclass, field, replace

CORE_KEYS = ("loai", "luong", "gia", "ngay")


@dataclass
class GoldLot:
    """Một lần mua vàng. JSON trong kho: {"loai", "luong", "gia", "ngay"?}."""
    kind: str  # "loai": "sjc" (miếng SJC) | "nhan" (nhẫn)
    taels: float  # "luong": số lượng, đơn vị lượng (1 lượng = 10 chỉ)
    price: float | None = None  # "gia": giá mua, triệu đồng một lượng; None nếu không ghi
    bought: str | None = None  # "ngay": ngày mua ISO; None nếu không ghi
    extra: dict = field(default_factory=dict)  # khóa lạ trong JSON: giữ nguyên khi ghi lại

    @classmethod
    def from_dict(cls, data):
        return cls(kind=data["loai"], taels=data["luong"], price=data.get("gia"), bought=data.get("ngay"),
                   extra={k: v for k, v in data.items() if k not in CORE_KEYS})

    def to_dict(self):
        out = {"loai": self.kind, "luong": self.taels, "gia": self.price}
        if self.bought:
            out["ngay"] = self.bought
        out.update(self.extra)
        return out

    @property
    def chi(self):
        return self.taels * 10


@dataclass
class FifoSale:
    lots: list  # các lô còn lại sau khi bán, giữ thứ tự cũ, bỏ lô đã hết
    cost: float  # vốn của phần đã bán, đồng (lô không ghi giá mua tính 0)


def holdings_chi(lots, kind=None):
    """Tổng số chỉ đang giữ (của loại kind nếu có)."""
    return sum(g.taels for g in lots if not kind or g.kind == kind) * 10


def sell_fifo(lots, chi, kind=None):
    """Bán chi chỉ, lấy dần từ lô mua cũ nhất (lô không ghi ngày xếp đầu), chỉ trong loại kind nếu có.

    Người gọi đã kiểm tra đủ vàng. Không sửa lots.
    """
    rest = [replace(g) for g in lots]
    pool = [g for g in rest if not kind or g.kind == kind]
    left, cost = chi / 10, 0.0
    for g in sorted(pool, key=lambda x: x.bought or ""):
        take = min(g.taels, left)
        cost += take * (g.price or 0) * 1e6
        g.taels = round(g.taels - take, 6)
        left = round(left - take, 6)
        if left <= 0:
            break
    return FifoSale([g for g in rest if g.taels > 1e-6], cost)
