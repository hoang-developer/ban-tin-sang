"""Việc theo giờ: luật khung giờ, đánh dấu việc đã làm trong ngày, chạy nhiều lần trong ngày không làm lại."""
import unittest
from datetime import datetime

from tests import harness as h

from domain.lich import schedule
from interface.lich import jobs
from repositories.lich import jobs as repo


def at(day, hour, minute=0):
    return datetime(2026, 11, day, hour, minute, tzinfo=h.VN_TZ)


class Luat(unittest.TestCase):
    def test_khung_gio(self):
        self.assertTrue(schedule.between(at(13, 6, 45), (6, 45), (12, 0)))
        self.assertTrue(schedule.between(at(13, 11, 59), (6, 45), (12, 0)))
        self.assertFalse(schedule.between(at(13, 12, 0), (6, 45), (12, 0)))  # mốc cuối không tính
        self.assertFalse(schedule.between(at(13, 6, 44), (6, 45), (12, 0)))

    def test_ngay_giao_dich(self):
        self.assertTrue(schedule.trading_day(at(13, 9)))   # thứ sáu
        self.assertFalse(schedule.trading_day(at(14, 9)))  # thứ bảy
        self.assertFalse(schedule.trading_day(at(15, 9)))  # chủ nhật

    def test_tin_quyen_loi(self):
        title = schedule.normalize("FPT CHỐT QUYỀN trả cổ tức")
        self.assertTrue(any(w in title for w in schedule.DIVIDEND_WORDS))
        self.assertFalse(any(w in schedule.normalize("FPT ký hợp đồng mới") for w in schedule.DIVIDEND_WORDS))


class DanhDau(unittest.TestCase):
    def setUp(self):
        h.reset()

    def test_danh_dau_theo_ngay(self):
        self.assertFalse(repo.done_today("ban_tin_sang", at(13, 7)))
        repo.mark_done("ban_tin_sang", at(13, 7))
        self.assertTrue(repo.done_today("ban_tin_sang", at(13, 20)))
        self.assertFalse(repo.done_today("ban_tin_sang", at(14, 7)))  # sang ngày khác là việc mới
        self.assertFalse(repo.done_today("gui_doan", at(13, 7)))      # việc khác chưa làm


class ChayLich(unittest.TestCase):
    def setUp(self):
        h.reset()

    def test_ban_tin_sang_chi_gui_mot_lan(self):
        sent = []
        real = (jobs.build_message, jobs.tg.send)
        self.addCleanup(lambda: (setattr(jobs, "build_message", real[0]), setattr(jobs.tg, "send", real[1])))
        jobs.build_message = lambda: "BANTIN"
        jobs.tg.send = lambda chat, text, buttons=None, tok=None: sent.append(text)
        self.assertIsNone(jobs.ban_tin_sang(at(13, 6, 0), "1"))
        self.assertEqual(jobs.ban_tin_sang(at(13, 7, 0), "1"), "đã gửi")
        self.assertIsNone(jobs.ban_tin_sang(at(13, 7, 15), "1"))  # đã đánh dấu
        self.assertEqual(sent, ["BANTIN"])
        self.assertEqual(jobs.ban_tin_sang(at(14, 7, 0), "1"), "đã gửi")  # ngày mới gửi lại


if __name__ == "__main__":
    unittest.main()
