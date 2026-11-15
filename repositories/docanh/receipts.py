"""Lưu trạng thái đọc ảnh: tên chủ tài khoản đã nhận ra, ảnh đã xử lý, danh sách giao dịch chờ chọn, giao dịch đã ghi."""
from infrastructure import kho
from repositories import keys

SEEN_DAYS, PENDING_DAYS, DONE_DAYS = 60, 2, 120


def owners():
    return list(kho.get(keys.OWNERS, []) or [])


def save_owners(names):
    kho.put(keys.OWNERS, names)


def claim_image(unique):
    """Đánh dấu ảnh đang xử lý; False nếu ảnh này đã xử lý rồi."""
    return kho.put_new(keys.image_seen(unique), True, SEEN_DAYS * 86400)


def release_image(unique):
    kho.delete(keys.image_seen(unique))


def pending(unique):
    return kho.get(keys.image_pending(unique))


def save_pending(unique, txs):
    kho.put(keys.image_pending(unique), txs, PENDING_DAYS * 86400)


def delete_pending(unique):
    kho.delete(keys.image_pending(unique))


def recorded(date_iso, amount, direction):
    """Id khoản đã ghi cho giao dịch này (cùng ngày, số tiền, chiều); None nếu chưa ghi."""
    return kho.get(keys.done_transaction(date_iso, amount, direction))


def mark_recorded(date_iso, amount, direction, entry_id):
    kho.put(keys.done_transaction(date_iso, amount, direction), entry_id, DONE_DAYS * 86400)


def learned():
    return kho.get(keys.LEARN, {})
