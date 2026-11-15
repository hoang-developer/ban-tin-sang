"""AssetRepo: tài sản đã khai báo ({"items", "dem", "lailo"}), lịch sử tài sản ròng theo ngày, giá đã lấy gần nhất.

Mục tài sản (items) khác nhau nhiều theo loại (tiền, tiết kiệm, cổ phiếu, quỹ, nợ…) nên tạm giữ dạng dict;
kiểu dữ liệu riêng cho từng loại làm ở các bước sau (plan.md).
"""
import json

from repositories import keys, store


def load():
    data = store.get(keys.ASSETS, {}) or {}
    data.setdefault("items", [])
    return data


def save(data):
    store.put(keys.ASSETS, data)


def save_snapshot(day_iso, record):
    """Tài sản ròng của một ngày: {"rong": số, "loai": {loại: giá trị}}."""
    store.hash_set(keys.ASSET_HISTORY, day_iso, json.dumps(record))


def history():
    """[(ngày ISO, {"rong", "loai"})] theo thứ tự ngày."""
    return sorted((day, json.loads(raw)) for day, raw in store.hash_all(keys.ASSET_HISTORY).items())


def price_cache(kind):
    """(giá {mã: đồng}, lúc cập nhật ISO hoặc None) lấy gần nhất của một nguồn giá."""
    data = store.get(keys.price_cache(kind), {}) or {}
    return data.get("gia", {}), data.get("luc")


def save_price_cache(kind, prices, when):
    store.put(keys.price_cache(kind), {"gia": prices, "luc": when})
