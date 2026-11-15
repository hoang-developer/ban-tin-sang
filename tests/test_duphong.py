"""Quỹ dự phòng: luật thuần của domain (không kho, không giờ giả) và service qua kho giả."""
import unittest
from datetime import date

from tests import harness as h

from domain.common.dates import add_months
from domain.duphong.reserve import MIN_DAYS, build_status, milestone, record_deposit
from repositories.duphong import reserve as reserve_repo
from services.duphong import reserve as service

DAY = date(2026, 11, 10)


def status(cfg=None, essential=(0, {}, 0), rows=(), flows=(0, 0, 0), day=DAY):
    return build_status(cfg or {}, day, essential, list(rows), flows)


class Domain(unittest.TestCase):
    def test_chi_tu_dat_tinh_muc_tieu_va_so_thang_con_lai(self):
        s = status({"chi": 12_000_000, "thang": 6, "bat_dau": "2026-11-10"}, rows=[("Quỹ dự phòng", 6_000_000)])
        self.assertEqual((s.monthly, s.target, s.missing, s.balance), (12_000_000, 72_000_000, 66_000_000, 6_000_000))
        self.assertEqual(s.covered, 0.5)
        self.assertEqual(s.deadline, date(2027, 11, 10))
        self.assertEqual((s.months_left, s.per_month, s.overdue, s.manual), (12, 5_500_000, False, True))

    def test_chua_du_ngay_ghi_chep_thi_chua_tinh_chi_thiet_yeu(self):
        self.assertEqual(status(essential=(9_000_000, {"an": 9_000_000}, MIN_DAYS - 1)).monthly, 0)
        s = status(essential=(9_000_000, {"an": 9_000_000}, MIN_DAYS))
        self.assertEqual((s.monthly, s.target, s.manual), (9_000_000, 54_000_000, False))

    def test_qua_han_va_du_quy(self):
        late = status({"chi": 10_000_000, "han": 6, "bat_dau": "2026-01-01"}, rows=[("x", 1_000_000)])
        self.assertTrue(late.overdue)
        self.assertEqual(late.months_left, 1)  # còn thiếu thì tối thiểu 1 tháng
        full = status({"chi": 10_000_000, "thang": 1}, rows=[("x", 10_000_000)])
        self.assertEqual((full.missing, full.per_month, full.overdue), (0, 0, False))

    def test_du_thu_chi_chi_tinh_khi_du_20_ngay(self):
        self.assertIsNone(status(flows=(5, 9, 19)).surplus)
        self.assertEqual(status(flows=(5, 9, 20)).surplus, 4)
        self.assertIsNone(status(flows=(5, 0, 30)).surplus)  # không có thu: không tính

    def test_moc_vua_vuot(self):
        two = {"chi": 10, "thang": 6}
        mk = lambda covered: status(two, rows=[("x", covered * 10)])  # noqa: E731
        self.assertEqual(milestone(mk(0.5), mk(1.2)), "đủ 1 tháng chi")
        self.assertEqual(milestone(mk(2.9), mk(3.1)), "đủ 3 tháng chi")
        self.assertEqual(milestone(mk(5.9), mk(6.0)), "ĐẠT MỤC TIÊU")
        self.assertIsNone(milestone(mk(1.2), mk(1.5)))  # không vượt mốc mới
        self.assertIsNone(milestone(status(), status(rows=[("x", 5)])))  # chưa có chi thiết yếu

    def test_ghi_nhan_nap_va_rut(self):
        cfg = record_deposit({}, DAY, 2_000_000)
        self.assertEqual(cfg, {"bat_dau": "2026-11-10", "nap": {"2026-11": 2_000_000}})
        cfg = record_deposit(cfg, date(2026, 11, 20), 1_000_000)
        self.assertEqual(cfg["nap"], {"2026-11": 3_000_000})
        self.assertEqual(record_deposit(cfg, DAY, -500_000)["nap"], {"2026-11": 3_000_000})  # rút không đổi số đã nạp
        many = {"nap": {f"2025-{m:02d}": 1 for m in range(1, 13)}, "bat_dau": "2025-01-01"}
        kept = record_deposit(many, DAY, 5)["nap"]
        self.assertEqual((len(kept), "2025-01" in kept, kept["2026-11"]), (12, False, 5))  # chỉ giữ 12 tháng gần nhất
        self.assertEqual(len(many["nap"]), 12)  # cấu hình gốc không bị sửa

    def test_cong_thang(self):
        self.assertEqual(add_months(date(2026, 1, 31), 1), date(2026, 2, 28))
        self.assertEqual(add_months(date(2026, 11, 10), 14), date(2028, 1, 10))


class Service(unittest.TestCase):
    def setUp(self):
        h.reset()
        h.at(2026, 11, 10, 10)

    def test_nap_cong_so_da_nap_va_bao_moc(self):
        service.set_monthly(10_000_000)
        c = service.change(12_000_000, DAY, from_main=False)
        self.assertEqual((c.before.balance, c.after.balance, c.milestone), (0, 12_000_000, "đủ 1 tháng chi"))
        self.assertEqual(reserve_repo.deposited_in("2026-11"), 12_000_000)
        r = service.change(-11_000_000, DAY, from_main=False)
        self.assertEqual((r.after.balance, r.milestone), (1_000_000, None))
        self.assertEqual(reserve_repo.deposited_in("2026-11"), 12_000_000)

    def test_tinh_tai_san_vao_quy(self):
        h.say("/taisan tietkiem TCB 50tr 5% 6 thang 01/11/2026")
        t = service.toggle("tcb")
        self.assertEqual((t.found, t.label, t.enabled), (True, "TCB", True))
        self.assertEqual(service.toggle("TCB").enabled, False)
        miss = service.toggle("không có")
        self.assertEqual((miss.found, miss.available), (False, ["TCB"]))
        self.assertEqual(service.savings_books(), [("TCB", 5, False)])

    def test_cai_dat(self):
        service.set_months(9)
        service.set_deadline(18, DAY)
        service.set_monthly(8_000_000)
        self.assertEqual(reserve_repo.load(), {"thang": 9, "han": 18, "bat_dau": "2026-11-10", "chi": 8_000_000})
        service.clear_monthly()
        self.assertNotIn("chi", reserve_repo.load())


if __name__ == "__main__":
    unittest.main()
