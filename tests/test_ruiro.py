"""Chính sách rủi ro khi ghi tiền (PR 2.1, domain/chitieu/risk.py): chi nhỏ rõ ràng ghi ngay; khoản lớn, nhiều số tiền,
ngày chưa tới hỏi lại bằng thẻ; số rất lớn bấm hai lần; việc đổi tài sản luôn qua thẻ."""
import unittest
from datetime import date

from tests import harness as h

from domain.chitieu import risk
from domain.chitieu.parse import parse_line

DAY = date(2026, 11, 20)


def level(text):
    return risk.text_level(text, DAY, lambda line: parse_line(line, DAY, None, {}))


class LuatThuan(unittest.TestCase):
    def test_chi_nho_ghi_ngay_chi_lon_hoi(self):
        self.assertEqual(level("cà phê 35k"), risk.GHI_NGAY)
        self.assertEqual(level("cà phê 35"), risk.GHI_NGAY)  # số trơn vẫn là nghìn, như cũ
        self.assertEqual(level("đổ xăng 2tr"), risk.GHI_NGAY)  # đúng ngưỡng
        self.assertEqual(level("tiền nhà 2,1tr"), risk.HOI_LAI)

    def test_so_rat_lon_xac_nhan_kep(self):
        self.assertEqual(level("tiền nhà 50tr"), risk.XAC_NHAN_KEP)
        self.assertEqual(level("+ thưởng 60tr"), risk.XAC_NHAN_KEP)

    def test_thu_do_luat_nhan_ra_ghi_ngay(self):
        self.assertEqual(level("+ lương 20tr"), risk.GHI_NGAY)
        self.assertEqual(level("lương 20tr"), risk.GHI_NGAY)  # từ khóa nhóm Thu nhập

    def test_nhieu_so_tien_va_ngay_chua_toi(self):
        self.assertEqual(level("ăn trưa 50k cà phê 30k"), risk.HOI_LAI)
        self.assertEqual(level("27/11/2026 mua sách 200k"), risk.HOI_LAI)
        self.assertEqual(level("hôm qua phở 50k"), risk.GHI_NGAY)

    def test_nhieu_dong_lay_muc_chat_nhat(self):
        self.assertEqual(level("cà phê 35k\ntiền nhà 3tr"), risk.HOI_LAI)
        self.assertEqual(level("cà phê 35k\ntiền nhà 80tr"), risk.XAC_NHAN_KEP)
        self.assertEqual(level("không có số"), risk.GHI_NGAY)

    def test_viec_cua_tro_ly(self):
        def job(viec, tien=0, source=risk.AI):
            return risk.decide(risk.Signal(amount=tien, direction=risk.THU if viec == "thu" else risk.CHI,
                                           source=source, job=viec))
        self.assertEqual(job("tai_khoan", 1_000), risk.HOI_LAI)  # đổi tài sản: luôn qua thẻ
        self.assertEqual(job("thu", 1_000_000), risk.GHI_NGAY)
        self.assertEqual(job("thu", 5_000_000), risk.HOI_LAI)  # AI đoán chiều thu: khoản lớn phải xác nhận
        self.assertEqual(job("tra_no", 3_000_000), risk.HOI_LAI)
        self.assertEqual(job("doi_chieu"), risk.GHI_NGAY)  # tự có bước hỏi riêng
        self.assertEqual(job("quy", 1_000, risk.ANH), risk.HOI_LAI)
        self.assertEqual(set(risk.CONFIRM_JOBS) & set(risk.LEDGER_JOBS), set())

    def test_mua_quy_cho_lon(self):
        self.assertTrue(risk.big_side_buy(12_000_000, 4_000_000))
        self.assertFalse(risk.big_side_buy(11_000_000, 4_000_000))
        self.assertFalse(risk.big_side_buy(12_000_000, 0))


class TrenBot(unittest.TestCase):
    def setUp(self):
        h.reset()
        h.at(2026, 11, 20, 10)

    def test_khoan_lon_hoi_roi_moi_ghi(self):
        text, buttons = h.say("tiền nhà 3tr")
        self.assertIn("khoản lớn 3.000.000đ", text)
        self.assertEqual(h.month_entries(), [])
        _, text, _ = h.press(h.button(buttons, "y:chi:"))
        self.assertIn("Đã ghi 3.000.000đ", text)
        self.assertEqual(len(h.month_entries()), 1)

    def test_bam_khong_ghi(self):
        _, buttons = h.say("tiền nhà 3tr")
        h.press(h.button(buttons, "y:huy:"))
        self.assertEqual(h.month_entries(), [])

    def test_so_rat_lon_bam_hai_lan(self):
        text, buttons = h.say("tiền nhà 50tr")
        self.assertIn("Kiểm tra lại số 0", text)
        _, text, buttons = h.press(h.button(buttons, "y:kep:"))
        self.assertIn("Chắc chắn ghi 50.000.000đ", text)
        self.assertEqual(h.month_entries(), [])
        _, text, _ = h.press(h.button(buttons, "y:chi:"))
        self.assertIn("Đã ghi 50.000.000đ", text)

    def test_nhieu_dong_chi_neu_dong_lon(self):
        text, buttons = h.say("cà phê 35k\ntiền nhà 3tr")
        self.assertIn("tiền nhà 3tr", text)
        self.assertNotIn("cà phê", text)
        self.assertEqual(h.month_entries(), [])
        _, text, _ = h.press(h.button(buttons, "y:chi:"))
        self.assertEqual(len(h.month_entries()), 2)

    def test_chi_nho_va_luong_ghi_ngay(self):
        for text in ("cà phê 35k", "+ lương 20tr", "lương 20tr"):
            self.assertIn("Đã ghi", h.say(text)[0], text)
        self.assertEqual(len(h.month_entries()), 3)

    def test_ngay_chua_ro_hoi_ngay_truoc(self):
        text, _ = h.say("27/11 đóng học 3tr")  # một câu hỏi mỗi lần: hỏi ngày, chọn xong là ghi
        self.assertIn("chưa tới", text)

    def test_ai_hieu_khoan_chi_lon_van_hoi(self):
        h.AI.replies["tiền nhà ba triệu"] = {"viec": "chi", "tien": 3000000, "ghi_chu": "tiền nhà"}
        text, buttons = h.say("tiền nhà ba triệu")
        self.assertIn("Kiểm tra lại", text)
        self.assertEqual(h.month_entries(), [])
        _, text, _ = h.press(h.button(buttons, "y:chi:"))
        self.assertIn("Đã ghi 3.000.000đ", text)

    def test_ai_hieu_khoan_thu_nho_ghi_ngay(self):
        h.AI.replies["mẹ cho ít tiền 500k"] = {"viec": "thu", "tien": 500000, "ghi_chu": "mẹ cho"}
        text, _ = h.say("mẹ cho ít tiền 500k")
        self.assertIn("Đã ghi 500.000đ", text)
        self.assertTrue(h.AI.calls)


if __name__ == "__main__":
    unittest.main()
