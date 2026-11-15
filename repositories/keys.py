"""Mọi khóa Redis của hai bot, một nơi duy nhất. Chuỗi khóa chép nguyên từ bản cũ: đổi chữ là mất dữ liệu đang chạy.

Khóa cố định là hằng; khóa có tham số là hàm. Mỗi khóa ghi hình dạng giá trị (JSON) ngay bên cạnh.
tests/test_keys.py chốt các chuỗi này và chặn việc viết khóa trực tiếp trong code.
"""

# ---- Bot chi tiêu: sổ thu chi ----------------------------------------------------------------
COUNTER = "chitieu:dem"  # số: mã khoản thu/chi đã cấp (INCR)
LEARN = "chitieu:hoc"  # {từ khóa ghi chú: mã nhóm} bot đã học
BUDGET = "chitieu:ngansach"  # {mã nhóm | "tong": hạn mức tháng}
GROUPS = "chitieu:nhomrieng"  # cấu hình nhóm riêng của người dùng
AI_CACHE = "chitieu:ai"  # {câu ghi chú: nhóm AI đoán}
AI_STATS = "chitieu:ai:thongke"  # hash: doan | sua -> số lần
PLAIN_NOTES = "chitieu:hieu:chi"  # [ghi chú AI đã xác định là khoản chi thường]
DAILY_GROUPS = "chitieu:dubao:nhom"  # [nhóm tính là chi tiêu hằng ngày]


def ledger_month(ym):
    """Hash: mã khoản -> JSON khoản thu/chi của tháng ym ("2026-11")."""
    return f"chitieu:{ym}"


# ---- Bot chi tiêu: tài sản, nợ, quỹ ----------------------------------------------------------
ASSETS = "chitieu:taisan"  # {"items": [...], "dem": số đã cấp, "lailo": [lãi/lỗ đã bán]}
ASSET_HISTORY = "chitieu:taisan:lichsu"  # hash: ngày -> {"rong": tài sản ròng, "loai": {loại: giá trị}}
GOLD = "vivang"  # ví vàng, dùng chung với bot bản tin: [{"loai": "sjc"|"nhan", "luong": lượng, "gia": triệu/lượng}]
SALARY = "chitieu:luong"  # {"ngay": ngày nhận lương, "tien": số tiền}
FUND = "chitieu:dautu"  # cấu hình đầu tư quỹ mở định kỳ (mã quỹ, kế hoạch, lệnh)
RESERVE = "chitieu:duphong"  # {"thang": số tháng mục tiêu, "han": đạt trong bao nhiêu tháng, "bat_dau": ngày, "chi": tự đặt,
#                              "nap": {"YYYY-MM": tổng đã nạp trong tháng}}
SAVINGS = "chitieu:tietkiem"  # {"moc", "bat_dau", "khong_tieu": [ngày ISO], "nhac": bool, "da_chuyen": đồng}
RECONCILE = "chitieu:doichieu"  # {"YYYY-MM": {"muc": {id: {...}}}}
OWNERS = "chitieu:chutk"  # [tên chủ tài khoản bot đã nhận ra từ ảnh]
KEYBOARD_FLAG = "chitieu:banphim:2"  # đã gửi hàng nút cố định bản 4 mục chưa


def price_cache(kind):
    """{"gia": {mã: giá}, "luc": thời điểm}: giá cổ phiếu/quỹ lấy gần nhất theo nguồn."""
    return f"chitieu:gia:{kind}"


def fund_nav(code):
    """{"ma", "luc", "nav": [[ngày ISO, NAV], ...]} khoảng 400 phiên gần nhất của quỹ."""
    return f"chitieu:dautu:nav:{code}"


def fund_info(code):
    """{"ma", "luc", "data": chi tiết quỹ của Fmarket}."""
    return f"chitieu:dautu:thongtin:{code}"


def savings_streak_milestone(n):
    return f"{SAVINGS}:moc:chuoi:{n}"  # cờ: đã mừng mốc chuỗi n ngày


