"""Tin có số tiền nhưng không phải khoản chi đã xảy ra: luật thuần của domain/chitieu/guard.py."""
import unittest

from domain.chitieu import guard

KHONG_GHI = [
    ("mai tôi định mua laptop 20tr", "tuong_lai"), ("sẽ đóng học 3tr", "tuong_lai"), ("muốn mua xe 30tr", "tuong_lai"),
    ("ăn trưa tháng sau 50k", "tuong_lai"), ("mai mua sách 200k", "tuong_lai"), ("quyết định mua laptop 20tr", "tuong_lai"),
    ("toi dinh mua laptop 20tr", "tuong_lai"), ("kế hoạch mua xe 30tr", "tuong_lai"),
    ("nếu mua xe 30tr thì sao", "gia_su"), ("giả sử mua laptop 20tr", "gia_su"), ("liệu mua laptop 20tr có đắt", "gia_su"),
    ("có nên mua laptop 20tr không", "hoi"), ("mua laptop 20tr được không", "hoi"), ("tháng này ăn phở bao nhiêu 50k?", "hoi"),
    ("cà phê 35k\nmai mua laptop 20tr", "tuong_lai"),  # nhiều dòng: một dòng có lý do thì cả tin chờ hỏi
    ("🔎 Chi 01/11–15/11/2026 · có chữ «phở»\nTổng: 372.000đ · 10 khoản", "dan_lai"),
    ("✅ Đã ghi 35.000đ · 🍜 Ăn uống — cà phê", "dan_lai"), ("🏠 Hôm nay, thứ ba 10/11\n💸 Đã chi 10,05tr", "dan_lai"),
    ("Mình hiểu là:\nTổng: 5tr · 2 khoản", "dan_lai"),
]
GHI_BINH_THUONG = [
    "cà phê 35k", "hôm qua mua laptop 20tr", "mua laptop 20tr", "tối qua ăn lẩu 300k", "tiền điện định kỳ 500k",
    "chi phí cố định 3tr", "trả Mai 500k", "sắp xếp tủ 50k", "đã ghi tiền điện 500k", "cà phê 35k\nphở 50k",
    "+ lương 20tr", "đóng họ 1tr #tiết kiệm", "02/11 cắt tóc 100k", "grab 50k",
]


class Guard(unittest.TestCase):
    def test_khong_ghi_thang(self):
        for text, reason in KHONG_GHI:
            self.assertEqual(guard.skip_reason(text), reason, text)

    def test_khoan_chi_thuong_van_ghi(self):
        for text in GHI_BINH_THUONG:
            self.assertIsNone(guard.skip_reason(text), text)
        self.assertIsNone(guard.skip_reason("   "))

    def test_tin_bot(self):
        self.assertTrue(guard.is_bot_text("📊 Chi tiêu tháng 11/2026"))
        self.assertTrue(guard.is_bot_text("Đã ghi 35.000đ · cà phê\nTổng: 35k"))
        self.assertFalse(guard.is_bot_text("đã ghi tiền điện 500k"))  # một dòng, không có dấu « · »
        self.assertFalse(guard.is_bot_text("🍜 phở 50k"))  # biểu tượng món ăn của người dùng


if __name__ == "__main__":
    unittest.main()
