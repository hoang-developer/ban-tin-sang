"""Đầu tư quỹ mở: lịch phiên giao dịch (domain thuần), nhớ tạm dữ liệu Fmarket và phiên kế tiếp (service qua Fmarket giả)."""
import unittest
from datetime import date, datetime

from tests import harness as h
from tests.test_dautu import setup_plan

from domain.common.dates import VN_TZ
from domain.dautu import calendar as cal
from infrastructure import web
from repositories.dautu import market as market_repo
from services.dautu import market as market

D = date


class Lich(unittest.TestCase):
    def test_thang(self):
        self.assertEqual(cal.ym_of(D(2026, 1, 5)), "2026-01")
        self.assertEqual((cal.ym_add("2026-11", 2), cal.ym_add("2026-01", -1), cal.ym_add("2026-12", 1)),
                         ("2027-01", "2025-12", "2027-01"))
        self.assertEqual(cal.months("2026-10", "2027-01"), ["2026-10", "2026-11", "2026-12", "2027-01"])
        self.assertEqual((cal.months("2026-11", "2026-10"), cal.ym_text("2026-09")), ([], "9/2026"))

    def test_ngay_lam_viec_va_dong_so(self):
        friday = D(2026, 10, 16)
        self.assertEqual((cal.weekdays_after(friday, 1), cal.weekdays_after(friday, 3)), (D(2026, 10, 19), D(2026, 10, 21)))
        self.assertEqual((cal.cutoff_day(D(2026, 10, 19)), cal.cutoff_day(D(2026, 10, 20))), (D(2026, 10, 16), D(2026, 10, 19)))

    def test_phien_ke_tiep_theo_lich_nav(self):
        tue_thu = [(D(2026, 10, d), 1.0) for d in (1, 6, 8, 13, 15, 20)]  # quỹ chỉ có NAV thứ Ba, thứ Năm
        self.assertEqual(cal.next_trading_from(tue_thu, D(2026, 10, 20)), D(2026, 10, 22))  # tự đoán theo thứ
        self.assertEqual(cal.next_trading_from(tue_thu, D(2026, 10, 15)), D(2026, 10, 20))  # có NAV sau đó: lấy đúng ngày
        self.assertEqual(cal.next_trading_from(tue_thu, D(2026, 10, 20), include=True), D(2026, 10, 20))
        self.assertEqual(cal.next_trading_from([], D(2026, 10, 16)), D(2026, 10, 19))  # không có NAV: thứ Hai–thứ Sáu

    def test_doc_phien_fmarket(self):
        phien = {"tradingTimeString": "01/10/2026", "closedOrderBookTimeString": "14:40 30/09/2026"}
        trading, closing = cal.parse_session(phien)
        self.assertEqual((trading, closing), (D(2026, 10, 1), datetime(2026, 9, 30, 14, 40, tzinfo=VN_TZ)))
        for bad in ({}, {"tradingTimeString": "x", "closedOrderBookTimeString": "y"}, None):
            with self.assertRaises((KeyError, TypeError, ValueError)):
                cal.parse_session(bad)

    def test_ngay_dong_so_som_nhat_con_kip(self):
        at = lambda d, hh, mm: datetime(2026, 10, d, hh, mm, tzinfo=VN_TZ)  # noqa: E731
        self.assertEqual(cal.earliest_order_day(at(16, 10, 0)), D(2026, 10, 16))  # thứ Sáu trước 14:40
        self.assertEqual(cal.earliest_order_day(at(16, 14, 40)), D(2026, 10, 19))  # đúng 14:40: đã đóng
        self.assertEqual(cal.earliest_order_day(at(17, 10, 0)), D(2026, 10, 19))  # thứ Bảy
        g = cal.guessed_session(D(2026, 10, 20))
        self.assertEqual((g["phien"], g["dong"], g["du_phong"]), (D(2026, 10, 20), datetime(2026, 10, 19, 14, 40, tzinfo=VN_TZ), True))


