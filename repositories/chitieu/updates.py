"""UpdatesRepo: dấu các tin Telegram đã nhận (chống xử lý trùng khi Telegram gửi lại một tin) và lượt bấm nút vừa xong
(chống bấm đúp). Kho lỗi hay chưa nối thì coi như tin mới: không bao giờ chặn nhầm một tin thật."""
import hashlib
import sys

from repositories import keys, store

# Hơn thời gian tối đa của hàm (60 giây): tin đang xử lý dở thì mọi lần gửi lại đều bị chặn; hàm đã chết giữa chừng thì
# lần Telegram gửi lại sau đó được xử lý lại.
DOING_SECONDS = 70
DONE_SECONDS = 3600
PRESS_SECONDS = 5


def claim_update(update_id):
    """True nếu đây là lần đầu thấy tin này (đã đánh dấu "đang làm"); False nếu đang hoặc đã xử lý."""
    try:
        return bool(store.put_new(keys.update_seen(update_id), "dang_lam", DOING_SECONDS))
    except Exception as e:
        print(f"[lỗi] đánh dấu tin {update_id}: {e!r}", file=sys.stderr)
        return True


def finish_update(update_id):
    """Xử lý xong: giữ dấu lâu hơn để lần gửi lại muộn cũng bị chặn."""
    try:
        store.put(keys.update_seen(update_id), "xong", DONE_SECONDS)
    except Exception as e:
        print(f"[lỗi] chốt tin {update_id}: {e!r}", file=sys.stderr)


def claim_press(chat, message_id, data):
    """True nếu cùng nút (dữ liệu `data`) trên cùng tin chưa được bấm trong PRESS_SECONDS giây qua."""
    digest = hashlib.sha1(str(data).encode()).hexdigest()[:12]
    try:
        return bool(store.put_new(keys.button_press(chat, message_id, digest), True, PRESS_SECONDS))
    except Exception as e:
        print(f"[lỗi] đánh dấu lượt bấm {data!r}: {e!r}", file=sys.stderr)
        return True
