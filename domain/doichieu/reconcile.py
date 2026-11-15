"""Đối chiếu tài sản mỗi tháng: so từng ngăn (tài khoản, sổ tiết kiệm, quỹ, cổ phiếu, nợ…) với số thật, lưu khoản lệch.

- Tài khoản chính: chốt lại số dư; lệch thì hỏi có ghi là khoản chi (hoặc thu) chưa ghi không. Khoản đó vào báo cáo chi
  tiêu nhưng không trừ số dư lần nữa (số dư đã là số thật).
- Quỹ mở còn lệnh chờ khớp hoặc hoán đổi đang chuyển: chưa cho đối chiếu (khớp xong bot tự cộng, nhập trước sẽ bị cộng hai lần).
- Vàng không có ở đây (ít khi đổi, mỗi lần mua có giá riêng): sửa ở 💼 Tài sản.
Ngày 15 (DAY) chọn vì lương (ngày 5), trả nợ (quanh ngày 10), lệnh quỹ cuối tháng và hoán đổi (~ngày 8) đã xong.
Luật thuần: không kho, không chữ hiển thị.
"""
from dataclasses import dataclass
from typing import NamedTuple

DAY = 15
UNITS = ("quy", "cp", "etf", "coin", "ngoaite")  # đối chiếu theo số lượng, không theo tiền


class Slot(NamedTuple):
    """Một ngăn cần đối chiếu: (mục tài sản, giá trị bot đang tính, đơn vị: "đ" hoặc tên đơn vị)."""
    item: dict
    value: float
    unit: str


def unit_of(item):
    """Đơn vị đối chiếu của mục tài sản loại UNITS."""
    return {"quy": "ccq", "cp": "cp", "etf": "ccq", "coin": item["ma"].upper(), "ngoaite": item["ma"]}[item["loai"]]


def color(gap, debt=False):
    """🟢 có nhiều hơn bot tính (nợ thì ngược lại: nợ ít hơn mới tốt)."""
    return "🟢" if (gap > 0) != bool(debt) else "🔴"


def gap_of(real, bot_value, unit):
    """Số lệch (thật − bot tính); tiền lệch dưới 1.000đ coi như khớp."""
    return real - bot_value if unit != "đ" or abs(real - bot_value) >= 1000 else 0


def make_record(item, bot_value, real, unit, gap):
    """Bản ghi một ngăn đã đối chiếu trong tháng."""
    return {"ten": item.get("ten") or item.get("ma"), "bot": bot_value, "that": real,
            "lech": round(gap, 4) if unit != "đ" else round(gap), "don_vi": unit,
            **({"no": True} if item["loai"] == "no" else {})}


def total_gap(done):
    """Tổng lệch tiền của các ngăn đã đối chiếu (không tính nợ, số lượng)."""
    return sum(r["lech"] for r in done.values() if r["don_vi"] == "đ" and not r.get("no"))


def has_pending_order(item, fund_cfg):
    """Quỹ mở còn lệnh chờ khớp hoặc hoán đổi đang chuyển (đối chiếu lúc này sẽ bị cộng hai lần)."""
    if item["loai"] != "quy":
        return False
    main = fund_cfg.get("ma")
    for o in fund_cfg.get("lenh", []):
        if o.get("trang_thai") == "cho" and (o.get("quy") or main) == item["ma"]:
            return True
        if o.get("loai") == "doi" and o.get("trang_thai") in ("cho", "chuyen") and item["ma"] in (main, o.get("quy")):
            return True
    return False


@dataclass
class SetResult:
    """Kết quả ghi số thật của một ngăn."""
    status: str  # "khong_con" | "cho_khop" | "so_am" | "khop" | "lech"
    item: dict | None = None
    bot_value: float = 0
    real: float = 0
    unit: str = "đ"
    gap: float = 0


@dataclass
class GapBooked:
    """Kết quả ghi khoản lệch của tài khoản chính là khoản chi/thu chưa ghi."""
    status: str  # "da_xu_ly" | "ok"
    gap: float = 0


@dataclass
class ScreenState:
    """Dữ liệu màn hình đối chiếu: mỗi ngăn kèm bản ghi đã đối chiếu (hoặc None) và cờ còn lệnh chờ khớp (chỉ tính cho ngăn chưa đối chiếu)."""
    entries: list  # [(Slot, bản ghi hoặc None, còn lệnh chờ khớp: bool)]
    done: dict