class DichVu(unittest.TestCase):
    def setUp(self):
        setup_plan()
        h.at(2026, 10, 2, 10)
        self.cfg = {"ma": "VMEEF", "id": h.FUND_ID["VMEEF"]}
        self.calls = []
        self.real = web.http_json

        def counting(url, body=None):
            self.calls.append(url)
            return self.real(url, body)
        web.http_json = counting
        self.addCleanup(setattr, web, "http_json", self.real)
        # setup_plan đã nhớ NAV/thông tin; xóa để đo từ đầu
        from repositories import keys, store
        store.delete(keys.fund_nav("VMEEF"))
        store.delete(keys.fund_info("VMEEF"))

    def fetches(self, word):
        return sum(1 for u in self.calls if word in u)

    def test_nav_nho_tam_hai_tieng(self):
        first = market.nav_history(self.cfg)
        self.assertTrue(first and first[-1][0] <= D(2026, 10, 2))
        self.assertEqual(self.fetches("get-nav-history"), 1)
        self.assertEqual(market.nav_history(self.cfg), first)
        self.assertEqual(self.fetches("get-nav-history"), 1)  # còn trong 2 tiếng: dùng bản nhớ
        market.nav_history(self.cfg, fresh=True)
        self.assertEqual(self.fetches("get-nav-history"), 2)
        h.at(2026, 10, 2, 13)  # quá 2 tiếng
        market.nav_history(self.cfg)
        self.assertEqual(self.fetches("get-nav-history"), 3)
        self.assertEqual(market_repo.load_nav("VMEEF")["ma"], "VMEEF")

    def test_nguon_loi_thi_dung_ban_da_nho_hoac_rong(self):
        self.assertEqual(market.nav_history({"ma": "XYZ", "id": 999}), [])  # chưa nhớ gì, nguồn lỗi (id lạ)
        good = market.nav_history(self.cfg)

        def broken(url, body=None):
            raise RuntimeError("hết mạng")
        web.http_json = broken
        h.at(2026, 10, 2, 14)  # quá hạn nhớ, nguồn lỗi
        self.assertEqual(market.nav_history(self.cfg), good)

    def test_thong_tin_quy_nho_tam_mot_tieng(self):
        info = market.fund_info(self.cfg)
        self.assertIn("phien", info)
        self.assertEqual(self.fetches(f"/products/{h.FUND_ID['VMEEF']}"), 1)
        market.fund_info(self.cfg)
        self.assertEqual(self.fetches(f"/products/{h.FUND_ID['VMEEF']}"), 1)
        h.at(2026, 10, 2, 11, 5)  # quá 1 tiếng
        market.fund_info(self.cfg)
        self.assertEqual(self.fetches(f"/products/{h.FUND_ID['VMEEF']}"), 2)

    def test_phien_theo_fmarket_roi_theo_lich_tu_doan(self):
        s = market.session(self.cfg)
        self.assertEqual((s["du_phong"], s["phien"] > D(2026, 10, 2)), (False, True))
        self.assertEqual(market.current_period(self.cfg), cal.ym_of(s["dong"].date()))
        orig = market.fund_info
        market.fund_info = lambda cfg, fresh=False: None  # không lấy được thông tin quỹ
        self.addCleanup(setattr, market, "fund_info", orig)
        guess = market.session(self.cfg)
        self.assertTrue(guess["du_phong"])
        self.assertEqual(guess["dong"].hour, 14)

    def test_han_dat_lenh_cuoi_thang(self):
        h.at(2026, 9, 30, 8, 35)
        deadline, s = market.is_deadline(self.cfg)
        self.assertTrue(deadline)
        self.assertEqual(s["phien"], D(2026, 10, 1))
        h.at(2026, 9, 30, 15, 0)  # qua 14:40: kỳ đã sang tháng sau
        self.assertEqual(market.is_deadline(self.cfg)[0], False)
        self.assertEqual(market.current_period(self.cfg), "2026-10")


if __name__ == "__main__":
    unittest.main()
