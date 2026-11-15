"""Trợ lý hiểu câu: khuôn các việc, chữ báo hiệu tin không phải khoản chi, nhận ra số và câu trả lời ngắn (tính thuần)."""
import unittest

from domain.troly import spec
from presentation.troly import view


class Khuon(unittest.TestCase):
    def test_truong_viec(self):
        f = spec.F("tien", "tien", "Bao nhiêu?", can=False, goi=True)
        self.assertEqual(f, {"ten": "tien", "kieu": "tien", "hoi": "Bao nhiêu?", "can": False, "goi": True, "chon": None})
        self.assertEqual(spec.GOLD_PRICE, (50, 300))
        self.assertIn((6, "6 tháng"), spec.TERMS)
        self.assertIn("tong_quan", spec.SCREENS)
        self.assertEqual(spec.PERIODS, ("ngay", "tuan", "thang", "thangtruoc"))

    def test_chu_bao_hieu(self):
        self.assertTrue(spec.mentions("gửi tiết kiệm VCB 50tr", spec.TRIGGER_RE))
        self.assertTrue(spec.mentions("gui tiet kiem vcb 50tr", spec.TRIGGER_RE))  # gõ không dấu
        self.assertFalse(spec.mentions("mua váy 350k", spec.TRIGGER_RE))  # "váy" không phải "vay"
        self.assertTrue(spec.mentions("mua vay 350k", spec.TRIGGER_RE))  # không dấu thì vẫn là "vay"
        self.assertTrue(spec.beyond_spending("bao giờ trả xong nợ?"))
        self.assertFalse(spec.beyond_spending("tháng này cà phê hết bao nhiêu"))

    def test_khong_tieu_gi(self):
        for t in ("khong tieu gi", "ko chi dong nao", "chua mua gi ca het", "k tieu"):
            self.assertTrue(spec.NO_SPEND.search(t), t)
        self.assertIsNone(spec.NO_SPEND.search("toi khong co tien"))

    def test_doc_so_va_cau_tra_loi_ngan(self):
        self.assertEqual([spec.number_of(x) for x in (5, 4.7, "4,7%", " 12 ", True, "abc", None)], [5.0, 4.7, 4.7, 12.0, None, None, None])
        self.assertTrue(spec.only_filler("khoảng là tầm hết"))
        self.assertFalse(spec.only_filler("khoảng 5 triệu"))
        self.assertEqual(spec.CASH_IN, ("tat_toan", "ban_vang", "ban_quy", "thu_no"))


class Chu(unittest.TestCase):
    def test_vi_du_va_menu_them(self):
        self.assertTrue(view.EXAMPLES.startswith("• mua 2 chỉ vàng nhẫn hết 27tr"))
        labels = [b[0] for row in view.ADD_MENU for b in row]
        self.assertIn("🏦 Tài khoản, ví", labels)
        self.assertEqual(view.ADD_MENU[-1][-1], view.BACK)


if __name__ == "__main__":
    unittest.main()
