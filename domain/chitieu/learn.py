"""Học nhóm người dùng chọn: khóa ghi nhớ bỏ số/ngày tháng, khoản đang chờ hỏi nhóm."""
import re

from domain.chitieu.kinds import OTHER
from domain.common.text import norm

MAX_LEARNED = 500  # số cụm từ học được tối đa

# Số, ngày tháng trong ghi chú không giúp gì cho việc xếp nhóm: học "tiền đổ rác" thay vì
# "tiền đổ rác tháng 11", để tháng sau ghi "tiền đổ rác tháng 12" bot vẫn nhận ra.
NOISE = re.compile(r"(?<!\w)(?:(?:tháng|thang|quý|quy|năm|kỳ|ky|tuần|tuan|ngày|ngay|lần|đợt|dot|t|q)\s*)?"
                   r"\d+(?:[/.\-]\d+)*(?!\w)")


def learn_key(note):
    key = " ".join(NOISE.sub(" ", norm(note)).split()).strip(" ,.:;-–")
    return key if len(key) >= 2 else norm(note)


def merge_learned(learned, pairs):
    """Thêm các cặp (khóa đã chuẩn hóa, mã nhóm) vào cụm đã học: cặp mới nhất ở cuối, giữ tối đa MAX_LEARNED."""
    learned = dict(learned)
    for key, code in pairs:
        learned.pop(key, None)
        learned[key] = code
    return dict(list(learned.items())[-MAX_LEARNED:])


def pending(e):
    """Khoản đang ở Khác mà người dùng chưa chọn để nguyên: bot sẽ hỏi nhóm."""
    return e["nhom"] == OTHER and not e.get("dekhac")
