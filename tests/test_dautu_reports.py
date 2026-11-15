"""Việc đầu tư quỹ phục vụ chỗ khác: gợi ý chia lương, dòng NAV bản tin tối, báo danh mục, tin tối lãi/lỗ."""
import unittest
from datetime import date

from tests import harness as h
from tests.test_dautu import setup_plan

from domain.dautu.plan import WATCH, is_active
from repositories.dautu import fund as fund_repo
from services.dautu import reports


class Chung(unittest.TestCase):
    def test_trang_thai_bat_tat(self):
        self.assertFalse(is_active({}))
        self.assertTrue(is_active({"ma": "VMEEF"}))
        self.assertFalse(is_active({"ma": "VMEEF", "tat": True}))
        self.assertIn("VIC", WATCH)


class ChuaBat(unittest.TestCase):
    def test_chua_bat_thi_khong_co_gi(self):
        h.reset()
        h.at(2026, 10, 2, 21)
        self.assertIsNone(reports.salary_part(date(2026, 10, 2)))
        self.assertIsNone(reports.evening_line(date(2026, 10, 2)))
        self.assertIsNone(reports.daily_report(h.CLOCK["now"]))


class DaBat(unittest.TestCase):
    def setUp(self):
        setup_plan()
        h.at(2026, 10, 2, 21)

    def test_phan_gop_trong_chia_luong(self):
        part = reports.salary_part(date(2026, 10, 2))
        self.assertEqual(part["ma"], "VMEEF")
        self.assertEqual(part["gop"], 5_000_000)  # 4tr VA + 1tr góp thêm VFF
        cfg = fund_repo.load()
        cfg["ky"] = {"2026-10": {"bo": True}}
        fund_repo.save(cfg)
        paused = reports.salary_part(date(2026, 10, 2))
        self.assertEqual((paused["gop"], paused["note"]), (0, "tháng này tạm dừng"))

    def test_dong_nav_ban_tin_toi(self):
        line = reports.evening_line(date(2026, 10, 2))
        self.assertTrue(line.startswith("💹 VMEEF "))
        self.assertIn("cách đỉnh 52 tuần", line)
        self.assertIn("VFF", line)  # quỹ chờ có dòng riêng (12 tháng)
        self.assertIn("(hôm nay,", line)

    def test_tin_toi_lai_lo(self):
        h.at(2026, 9, 10, 17, 30)
        h.run_jobs()  # lệnh 9/9 khớp: có ccq để báo lãi/lỗ
        h.at(2026, 10, 1, 21, 5)
        text, buttons = reports.daily_report(h.CLOCK["now"])
        self.assertIn("📊 <b>Quỹ tối 01/10</b>", text)
        self.assertIn("VMEEF", text)
        self.assertEqual(buttons, [[("📈 Chi tiết", "dt:xem")]])
        cfg = fund_repo.load()
        cfg["baocao_toi"] = False
        fund_repo.save(cfg)
        self.assertIsNone(reports.daily_report(h.CLOCK["now"]))

    def test_bao_danh_muc_moi(self):
        cfg = fund_repo.load()
        orig = reports.fund_info
        reports.fund_info = lambda c, fresh=False: {"top_luc": "30/09", "top": [{"ma": "VIC", "tyle": 5.5}, {"ma": "FPT", "tyle": 3}]}
        self.addCleanup(setattr, reports, "fund_info", orig)
        text = reports.holdings_alert(cfg)
        self.assertIn("top 10 có VIC 5,5%", text)
        self.assertEqual(fund_repo.load()["top_luc"], "30/09")  # ghi nhớ đã báo
        self.assertIsNone(reports.holdings_alert(fund_repo.load()))  # báo rồi: không báo lại
        reports.fund_info = lambda c, fresh=False: {"top_luc": "31/10", "top": [{"ma": "FPT", "tyle": 3}]}
        self.assertIsNone(reports.holdings_alert(fund_repo.load()))  # danh mục mới không có nhóm theo dõi


if __name__ == "__main__":
    unittest.main()