def savings_saved_milestone(m):
    return f"{SAVINGS}:moc:bot:{m}"  # cờ: đã mừng mốc đã bớt m đồng


def reconcile_reminder(ym):
    return f"{RECONCILE}:nhac:{ym}"  # cờ: đã nhắc đối chiếu tháng ym


# ---- Bot chi tiêu: nhắc, cảnh báo (cờ có hạn dùng, mỗi cờ một lần) -----------------------------
def alert_rise(code):
    return f"chitieu:canhbao:tang:{code}"


def alert_budget(code, ym):
    return f"chitieu:canhbao:ngansach:{code}:{ym}"


def debt_reminder(debt_id, ym, stage):
    return f"chitieu:nhac:no:{debt_id}:{ym}:{stage}"


def saving_maturity_reminder(item_id, maturity):
    return f"chitieu:nhac:daohan:{item_id}:{maturity}"


# ---- Bot chi tiêu: hội thoại với trợ lý, ảnh --------------------------------------------------
CARD_COUNTER = "chitieu:the:dem"  # số: mã thẻ xác nhận đã cấp (INCR)


def conversation(chat):
    """{"viec": {...}, "hoi": trường đang hỏi, "sua": bool, "the": id}: việc đang làm dở của một chat."""
    return f"chitieu:cho:{chat or 0}"


def card(card_id):
    """Thẻ chờ xác nhận: việc cần làm khi bấm ✅."""
    return f"chitieu:the:{card_id}"


def ai_usage(day):
    return f"chitieu:hieu:thu:{day}"  # số lượt gọi AI hiểu câu trong ngày (INCR)


def benchmark_usage(day):
    return f"chitieu:danhgia:{day}"  # số lượt ?danhgia= trong ngày (INCR)


def image_seen(unique_id):
    return f"chitieu:anh:{unique_id}"  # cờ: ảnh (mã Telegram) đã ghi, tránh ghi trùng


def image_pending(unique_id):
    return f"chitieu:anhcho:{unique_id}"  # [giao dịch đọc từ ảnh, chờ người dùng chọn]


def done_transaction(date_iso, amount, direction):
    return f"chitieu:gd:{date_iso}|{amount}|{direction}"  # mã khoản đã ghi từ ảnh, chống ghi trùng


# ---- Bot bản tin ----------------------------------------------------------------------------
WATCHLIST = "theodoi"  # {mã: {...}} cổ phiếu theo dõi
REMINDERS = "nhac"  # [lời nhắc /nho]
KEYWORDS = "tukhoa"  # [từ khóa tin tức theo dõi]
GOLD_HISTORY = "vang_lichsu"  # {ngày: giá vàng}
GUESS_STATS = "doan_thongke"  # thống kê trò đoán VN-Index
ALERT_STATE = "canhbao"  # trạng thái cảnh báo giá
BOARD = "bangdien"  # {"ngay", "id": tin nhắn bảng điện}
DIVIDENDS_SEEN = "cotuc_daxem"  # [cổ tức đã báo]
TICK_LAST = "tick_cuoi"  # "HH:MM dd/mm" lần tick gần nhất
TICK_LOCK = "khoa:tick"  # khóa chạy: chỉ một tick cùng lúc
ANALYSIS_OFF = "nhandinh:tat"  # có khóa này thì không tự gửi nhận định
CACHE_SECTORS = "nhandinh:nganh"
CACHE_HOSE = "nhandinh:hose"


def guess(day):
    return f"doan:{day}"  # lựa chọn đoán VN-Index của ngày


def guess_result(day):
    return f"doan_kq:{day}"  # kết quả đoán của ngày


def job_done(job, day):
    return f"xong:{job}:{day}"  # cờ: việc theo lịch đã chạy hôm nay


def cache_foreign(days, since):
    return f"nhandinh:kn:{days}:{since}"
