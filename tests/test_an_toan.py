"""Bot không bao giờ ghi thẳng một tin có số tiền mà không phải khoản chi đã xảy ra (dự định, câu hỏi giả định, tin bot bị dán
lại). Đây là bộ ca hồi quy cho giai đoạn "chặn ghi sai" (docs/ke-hoach-tro-ly.md); thêm ca mới ở đây mỗi lần gặp lỗi ghi sai."""
import unittest

from tests import harness as h

from interface.chitieu import bot


def count():
    return len(h.month_entries())


class KhongGhiThang(unittest.TestCase):
    def setUp(self):
        h.reset()
        h.at(2026, 11, 20, 10)

    def test_du_dinh_va_cau_gia_dinh_khong_vao_so(self):
        for text in ("mai tôi định mua laptop 20tr", "tháng sau đóng học 3tr", "sẽ mua xe 30tr", "muốn mua xe 30tr",
                     "nếu mua xe 30tr thì sao", "giả sử mua laptop 20tr", "có nên mua laptop 20tr không",
                     "mua laptop 20tr được không"):
            reply, _ = h.say(text)
            self.assertEqual(count(), 0, text)
            self.assertNotIn("✅ Đã ghi", reply, text)

    def test_du_dinh_hoi_lai_bang_the(self):
        text, buttons = h.say("mai tôi định mua laptop 20tr")
        self.assertIn("nghe như một dự định, chưa phải khoản đã chi, nên mình chưa ghi", text)
        self.assertEqual(count(), 0)
        _, done, _ = h.press(h.button(buttons, "y:chi:"))  # đã chi thật: ghi nguyên tin
        self.assertIn("Đã ghi 20.000.000đ", done)
        self.assertEqual(count(), 1)

    def test_bam_khong_ghi(self):
        _, buttons = h.say("nếu mua xe 30tr thì sao")
        h.press(h.button(buttons, "y:huy:"))
        self.assertEqual(count(), 0)

    def test_tin_bot_bi_dan_lai(self):
        reply, _ = h.say("cà phê 35k")
        self.assertEqual(count(), 1)
        echo, buttons = h.say(reply)  # dán lại đúng tin bot vừa gửi
        self.assertIn("giống tin bot đã gửi nên mình không ghi", echo)
        self.assertEqual(count(), 1)
        report, _ = h.say("/thang")
        h.say(report)  # dán lại cả báo cáo
        h.say("🔎 Chi 01/11–15/11/2026 · có chữ «phở»\nTổng: 372.000đ · 10 khoản")
        self.assertEqual(count(), 1)

    def test_khoan_chi_thuong_van_ghi_ngay(self):
        for text, added in (("cà phê 35k", 1), ("hôm qua mua laptop 20tr", 1), ("mua laptop 20tr", 1),
                            ("tiền điện định kỳ 500k", 1), ("trả Mai 500k", 1), ("sắp xếp tủ 50k", 1),
                            ("cà phê 35k\nphở 50k", 2), ("tối qua ăn lẩu 300k", 1)):
            before = count()
            reply, _ = h.say(text)
            self.assertIn("Đã ghi", reply, text)
            self.assertEqual(count() - before, added, text)

    def test_ai_noi_la_khoan_chi_van_khong_ghi_cau_du_dinh(self):
        """Câu có chữ báo hiệu ("chuyển") nên hỏi AI; AI trả "chi" thì trước đây bot ghi luôn dù là dự định."""
        text = "mai tôi định chuyển 20tr tiền nhà"
        h.AI.replies[text] = {"viec": "chi"}
        reply, buttons = h.say(text)
        self.assertEqual(count(), 0)
        self.assertIn("nghe như một dự định", reply)
        self.assertTrue(any(b.startswith("y:chi:") for b in buttons))

    def test_goi_thang_record_text_van_ghi(self):
        """record_text là bước ghi sau khi người dùng đã xác nhận (nút 💸, thẻ AI): không tự chặn lần hai."""
        bot.record_text("mai tôi định mua laptop 20tr", h.CLOCK["now"])
        self.assertEqual(count(), 1)


if __name__ == "__main__":
    unittest.main()
