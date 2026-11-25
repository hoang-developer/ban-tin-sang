"""Một định nghĩa dòng tiền (domain/chitieu/flow.py): mọi màn hình cho cùng một số "đã chi".

Lỗi cũ: quẹt thẻ mua tivi 10tr rồi trả thẻ 10tr thì /thang báo chi 20,05tr, /menu báo 10,05tr, ngân sách tổng 15tr báo
"vượt 134%"; trả thẻ còn được tính là "để dành thật"; hoàn tiền thành thu nhập."""
import unittest
from datetime import date

from tests import harness as h

from domain.chitieu import flow
from domain.chitieu.kinds import INCOME
from interface.kehoach import plan as kehoach
from interface.thongbao import digest
from interface.troly import assistant

DAY = date(2026, 11, 10)


class Luat(unittest.TestCase):
    def test_loai_khoan(self):
        self.assertEqual(flow.kind({"nhom": INCOME, "ghichu": "lương"}), flow.THU)
        self.assertEqual(flow.kind({"nhom": "mua", "ghichu": "quẹt thẻ mua tivi"}), flow.CHI)  # quẹt thẻ là chi
        self.assertEqual(flow.kind({"nhom": "khac", "ghichu": "trả thẻ tín dụng"}), flow.TRA_GOC)  # theo ghi chú
        self.assertEqual(flow.kind({"nhom": "khac", "ghichu": "chú Tư", "no": 3}), flow.TRA_GOC)  # gắn khoản nợ
        self.assertEqual(flow.kind({"nhom": "r1", "ghichu": "góp xe"}, debt_group="r1"), flow.TRA_GOC)  # nhóm Trả nợ
        self.assertEqual(flow.kind({"nhom": "r1", "ghichu": "góp xe"}), flow.CHI)  # không biết nhóm Trả nợ là nhóm nào

    def test_tong(self):
        items = [{"nhom": INCOME, "tien": 20_000_000, "ghichu": "lương"},
                 {"nhom": "mua", "tien": 10_000_000, "ghichu": "tivi"},
                 {"nhom": "khac", "tien": 10_000_000, "ghichu": "trả thẻ"},
                 {"nhom": "mua", "tien": -500_000, "ghichu": "hoàn tiền tivi", "hoan": True}]
        self.assertEqual((flow.spent(items), flow.income(items), flow.repaid(items)), (9_500_000, 20_000_000, 10_000_000))
        self.assertEqual(flow.debt_group_of({"moi": ["r1"], "ten": {"r1": "🏦 Trả nợ"}}), "r1")
        self.assertIsNone(flow.debt_group_of({}))


class MoiManHinhCungMotSo(unittest.TestCase):
    def setUp(self):
        h.reset()
        h.at(2026, 11, 10, 10)

    def ghi(self, with_group):
        if with_group:
            h.say("/nhom them 🏦 Trả nợ: trả nợ, thẻ tín dụng, trả thẻ")
        for text in ("+ lương 20tr", "quẹt thẻ mua tivi 10tr", "trả thẻ tín dụng 10tr", "ăn trưa 50k"):
            h.say(text)

    def check(self):
        report = h.say("/thang")[0]
        self.assertIn("Chi 10.050.000đ · 2 khoản", report)
        self.assertIn("Trả gốc nợ 10tr (không tính là chi)", report)
        self.assertIn("Thu 20tr → 🔴 còn −50k", report)  # còn lại sau chi và trả gốc
        self.assertIn("đã chi 10,05tr", h.say("/menu")[0])
        self.assertIn("Tổng chi: 10,05tr/15tr (67%)", h.say("/ngansach tổng 15tr")[0])  # lỗi cũ: 20,05tr/15tr (134%)
        self.assertIn("Đã chi 10,05tr", h.say("/dubao tatca")[0])
        self.assertEqual(kehoach.numbers(DAY)["spent"], 10_050_000)
        self.assertIn("Hôm nay chi 10,05tr", digest.today_line(DAY))
        self.assertIn("đã chi 10,05tr", assistant.finance_facts(DAY))
        self.assertIn("10.050.000đ", h.say("/hoi tháng này chi bao nhiêu")[0])
        self.assertNotIn("Để dành thật 10tr", h.say("/tietkiem")[0])  # trả thẻ không phải để dành

    def test_co_nhom_tra_no(self):
        self.ghi(with_group=True)
        self.check()

    def test_chua_co_nhom_tra_no_nhan_theo_ghi_chu(self):
        self.ghi(with_group=False)
        self.check()

    def test_hoi_rieng_nhom_tra_no_van_ra(self):
        self.ghi(with_group=True)
        self.assertIn("10.000.000đ", h.say("/hoi tháng này trả nợ bao nhiêu")[0])


class HoanTien(unittest.TestCase):
    def setUp(self):
        h.reset()
        h.at(2026, 11, 10, 10)

    def test_hoan_tien_giam_chi_nhom_goc_khong_thanh_thu_nhap(self):
        h.say("áo khoác 300k")
        reply, _ = h.say("hoàn tiền áo khoác 50k")
        self.assertIn("↩️ hoàn 50.000đ · 🛍️ Mua sắm", reply)
        e = h.month_entries()[-1]
        self.assertEqual((e["tien"], e["nhom"], e.get("hoan")), (-50_000, "mua", True))
        report = h.say("/thang")[0]
        self.assertIn("Chi 250.000đ", report)
        self.assertNotIn("Thu", report)  # không còn thu nhập ảo 50k

    def test_dau_cong_van_la_thu(self):
        h.say("+ hoàn tiền thuế 2tr")  # người dùng tự đánh dấu là thu
        e = h.month_entries()[-1]
        self.assertEqual((e["tien"], e["nhom"], e.get("hoan")), (2_000_000, INCOME, None))

    def test_tong_bang_0_khong_loi(self):
        h.say("áo 50k")
        h.say("hoàn tiền áo 50k")
        self.assertIn("Chi 0đ", h.say("/thang")[0])


if __name__ == "__main__":
    unittest.main()
