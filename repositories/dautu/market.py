"""MarketRepo: nhớ tạm dữ liệu quỹ lấy từ Fmarket (khóa keys.fund_nav, keys.fund_info) để khỏi gọi lại mỗi lần.

NAV: {"ma", "luc", "nav": [[ngày ISO, NAV], ...]} (khoảng 400 phiên gần nhất).
Thông tin: {"ma", "luc", "data": {"phien", "top", "top_luc"}}.
"""
from repositories import keys, store


def load_nav(code):
    return store.get(keys.fund_nav(code), {}) or {}


def save_nav(code, when_iso, navs):
    store.put(keys.fund_nav(code), {"ma": code, "luc": when_iso, "nav": navs})


def load_info(code):
    return store.get(keys.fund_info(code), {}) or {}


def save_info(code, when_iso, data):
    store.put(keys.fund_info(code), {"ma": code, "luc": when_iso, "data": data})
