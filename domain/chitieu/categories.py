"""Các nhóm chi tiêu có sẵn và bảng từ khóa. Từ khóa so khớp nguyên từ; nhiều từ cùng khớp thì lấy cụm dài nhất
("tiền nước" thắng "nước"). Gõ không dấu cũng nhận ra."""
import re

from domain.common.text import norm, plain

# mã -> (tên, từ khóa)
CATEGORIES = {
    "an": ("🍜 Ăn uống", [
        "ăn", "ăn sáng", "ăn trưa", "ăn tối", "ăn đêm", "ăn vặt", "cơm", "cơm văn phòng", "phở", "bún", "miến",
        "mì", "mỳ", "hủ tiếu", "bánh mì", "bánh cuốn", "bánh", "bánh ngọt", "xôi", "cháo", "lẩu", "nướng", "gà",
        "vịt", "bò", "pizza", "burger", "kfc", "lotteria", "jollibee", "mcdonald", "cà phê", "cafe", "coffee",
        "highlands", "highland", "starbucks", "starbuck", "phúc long", "katinat", "trà", "trà sữa", "trà đá",
        "nước", "nước ngọt", "nước suối", "nước lọc", "nước mía", "nước ép", "sinh tố", "bia", "rượu", "nhậu", "chè", "kem", "sữa chua", "hoa quả", "trái cây",
        "đồ ăn", "nhà hàng", "quán", "buffet", "grabfood", "shopeefood", "baemin", "gofood", "đặt đồ ăn",
        "bim bim", "snack", "kẹo", "liên hoan", "tiệc"]),
    "cho": ("🛒 Đi chợ, siêu thị", [
        "chợ", "đi chợ", "siêu thị", "winmart", "vinmart", "bách hóa xanh", "coopmart", "co.op", "aeon", "big c",
        "lotte mart", "mega market", "tạp hóa", "rau", "thịt", "cá", "tôm", "trứng", "gạo", "mắm", "dầu ăn",
        "gia vị", "sữa", "đồ khô", "thực phẩm", "nước giặt", "bột giặt", "giấy vệ sinh", "nước rửa bát",
        "dầu gội", "sữa tắm", "kem đánh răng", "đồ dùng"]),
    "xe": ("🛵 Đi lại", [
        "xăng", "đổ xăng", "grab", "grabbike", "grabcar", "be", "xanh sm", "taxi", "gojek", "xe ôm", "gửi xe",
        "trông xe", "đỗ xe", "vé xe", "xe khách", "xe buýt", "bus", "tàu", "vé tàu", "máy bay", "vé máy bay",
        "metro", "xe", "xe máy", "ô tô", "oto", "rửa xe", "sửa xe", "thay dầu", "thay nhớt", "bảo dưỡng",
        "bảo dưỡng xe", "vá xe", "lốp", "phí đường", "cầu đường", "vetc", "epass", "đăng kiểm", "bảo hiểm xe", "phạt nguội", "nộp phạt"]),
    "nha": ("🏠 Nhà cửa, hóa đơn", [
        "tiền nhà", "thuê nhà", "tiền phòng", "tiền trọ", "trọ", "điện", "tiền điện", "hóa đơn điện",
        "tiền nước", "hóa đơn nước", "internet", "wifi", "tiền mạng", "cước", "điện thoại", "nạp điện thoại",
        "nạp tiền điện thoại", "4g", "gas", "bình gas", "phí quản lý", "phí dịch vụ", "chung cư", "sửa nhà",
        "sửa điện", "thợ", "đồ gia dụng", "nồi", "chảo", "giường", "tủ", "bàn ghế", "điều hòa", "máy giặt",
        "tủ lạnh", "truyền hình", "k+", "viettel", "vnpt", "fpt"]),
    "mua": ("🛍️ Mua sắm", [
        "mua", "quần", "áo", "quần áo", "váy", "giày", "dép", "túi", "ví", "đồng hồ", "kính", "mỹ phẩm", "son",
        "nước hoa", "skincare", "shopee", "lazada", "tiki", "tiktok shop", "sendo", "uniqlo", "zara",
        "mua điện thoại", "laptop", "máy tính", "tai nghe", "ốp lưng", "sạc", "đồ điện tử", "phụ kiện",
        "trang sức", "cây cảnh", "đồ trang trí", "cắt tóc", "làm tóc", "gội đầu", "làm nail", "spa"]),
    "khoe": ("💊 Sức khỏe", [
        "thuốc", "nhà thuốc", "pharmacity", "long châu", "khám", "khám bệnh", "bệnh viện", "phòng khám",
        "nha khoa", "răng", "xét nghiệm", "tiêm", "vắc xin", "vitamin", "thực phẩm chức năng", "bảo hiểm",
        "bảo hiểm y tế", "gym", "phòng tập", "yoga", "bơi", "massage", "khẩu trang", "kính mắt"]),
    "choi": ("🎬 Giải trí, du lịch", [
        "phim", "xem phim", "rạp", "cgv", "lotte cinema", "bhd", "netflix", "spotify", "youtube",
        "youtube premium", "apple music", "icloud", "google one", "chatgpt", "game", "nạp game", "steam",
        "karaoke", "bi a", "bida", "concert", "vé xem", "du lịch", "khách sạn", "homestay", "resort", "tour",
        "vé tham quan", "dã ngoại", "picnic", "cắm trại", "đi chơi"]),
    "hoc": ("📚 Học tập", [
        "học phí", "tiền học", "đóng học", "học", "học thêm", "lớp", "khóa học", "sách", "vở", "bút",
        "văn phòng phẩm", "giáo trình", "udemy", "coursera", "tiếng anh", "ielts", "lệ phí thi"]),
    "qua": ("🎁 Hiếu hỷ, quà tặng", [
        "đám cưới", "cưới", "mừng cưới", "sinh nhật", "quà", "tặng", "biếu", "đám ma", "đám hiếu", "phúng",
        "viếng", "lì xì", "mừng tuổi", "từ thiện", "ủng hộ", "hoa", "đi lễ", "lễ chùa", "công đức"]),
    "giadinh": ("👨‍👩‍👧 Gia đình, con cái", [
        "cho con", "của con", "con đi học", "cho bé", "bỉm", "tã", "sữa bột", "đồ chơi", "gửi bố mẹ",
        "biếu bố mẹ", "bố mẹ", "ông bà", "giúp việc", "osin", "trông trẻ", "nhà trẻ", "mầm non", "thú cưng",
        "cho chó", "cho mèo", "thức ăn cho chó", "thức ăn cho mèo", "pate"]),
    "khac": ("📦 Khác", []),
    "thu": ("💰 Thu nhập", [
        "lương", "nhận lương", "thưởng", "tiền thưởng", "hoa hồng", "lãi tiết kiệm", "cổ tức", "bán",
        "thu nhập", "được cho", "được tặng", "hoàn tiền", "cashback", "freelance", "làm thêm"]),
}
GENERIC = {"mua", "ăn", "quán", "học", "bánh", "nước", "xe"}  # từ chung chung: chỉ dùng khi không có từ nào rõ hơn
MAX_LEARNED = 500  # số cụm từ học được tối đa
MAX_GROUPS, MAX_WORDS = 20, 60  # số nhóm tự tạo, số từ khóa tự thêm cho mỗi nhóm


def word_pattern(word):
    return re.compile(rf"(?<!\w){re.escape(word)}(?!\w)")


# Bỏ dấu rồi trùng với chữ thường gặp: "chợ"/"cho", "cá"/"ca", "quà"/"qua", "vở"/"vợ", "gà"/"ga"(gas)...
# Câu gõ không dấu thì không dùng các dạng này để đoán nhóm.
AMBIGUOUS_PLAIN = {"cho", "ca", "qua", "ta", "tu", "vo", "noi", "bo", "ga", "but", "che", "tang", "tra"}


def plain_pattern(word):
    bare = plain(word)
    return None if bare in AMBIGUOUS_PLAIN and bare != norm(word) else word_pattern(bare)


# (mẫu có dấu, mẫu không dấu hoặc None, điểm, mã nhóm); điểm là độ dài cụm, từ chung chung điểm thấp
KEYWORDS = [(word_pattern(norm(k)), plain_pattern(k), 0.5 if norm(k) in GENERIC else len(norm(k)), code)
            for code, (_, words) in CATEGORIES.items() for k in words]
