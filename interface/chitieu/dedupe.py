"""Chống xử lý trùng ở cửa vào của bot chi tiêu.

- Telegram gửi lại một tin (cùng update_id) khi hàm trả lời chậm hay lỗi: không ghi khoản lần hai.
- Bấm đúp một nút: hai lượt chạy gần như cùng lúc cùng đọc rồi cùng ghi, nên nút ghi hai lần dù bấm lần hai báo "đã xử lý".
"""
from repositories.chitieu import updates


def start(update):
    """True nếu nên xử lý tin này; False nếu đang hoặc đã xử lý (Telegram gửi lại)."""
    update_id = update.get("update_id")
    return True if update_id is None else updates.claim_update(update_id)


def finish(update):
    """Xử lý xong một tin."""
    update_id = update.get("update_id")
    if update_id is not None:
        updates.finish_update(update_id)


def repeated_press(query):
    """True nếu cùng nút trên cùng tin vừa được bấm trong vài giây qua (bấm đúp): lượt này bỏ qua."""
    message = query.get("message") or {}
    data, message_id = query.get("data"), message.get("message_id")
    if not data or message_id is None:
        return False
    return not updates.claim_press((message.get("chat") or {}).get("id"), message_id, data)
