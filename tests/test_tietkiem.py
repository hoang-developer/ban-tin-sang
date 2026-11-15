"""Tiết kiệm từ khi dùng bot: luật thuần của domain, mốc thành tích, và service qua kho giả."""
import unittest
from datetime import date

from tests import harness as h

from domain.tietkiem.progress import (DEFAULT_BASE, Milestones, build_progress, collect_days, is_debt, reached_saved_marks,
                                      reached_streak_marks, streaks, week_part, with_defaults)
from presentation.tietkiem import progress as pview
from repositories.tietkiem import progress as progress_repo
from services.tietkiem import progress as service

D = date


def entry(day, tien, nhom="an", **extra):
    return {"id": 1, "ngay": day, "nhom": nhom, "tien": tien, "ghichu": "x", **extra}


class Domain(unittest.TestCase):
    def test_cau_hinh_mac_dinh_va_gia_tri_da_luu_de_len(self):
        self.assertEqual(with_defaults(None)["moc"], DEFAULT_BASE)
        cfg = with_defaults({"moc": 300_000, "nhac": False})
        self.assertEqual((cfg["moc"], cfg["nhac"], cfg["bat_dau"], cfg["khong_tieu"]), (300_000, False, "2026-11-04", []))

    def test_khoan_tra_no_khong_tinh_chi_lat_vat(self):
        self.assertTrue(is_debt(entry("2026-11-05", 5, no=True), None))
        self.assertTrue(is_debt(entry("2026-11-05", 5, nhom="tra_no"), "tra_no"))
        self.assertFalse(is_debt(entry("2026-11-05", 5), None))

    def test_gom_ngay_co_ghi_va_chi_lat_vat(self):
        cfg = with_defaults({"bat_dau": "2026-11-04", "khong_tieu": ["2026-11-06", "2026-11-01", "2026-11-20"]})
        entries = [entry("2026-11-04", 35_000), entry("2026-11-04", 65_000), entry("2026-11-05", 2_000_000),  # khoản lớn
                   entry("2026-11-05", 500_000, no=True), entry("2026-11-05", 19_000_000, nhom="thu")]  # trả nợ, thu nhập
        small, logged = collect_days(cfg, D(2026, 11, 10), entries, None, "thu")
        self.assertEqual(small, {D(2026, 11, 4): 100_000})
        # ngày 5 có chi (khoản lớn, trả nợ) nên là ngày có ghi dù không có chi lặt vặt; thu nhập không tính; khong_tieu chỉ nhận trong [bắt đầu, hôm nay]
        self.assertEqual(logged, {D(2026, 11, 4), D(2026, 11, 5), D(2026, 11, 6)})

    def test_chuoi_ngay(self):
        logged = {D(2026, 11, d) for d in (1, 2, 3, 5, 6, 7, 8)}
        self.assertEqual(streaks(logged, D(2026, 11, 8)), (4, 4))
        self.assertEqual(streaks(logged, D(2026, 11, 9)), (4, 4))  # hôm nay chưa ghi: chuỗi tính tới hôm qua, chưa đứt
        self.assertEqual(streaks(logged, D(2026, 11, 10)), (0, 4))
        self.assertEqual(streaks(set(), D(2026, 11, 10)), (0, 0))

    def test_tien_do(self):
        cfg = with_defaults({"moc": 300_000, "bat_dau": "2026-11-01"})
        small = {D(2026, 11, 1): 100_000, D(2026, 11, 2): 400_000, D(2026, 11, 3): 300_000}
        logged = {D(2026, 11, 1), D(2026, 11, 2), D(2026, 11, 3), D(2026, 11, 4)}
        p = build_progress(cfg, D(2026, 11, 4), small, logged, {"duphong": 0, "dautu": 0, "tra_no": 0})
        self.assertEqual((p.saved, p.days, p.elapsed, p.streak, p.best), (100_000, 3, 3, 4, 4))
        self.assertEqual((p.avg, p.spent_today, p.today_logged, p.movable), (800_000 / 3, 0, True, 100_000))
        self.assertEqual(p.weeks, [(D(2026, 11, 2), 350_000, 2), (D(2026, 10, 26), 100_000, 1)])  # tuần này: ngày 2, 3; tuần trước: ngày 1
        late = build_progress(with_defaults({"moc": 300_000, "bat_dau": "2026-11-01", "da_chuyen": 90_000}), D(2026, 11, 4), small, logged, {})
        self.assertEqual(late.movable, 0)  # đã chuyển 90k: phần chưa chuyển 10k, làm tròn xuống 100k = 0

    def test_hom_nay_chua_het_ngay_nen_chua_cong(self):
        cfg = with_defaults({"moc": 300_000, "bat_dau": "2026-11-04"})
        p = build_progress(cfg, D(2026, 11, 4), {D(2026, 11, 4): 50_000}, {D(2026, 11, 4)}, {})
        self.assertEqual((p.saved, p.days, p.spent_today), (0, 0, 50_000))

    def test_tuan_va_moc(self):
        small = {D(2026, 11, 9): 100_000, D(2026, 11, 10): 500_000}
        self.assertEqual(week_part(300_000, small, {D(2026, 11, 8), D(2026, 11, 9), D(2026, 11, 10)}, D(2026, 11, 9), D(2026, 11, 10)),
                         (2, (300_000 - 100_000) + (300_000 - 500_000)))  # ngày 9 bớt 200k, ngày 10 chi hơn 200k; ngày 8 ngoài tuần
        week = {D(2026, 11, d) for d in range(1, 8)}  # chuỗi 7 ngày liên tiếp tới 07/11, hôm nay 07/11
        p = build_progress(with_defaults({"moc": 100, "bat_dau": "2026-01-01"}), D(2026, 11, 7), {}, week, {})
        self.assertEqual((p.streak, reached_streak_marks(p)), (7, [7]))


