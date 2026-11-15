"""Lệnh quỹ (ghi, khớp, hoán đổi, sửa ccq, tạm dừng) gọi thẳng service; định dạng và đọc ngày/số là hàm thuần."""
import unittest
from datetime import date

from tests import harness as h
from tests.test_dautu import setup_plan, units

from domain.common.format import short, vn_num, vnd
from domain.common.money import number
from domain.dautu.calendar import read_date
from domain.dautu.text import money, units_text
from repositories.dautu import fund as fund_repo
from services.dautu import orders, switch


class HamThuan(unittest.TestCase):
    def test_dinh_dang(self):
        self.assertEqual((vn_num(1766.65), vn_num(1234, 0), vn_num(5, 1, sign=True)), ("1.766,65", "1.234", "+5,0"))
        self.assertEqual((short(1_250_000), short(35_000), short(999_800), vnd(1500)), ("1,25tr", "35k", "1tr", "1.500đ"))
        self.assertEqual((money(500), money(2_000_000), units_text(66.0), units_text(66.4), units_text(66.43)),
                         ("0đ", "2tr", "66", "66,4", "66,43"))

    def test_doc_so(self):
        self.assertEqual((number("1.000"), number("0,05"), number("95,5"), number(" 7 ")), (1000.0, 0.05, 95.5, 7.0))
        with self.assertRaises(ValueError):
            number("abc")

    def test_doc_ngay(self):
        today = date(2026, 11, 15)
        self.assertEqual(read_date("dadat 1tr 9/11", today), date(2026, 11, 9))
        self.assertEqual(read_date("20/12", date(2026, 1, 15)), date(2025, 12, 20))  # xa hơn 6 tháng tới: năm trước
        self.assertEqual(read_date("9/11/2025", today), date(2025, 11, 9))
        self.assertIsNone(read_date("không có ngày", today))
        self.assertIsNone(read_date("31/2", today))


class Lenh(unittest.TestCase):
    def setUp(self):
        setup_plan()

    def test_dat_lenh_roi_khop(self):
        h.at(2026, 9, 10, 10)
        cfg = fund_repo.load()
        before = len(cfg["lenh"])
        note = orders.record_order(500_000, quiet=True)
        self.assertIn("Đã ghi lệnh mua VMEEF 500.000đ", note)
        cfg = fund_repo.load()
        self.assertEqual((len(cfg["lenh"]), cfg["lenh"][-1]["trang_thai"]), (before + 1, "cho"))
        h.at(2026, 9, 11, 17, 30)
        got = orders.match_details()
        self.assertTrue(got and got[0][0] == "VMEEF")
        self.assertIn("đã khớp phiên", got[0][1])
        self.assertEqual(fund_repo.load()["lenh"][-1]["trang_thai"], "khop")
        self.assertEqual(orders.match_orders(), [])  # khớp rồi không báo lại

    def test_sua_ccq_lenh_khop_gan_nhat(self):
        h.at(2026, 9, 10, 17, 30)
        orders.match_orders()
        self.assertIn("Chưa có lệnh nào", orders.fix_units("0"))
        self.assertIn("Gõ số ccq", orders.fix_units("abc"))
        text = orders.fix_units("70,5")
        self.assertIn("70,5 ccq", text)
        self.assertEqual(units("VMEEF"), 70.5)

    def test_gop_va_rut_quy_cho(self):
        cfg = fund_repo.load()
        notes = []
        left = orders.add_money(cfg, 2_000_000, "2026-09", from_main=False, notes=notes)
        fund_repo.save(cfg)
        taken, remain = orders.take_money(cfg, 99_000_000, to_main=False)
        self.assertEqual((taken, remain), (left, 0))

    def test_tam_dung_ky(self):
        h.at(2026, 10, 5, 10)
        period = orders.current_period(fund_repo.load())
        self.assertIn("Kỳ này đã qua", orders.skip("2026-01"))
        self.assertIn("Tạm dừng góp tháng", orders.skip(period))
        self.assertTrue(fund_repo.load()["ky"][period]["bo"])

    def test_phan_tich_cau_dat_lenh(self):
        cfg = fund_repo.load()
        now = h.CLOCK["now"]
        self.assertIn("Ngày đặt lệnh chưa tới", orders.order_spec(cfg, "30/12", now))
        day, session_day, period = orders.order_spec(cfg, "9/9", now)
        self.assertEqual(day, date(2026, 9, 9))
        self.assertTrue(session_day > day and period.startswith("2026-"))


class HoanDoi(unittest.TestCase):
    def setUp(self):
        setup_plan()
        h.at(2026, 9, 14, 20)
        h.say("/dautu taicocau 15,5tr")
        h.at(2026, 9, 17, 17, 30)
        h.run_jobs()

    def test_hoan_doi_hai_buoc(self):
        h.at(2026, 9, 22, 10)
        note = orders.record_switch(100, quiet=True)
        self.assertIn("Đã ghi hoán đổi 100 ccq VFF → VMEEF", note)
        self.assertEqual(len(switch.open_switches()), 1)
        h.at(2026, 9, 24, 17, 30)
        self.assertIn("đang chuyển sang VMEEF", orders.match_orders()[0])
        order = switch.open_switches()[0]
        self.assertEqual(order["trang_thai"], "chuyen")
        self.assertIsInstance(switch.switch_calc(order["id"], date(2026, 10, 30), date(2026, 10, 1)), str)  # chưa có NAV
        self.assertIsInstance(switch.switch_calc(999, date(2026, 9, 24), date(2026, 10, 1)), str)
        h.at(2026, 10, 2, 10)  # có NAV ngày mua 01/10
        preview = switch.switch_preview(order["id"], date(2026, 9, 24), date(2026, 10, 1), 210.5)
        self.assertIn("(theo Fmarket)", preview)
        before = units("VMEEF")
        self.assertIn("Hoán đổi xong", switch.finish_switch(order["id"], date(2026, 9, 24), date(2026, 10, 1), 210.5))
        self.assertEqual(units("VMEEF"), round(before + 210.5, 2))
        self.assertEqual(switch.open_switches(), [])

    def test_nhac_sau_bay_ngay(self):
        h.at(2026, 9, 22, 10)
        orders.record_switch(100, quiet=True)
        self.assertEqual(switch.switch_prompts(date(2026, 9, 28)), [])
        prompts = switch.switch_prompts(date(2026, 9, 29))
        self.assertEqual(len(prompts), 1)
        self.assertIn("xong chưa?", prompts[0][0])

    def test_nav_theo_ngay(self):
        h.at(2026, 10, 2, 10)
        fund = fund_repo.load()
        day, nav = switch.nav_on(fund, date(2026, 10, 1))
        self.assertEqual(day, date(2026, 10, 1))
        self.assertGreater(nav, 0)
        self.assertIsNone(switch.nav_on(fund, date(2027, 6, 1)))


if __name__ == "__main__":
    unittest.main()
