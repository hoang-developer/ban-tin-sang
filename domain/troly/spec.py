"""Trợ lý hiểu câu thường: khuôn các trường của việc, chữ báo hiệu tin không phải khoản chi, nhận ra câu trả lời ngắn (tính thuần)."""
import re

from domain.common.text import norm, plain


STATE_SECONDS, CARD_SECONDS = 900, 2 * 86400

TRY_LIMIT = 40  # số lượt thử ?hieu= mỗi ngày trên trang tình trạng


def F(ten, kieu, hoi=None, can=True, goi=False, chon=None):
    """Một trường của việc. kieu: tien (đồng), so, chu, ngay (ISO), chon (một trong các lựa chọn), co (đúng/sai).
    can: bắt buộc; goi: không bắt buộc nhưng hỏi một lần (có nút Bỏ qua); chon: [(giá trị, nhãn)] hoặc hàm trả danh sách."""
    return {"ten": ten, "kieu": kieu, "hoi": hoi, "can": can, "goi": goi, "chon": chon}

GOLD_PRICE = (50, 300)  # triệu đồng/lượng: ngoài khoảng này gần như chắc nhập nhầm (giá một chỉ, thiếu số 0…)

TERMS = [(0, "Không kỳ hạn"), (1, "1 tháng"), (3, "3 tháng"), (6, "6 tháng"), (12, "12 tháng")]

SCREENS = ("tong_quan", "chi_tieu", "tai_san", "no", "ke_hoach", "chia_luong", "du_phong", "dau_tu", "tiet_kiem",
           "suc_khoe", "lich_su", "bieu_do", "du_bao", "ngan_sach", "huong_dan")

PERIODS = ("ngay", "tuan", "thang", "thangtruoc")

SIMPLE = ("chi", "hoi", "xem", "khong_tieu", "xoa_cuoi", "khac")

# Chữ báo hiệu tin không phải khoản chi thường. So trên chữ có dấu khi người dùng gõ có dấu ("váy" khác "vay",
# "bạn" khác "bán"); gõ không dấu thì so trên chữ đã bỏ dấu.
TRIGGERS = ["chuyển", "nạp", "rút", "tiết kiệm", "vàng", "vay", "mượn", "quỹ", "ccq", "chứng chỉ", "cổ phiếu", "bán",
            "đầu tư", "tài khoản", "số dư", "ngân sách", "lương về", "nhận lương", "nhận tiền", "được thưởng",
            "hoán đổi", "tất toán", "đáo hạn", "dự phòng", "vff", "vmeef", "không tiêu", "khớp lệnh", "đặt lệnh",
            "nợ", "trả góp", "khoản vay", "trả lại", "sjc", "lượng", "nhẫn", "chốt lời", "cắt lỗ", "xóa", "sửa",
            "còn lại"]

# Câu hỏi về thứ ngoài sổ chi tiêu (nợ, tài sản, quỹ, kế hoạch): không trả lời bằng sổ chi tiêu
BEYOND = ["nợ", "vay", "quỹ", "ccq", "vff", "vmeef", "tài sản", "tiết kiệm", "vàng", "cổ phiếu", "đầu tư", "dự phòng",
          "kế hoạch", "mục tiêu", "lãi", "lỗ", "ngân sách", "trả xong", "bao giờ", "khi nào", "tài khoản", "số dư",
          "sức khỏe", "để dành", "được tiêu", "nên tiêu", "được không", "có nên", "nên mua", "có đủ"]


def word_re(words):
    return re.compile(r"(?<!\w)(?:" + "|".join(re.escape(w) for w in words) + r")(?!\w)")

TRIGGER_RE = (word_re(TRIGGERS), word_re([plain(w) for w in TRIGGERS]))

BEYOND_RE = (word_re(BEYOND), word_re([plain(w) for w in BEYOND]))


def mentions(text, pair):
    """Tin có nhắc một trong các chữ? Gõ có dấu thì so chữ có dấu, gõ không dấu thì so chữ đã bỏ dấu."""
    accented, bare = norm(text), plain(text)
    return bool(pair[0].search(accented) if accented != bare else pair[1].search(bare))


def beyond_spending(text):
    return mentions(text, BEYOND_RE)


def number_of(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip().rstrip("%").replace(",", "."))
    except ValueError:
        return None

CASH_IN = ("tat_toan", "ban_vang", "ban_quy", "thu_no")  # tiền tự về tài khoản chính

NO_SPEND = re.compile(r"(?<!\w)(?:khong|ko|k|chua) (?:tieu|chi|mua)(?: gi| dong nao| xu nao)?(?: ca| het)?(?!\w)")

FILLER = {"khoang", "la", "tam", "het", "tong", "gan", "duoc", "co", "thoi", "a", "nhe", "da"}


def only_filler(rest):
    return all(w in FILLER for w in plain(re.sub(r"[^\w\s]", " ", rest)).split())
