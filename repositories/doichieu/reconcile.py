"""ReconcileRepo: các lần đối chiếu theo tháng (khóa keys.RECONCILE) và cờ đã nhắc ngày 15.

{"YYYY-MM": {"muc": {id: {"ten", "bot", "that", "lech", "don_vi", "no"?, "ghi"?}}}}; giữ 12 tháng gần nhất.
"""
from repositories import keys, store

FORTY_DAYS = 40 * 86400


def load_all():
    return store.get(keys.RECONCILE, {}) or {}


def load_month(ym):
    return load_all().get(ym, {"muc": {}})


def save_month(ym, month):
    data = load_all()
    data[ym] = month
    store.put(keys.RECONCILE, dict(sorted(data.items())[-12:]))


def claim_reminder(ym):
    """True nếu đây là lần đầu nhắc đối chiếu tháng ym (và đánh dấu đã nhắc)."""
    return store.put_new(keys.reconcile_reminder(ym), True, FORTY_DAYS)
