"""ReserveRepo: cấu hình quỹ dự phòng (khóa keys.RESERVE).

{"thang": số tháng mục tiêu, "han": đạt trong bao nhiêu tháng, "bat_dau": ngày, "chi": tự đặt,
 "nap": {"YYYY-MM": tổng đã nạp trong tháng}}
"""
from repositories import keys, store


def load():
    return store.get(keys.RESERVE, {}) or {}


def save(cfg):
    store.put(keys.RESERVE, cfg)


def deposited_in(ym):
    """Tổng đã nạp vào quỹ trong tháng ym ('2026-11')."""
    return load().get("nap", {}).get(ym, 0)
