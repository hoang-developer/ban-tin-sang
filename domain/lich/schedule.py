"""Luật giờ giấc của việc theo giờ: khung giờ, ngày giao dịch, tin quyền lợi cổ đông (tính thuần)."""
from domain.canhbao.rules import normalize  # noqa: F401

# Từ khóa nhận ra tin quyền lợi cổ đông (so khớp sau khi đưa về chữ thường)
DIVIDEND_WORDS = ["cổ tức", "chốt quyền", "chốt danh sách", "không hưởng quyền", "phát hành thêm",
                  "thưởng cổ phiếu", "cổ phiếu thưởng"]


def between(now, start, end):
    """Giờ:phút của now nằm trong [start, end) (mỗi mốc là (giờ, phút))."""
    return start <= (now.hour, now.minute) < end


def trading_day(now):
    return now.weekday() < 5
