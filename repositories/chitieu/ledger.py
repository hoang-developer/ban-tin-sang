"""LedgerRepo: sổ thu chi. Mỗi tháng một hash (mã khoản -> JSON khoản), ghi/sửa/xóa từng khoản riêng nên hai tin nhắn
tới cùng lúc không đè mất khoản của nhau. Mã khoản cấp từ một bộ đếm chung (next_id).

Khoản thu/chi giữ dạng dict (id, ngay, gio, nhom, tien, ghichu…): kiểu dữ liệu riêng làm sau (plan.md).
"""
import json

from repositories import keys, store


def load(ym):
    """Các khoản của tháng ym ("2026-11"), xếp theo mã."""
    return sorted((json.loads(raw) for raw in store.hash_all(keys.ledger_month(ym)).values()), key=lambda e: e["id"])


def save(entry):
    """Ghi (hoặc ghi đè) một khoản vào tháng của ngày khoản đó. Khóa bắt đầu bằng "_" chỉ dùng tạm khi trả lời, không lưu."""
    kept = {k: v for k, v in entry.items() if not k.startswith("_")}
    store.hash_set(keys.ledger_month(entry["ngay"][:7]), entry["id"], json.dumps(kept, ensure_ascii=False))


def find(ym, entry_id):
    """Khoản đó hoặc None nếu đã xóa."""
    raw = store.hash_get(keys.ledger_month(ym), entry_id)
    return json.loads(raw) if raw else None


def remove(ym, entry_id):
    store.hash_del(keys.ledger_month(ym), entry_id)


def next_id():
    """Mã cho khoản mới."""
    return store.incr(keys.COUNTER)


def last_id():
    """Mã khoản đã cấp gần nhất (0 nếu chưa có): dùng làm mốc "các khoản ghi trước lúc này"."""
    return int(store.get(keys.COUNTER) or 0)
