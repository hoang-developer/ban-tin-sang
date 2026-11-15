"""Lệnh của bot bản tin: luật nhập số tiền và thời gian, chữ mức giá, các lệnh theo dõi, ngày cần nhớ, ví vàng, đoán xanh/đỏ."""
import unittest
from datetime import datetime

from tests import harness as h

from domain.lenh import rules
from interface.lenh import bot
from presentation.lenh import view


class Luat(unittest.TestCase):
    def test_doi_tien_ra_chu_gon(self):
        self.assertEqual([rules.money(x) for x in (0, 999, 1500, 2.5e6, 3e6, 1.234e9, -4e9)],
                         ["0đ", "999đ", "1.500đ", "2,50 triệu", "3 triệu", "1,23 tỷ", "-4 tỷ"])
        self.assertEqual([rules.amount_text(x) for x in (0, 0.01, 0.2, 1, 1.5, 2.02)],
                         ["0 chỉ", "0,1 chỉ", "2 chỉ", "1 lượng", "1 lượng 5 chỉ", "2 lượng 0,2 chỉ"])

    def test_mau_nhap(self):
        self.assertEqual(rules.DATE.fullmatch("20/11").groups(), ("20", "11"))
        self.assertIsNone(rules.DATE.fullmatch("20-11"))
        self.assertEqual(rules.AMOUNT.fullmatch("1,5ty").groups(), ("1,5", "ty"))
        self.assertEqual(rules.PERIOD.fullmatch("2tuần").groups(), ("2", "tuần"))
        self.assertEqual((rules.UNIT_MONEY["tr"], rules.UNIT_DAYS["nam"], rules.UNITS["chi"], rules.KINDS["miếng"]), (1e6, 365, 0.1, "sjc"))

    def test_mot_so_ham_nho(self):
        self.assertEqual((rules.parse_level("-"), rules.parse_level("40,5")), (None, 40.5))
        self.assertEqual(rules.when_text({"ngay": 3, "thang": 4, "am": True}), "3/4 âm lịch")
        self.assertEqual(rules.when_text({"ngay": 20, "thang": 11, "am": False}), "20/11")
        self.assertEqual(rules.rows_of([1, 2, 3, 4, 5], 2), [[1, 2], [3, 4], [5]])

    def test_chu_muc_gia(self):
        self.assertEqual(view.level_text((None, None)), "")
        self.assertEqual(view.level_text((50, 60)), " · báo khi ≤ 50.000 hoặc ≥ 60.000")
        self.assertIn("xanh", view.GUESS_TEXT)
        self.assertEqual(view.GUESS_LABEL["do"], "🔴 Đỏ")


class Lenh(unittest.TestCase):
    def setUp(self):
        h.reset()
        h.at(2026, 11, 13, 8, 30)
        real = (bot.quote, bot.quotes, bot.stock_command, bot.gold_prices)
        self.addCleanup(lambda: (setattr(bot, "quote", real[0]), setattr(bot, "quotes", real[1]),
                                 setattr(bot, "stock_command", real[2]), setattr(bot, "gold_prices", real[3])))
        bot.gold_prices = lambda: {"sjc": (150.0, 152.0), "nhan": (148.0, 150.0), "nhan_ten": "Nhẫn", "nguon": "x"}
        bot.quote = lambda s: None if s == "NONE" else {"price": 50000.0, "ref": 49000.0}
        bot.quotes = lambda syms: {s: {"price": 50000.0, "ref": 49000.0} for s in syms}
        bot.stock_command = lambda args: "STOCK " + " ".join(args)

    def test_theo_doi_ma(self):
        self.assertIn("Chưa theo dõi mã nào", bot.answer("/theodoi"))
        self.assertIn("Đã theo dõi <b>FPT</b> · báo khi ≤ 50.000 hoặc ≥ 60.000", bot.answer("/theodoi fpt 50 60"))
        self.assertIn("❓ Không tìm thấy mã <b>NONE</b>", bot.answer("/theodoi none"))
        self.assertIn("Mã không hợp lệ", bot.answer("/theodoi f"))
        text, rows = bot.answer("/theodoi")
        self.assertIn("• <b>FPT</b> 50.000 (+2,04%) · báo khi", text)
        self.assertEqual(rows, [[("❌ Bỏ FPT", "bo:FPT")]])
        self.assertEqual(bot.price_alerts(), {"FPT": (50.0, 60.0)})

    def test_ngay_can_nho(self):
        self.assertIn("Lưu ngày cần nhớ", bot.answer("/nho"))
        self.assertIn("Đã lưu: <b>sinh nhật vợ</b> – 20/11", bot.answer("/nho sinh nhật vợ 20/11"))
        self.assertIn("không hợp lệ", bot.answer("/nho họp 31/2"))
        self.assertIn("không hợp lệ", bot.answer("/nho x 31/13 âm"))
        text, rows = bot.answer("/nho")
        self.assertIn("sinh nhật vợ – 20/11", text)
        self.assertEqual(rows[0][0][1], "xoanho:1")
        self.assertEqual(bot.on_button("xoanho:1", {}, h.CLOCK["now"])[0], "Đã xóa")
        self.assertEqual(bot.delete_reminder("1"), "Mục này đã xóa rồi")

    def test_vi_vang(self):
        self.assertIn("Thêm vàng vào ví", bot.answer("/vivang"))
        self.assertIn("Đã thêm 2 chỉ vào ví", bot.answer("/vivang nhan 2 chi 136"))
        self.assertIn("Thêm vàng vào ví", bot.answer("/vivang sjc 2000 luong"))  # quá 1000 lượng
        self.assertEqual(bot.answer("/vivang xoa"), "🗑 Đã xóa ví vàng")

    def test_doan_xanh_do(self):
        self.assertEqual(bot.record_guess("zzz", h.CLOCK["now"]), "Lựa chọn không hợp lệ")
        self.assertIsNone(bot.record_guess("xanh", h.CLOCK["now"]))
        h.at(2026, 11, 13, 9, 30)
        self.assertEqual(bot.record_guess("xanh", h.CLOCK["now"]), "Hết giờ đoán hôm nay rồi")
        h.at(2026, 11, 14, 8, 30)
        self.assertEqual(bot.record_guess("xanh", h.CLOCK["now"]), "Cuối tuần không có phiên, thứ Hai đoán tiếp nhé")
        self.assertIn("Chưa có lượt đoán nào", bot.answer("/doan"))

    def test_lenh_la_va_nhom(self):
        self.assertEqual(bot.answer("xin chào"), None)
        self.assertEqual(bot.answer("/zzz"), bot.HELP)
        self.assertEqual(bot.answer("/stock@Bot fpt")[0], "STOCK fpt")
        self.assertEqual([m["command"] for m in bot.MENU][:2], ["stock", "nhandinh"])

    def test_nut_bam_chung_khoan(self):
        toast, action = bot.on_button("doan:xanh", {}, h.CLOCK["now"])
        self.assertEqual(toast, "Đã ghi: 🟢 Xanh")  # thứ sáu 8:30, còn trong giờ đoán
        self.assertEqual(bot.on_button("zzz:1", {}, h.CLOCK["now"]), (None, None))


if __name__ == "__main__":
    unittest.main()
