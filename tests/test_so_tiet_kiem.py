"""Sổ tiết kiệm có kỳ hạn: tất toán trước hạn chỉ được lãi không kỳ hạn, sổ đã đáo hạn hỏi tái tục hay rút (không đóng băng im lặng)."""
import unittest
from datetime import date

from tests import harness as h
from tests.test_dongtien import item, main_balance, net, set_main

from domain.taisan import rules
from interface.taisan import assets as ts
from interface.thongbao import digest
from repositories.taisan import assets as assets_repo

BOOK = {"loai": "tietkiem", "ten": "ACB", "tien": 100_000_000, "lai": 6.0, "ky": 12, "ngay": "2026-01-01"}


class Luat(unittest.TestCase):
    def test_tat_toan_truoc_han_chi_duoc_lai_khong_ky_han(self):
        total, interest, early, maturity = rules.payout(BOOK, date(2026, 11, 25))
        self.assertEqual((early, maturity), (True, date(2027, 1, 1)))
        self.assertEqual(round(interest), 449_315)  # 100tr × 0,5%/năm × 328/365 (lỗi cũ: 5.391.781 theo lãi 6%)
        self.assertEqual(round(total), 100_449_315)

    def test_lai_khong_ky_han_chinh_theo_so(self):
        total, interest, early, _ = rules.payout({**BOOK, "lai_kkh": 1.0}, date(2026, 11, 25))
        self.assertEqual((early, round(interest)), (True, 898_630))

    def test_toi_han_hoac_qua_han_du_lai_co_ky_han(self):
        for day in (date(2027, 1, 1), date(2027, 6, 1)):
            total, interest, early, _ = rules.payout(BOOK, day)
            self.assertEqual((early, round(interest)), (False, 6_000_000), day)  # lãi dừng ở ngày đáo hạn

    def test_so_khong_ky_han_giu_nguyen_lai_cua_no(self):
        book = {"loai": "tietkiem", "ten": "KKH", "tien": 10_000_000, "lai": 1.0, "ky": 0, "ngay": "2026-01-01"}
        total, interest, early, maturity = rules.payout(book, date(2026, 11, 25))
        self.assertEqual((early, maturity, round(interest)), (False, None, 89_863))

    def test_tai_tuc_tu_ngay_dao_han(self):
        book = {**BOOK, "ngay": "2025-01-01"}
        renewed = rules.renewed(book, date(2026, 11, 25))
        self.assertEqual((renewed["tien"], renewed["ngay"], renewed["ky"], renewed["lai"]), (106_000_000, "2026-01-01", 12, 6.0))
        self.assertEqual(book["tien"], 100_000_000)  # không sửa bản gốc


class TrenBot(unittest.TestCase):
    def setUp(self):
        h.reset()
        h.at(2026, 11, 25, 10)
        set_main(10_000_000)
        h.say("/taisan tietkiem ACB 100tr 6% 12 thang 01/01/2026")  # chưa tới hạn (01/01/2027)
        h.say("/taisan tietkiem BIDV 100tr 6% 12 thang 01/01/2025")  # đã đáo hạn 01/01/2026

    def book(self, name):
        return next((it for it in assets_repo.load()["items"] if it.get("ten") == name), None)

    def test_the_tat_toan_noi_ro_chua_toi_han(self):
        h.AI.replies["rút sổ ACB về"] = {"viec": "tat_toan", "ten": "ACB"}
        h.say("rút sổ ACB về")
        _, text, buttons = h.press("y:bo:tien")  # bỏ qua câu hỏi "nhận về bao nhiêu": bot tự tính
        self.assertIn("gốc + lãi không kỳ hạn: sổ chưa tới hạn 01/01/2027", text)
        _, done, _ = h.press(h.button(buttons, "y:ok:"))
        self.assertIn("nhận 100.449.315đ (lãi 449.315đ)", done)  # không còn ~105,4tr
        self.assertIn("Rút trước hạn (01/01/2027) nên bot chỉ tính lãi không kỳ hạn", done)
        self.assertEqual(main_balance(), 10_000_000 + 100_449_315)
        income = [e["tien"] for e in h.month_entries() if e["nhom"] == "thu"]
        self.assertEqual(income, [449_315])  # thu nhập tăng 0,45tr, không phải 5,4tr

    def test_so_da_dao_han_van_du_lai_khi_rut(self):
        h.AI.replies["rút sổ BIDV về"] = {"viec": "tat_toan", "ten": "BIDV"}
        h.say("rút sổ BIDV về")
        _, text, buttons = h.press("y:bo:tien")
        self.assertIn("gốc + lãi tới hôm nay", text)
        _, done, _ = h.press(h.button(buttons, "y:ok:"))
        self.assertIn("nhận 106.000.000đ (lãi 6.000.000đ)", done)

    def test_tin_sang_hoi_tai_tuc_hay_rut(self):
        text, rows = digest.morning(date(2026, 11, 25))
        self.assertIn("Sổ <b>BIDV</b> đã đáo hạn 01/01/2026: gốc + lãi 106tr", text)
        self.assertIn("lãi dừng ở ngày đáo hạn, chưa cộng thêm", text)
        self.assertNotIn("<b>ACB</b> đã đáo hạn", text)  # ACB chưa tới hạn
        data = [d for row in rows for _, d in row]
        bidv = self.book("BIDV")["id"]
        self.assertIn(f"ts:taituc:{bidv}", data)
        self.assertIn(f"ts:rutso:{bidv}", data)
        self.assertIsNone(digest.morning(date(2026, 11, 25)))  # nhắc một lần, 10 ngày sau mới nhắc lại nếu chưa trả lời

    def test_bam_tai_tuc_goc_cong_lai_tinh_tu_ngay_dao_han(self):
        bidv = self.book("BIDV")["id"]
        before = net()
        toast, text, _ = h.press(f"ts:taituc:{bidv}")
        self.assertIn("Đã tái tục sổ BIDV", toast)
        self.assertIn("gốc mới 106.000.000đ", text)
        self.assertIn("đáo hạn 01/01/2027", text)
        book = self.book("BIDV")
        self.assertEqual((book["tien"], book["ngay"]), (106_000_000, "2026-01-01"))
        # từ 01/01 tới 25/11 (328 ngày) lãi 6% trên 106tr ≈ 5,7tr: gần 111,7tr như ngân hàng tự tái tục
        self.assertEqual(round((net() - before) / 1e6, 1), 5.7)
        self.assertEqual(h.press(f"ts:taituc:{bidv}")[0].startswith("Sổ này chưa tới hạn"), True)  # đã gia hạn, chưa tới hạn mới

    def test_bam_rut_ve_tai_khoan_chinh(self):
        bidv = self.book("BIDV")["id"]
        toast, text, _ = h.press(f"ts:rutso:{bidv}")
        self.assertIn("Tất toán sổ BIDV", toast)
        self.assertEqual(main_balance(), 10_000_000 + 106_000_000)
        self.assertIsNone(self.book("BIDV"))
        self.assertIn("không còn", h.press(f"ts:rutso:{bidv}")[0])

    def test_3_ngay_truoc_han_van_nhac_nhu_cu(self):
        from services.taisan import reminders
        notes = reminders.maturity_notes(date(2026, 12, 30))
        self.assertEqual(len(notes), 1)
        self.assertIn("Sổ ACB 100tr đáo hạn 01/01", notes[0])


if __name__ == "__main__":
    unittest.main()