class Service(unittest.TestCase):
    def setUp(self):
        h.reset()
        h.at(2026, 11, 10, 10)

    def test_moc_chi_bao_mot_lan(self):
        import sochitieu as ct
        for d in range(4, 11):  # 7 ngày liên tiếp có ghi (ghi thẳng vào sổ, không qua tin trả lời vì tin trả lời đã báo mốc)
            h.at(2026, 11, d, 9)
            ct.add("cà phê 35k", h.CLOCK["now"])
        p = service.summary(D(2026, 11, 10))
        first = service.claim_milestones(p)
        self.assertEqual(first.streak, [7])
        self.assertEqual(service.claim_milestones(p), Milestones())  # báo rồi: không báo lại

    def test_dau_ngay_khong_tieu(self):
        self.assertEqual(service.mark_no_spend("2026-11-01", D(2026, 11, 10)).status, "ngoai_pham_vi")  # trước ngày bắt đầu
        self.assertEqual(service.mark_no_spend("2026-11-07", D(2026, 11, 10)).status, "ngoai_pham_vi")  # quá hôm qua
        h.say("cà phê 35k")
        self.assertEqual(service.mark_no_spend("2026-11-10", D(2026, 11, 10)).status, "da_co_chi")
        ok = service.mark_no_spend("2026-11-09", D(2026, 11, 10))
        self.assertEqual((ok.status, ok.when, ok.progress.streak), ("ok", "hôm qua", 2))
        self.assertEqual(progress_repo.load()["khong_tieu"], ["2026-11-09"])
        service.mark_no_spend("2026-11-09", D(2026, 11, 10))
        self.assertEqual(progress_repo.load()["khong_tieu"], ["2026-11-09"])  # bấm lại không ghi trùng

    def test_nhac_21h(self):
        self.assertIsNotNone(service.reminder(D(2026, 11, 10)))  # chưa ghi gì
        h.say("cà phê 35k")
        self.assertIsNone(service.reminder(D(2026, 11, 10)))  # đã ghi
        service.set_reminder(False)
        self.assertIsNone(service.reminder(D(2026, 11, 11)))  # tắt nhắc
        self.assertFalse(service.reminder_on())
        self.assertTrue(service.toggle_reminder())

    def test_chuyen_phan_da_bot_vao_quy_du_phong(self):
        change = service.move_to_reserve(1_000_000, D(2026, 11, 10))
        self.assertEqual(change.after.balance, 1_000_000)
        self.assertEqual(progress_repo.load()["da_chuyen"], 1_000_000)


class Presentation(unittest.TestCase):
    def test_dong_mung_moc_da_bot(self):
        p = build_progress(with_defaults({"moc": 300_000, "bat_dau": "2026-11-01"}), D(2026, 11, 20), {}, set(), {})
        lines = pview.milestone_lines(Milestones(streak=[7], saved=[1_000_000]), p)
        self.assertEqual(lines[0], "🎉 Ghi chép 7 ngày liên tiếp! Kỷ lục: 0 ngày")
        self.assertEqual(lines[1], "🎉 Từ 01/11 đã chi lặt vặt ít hơn trước 1tr! Chuyển vào quỹ để thành tiền để dành thật: /tietkiem")
        four_days = build_progress(with_defaults({"moc": 1_000_000, "bat_dau": "2026-11-01"}), D(2026, 11, 5),
                                   {}, {D(2026, 11, d) for d in (1, 2, 3, 4)}, {})  # bớt đủ mốc, không chi gì: 4tr
        self.assertEqual(reached_saved_marks(four_days), [1_000_000])

    def test_ghi_chu_so_tien(self):
        self.assertEqual(pview.saved_text(289_000), "đã bớt ~289k")
        self.assertEqual(pview.saved_text(-50_000), "đang chi hơn mốc 50k")
        self.assertEqual(pview.money(999), "0đ")


if __name__ == "__main__":
    unittest.main()
