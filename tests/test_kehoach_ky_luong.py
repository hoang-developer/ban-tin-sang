"""Kế hoạch theo kỳ lương (PR 0.7): kỳ chi tiêu từ ngày lương tới trước ngày lương kế, thu của kỳ không sụp vì khoản thu
nhỏ hay đối chiếu, phần dư sau chia lương mặc định để dành, ngân sách "Chi hằng ngày" tính đủ mọi khoản."""
import unittest
from datetime import date

from tests import harness as h

from domain.kehoach import plan as rules
from repositories.kehoach import settings as settings_repo
from services.kehoach import plan as service

D = date


def salary(day, amount, note="lương"):
    return {"ngay": day, "tien": amount, "ghichu": note, "nhom": "thu"}


class KyLuong(unittest.TestCase):
    def test_chua_dat_ngay_luong_la_thang_duong_lich(self):
        self.assertEqual(rules.pay_period(D(2026, 11, 10), None), (D(2026, 11, 1), D(2026, 11, 30)))

    def test_ky_tu_ngay_luong_toi_truoc_ngay_luong_ke(self):
        self.assertEqual(rules.pay_period(D(2026, 10, 28), 28), (D(2026, 10, 28), D(2026, 11, 27)))
        self.assertEqual(rules.pay_period(D(2026, 10, 31), 28), (D(2026, 10, 28), D(2026, 11, 27)))
        self.assertEqual(rules.pay_period(D(2026, 11, 1), 28), (D(2026, 10, 28), D(2026, 11, 27)))
        self.assertEqual(rules.pay_period(D(2026, 10, 27), 28), (D(2026, 9, 28), D(2026, 10, 27)))

    def test_ngay_luong_31_o_thang_ngan_va_qua_nam(self):
        self.assertEqual(rules.pay_period(D(2027, 2, 28), 31), (D(2027, 2, 28), D(2027, 3, 30)))
        self.assertEqual(rules.pay_period(D(2027, 1, 5), 10), (D(2026, 12, 10), D(2027, 1, 9)))
        self.assertEqual(rules.pay_period(D(2026, 12, 15), 10), (D(2026, 12, 10), D(2027, 1, 9)))


class ThuCuaKy(unittest.TestCase):
    START = D(2026, 10, 28)

    def test_luong_da_ghi_thang_luong_du_kien(self):
        self.assertEqual(rules.plan_income([salary("2026-10-28", 20_000_000)], self.START, 19_000_000), (20_000_000, ""))

    def test_luong_ve_som_van_tinh_cho_ky_moi(self):
        got = rules.plan_income([salary("2026-10-25", 20_000_000)], self.START, 19_000_000)
        self.assertEqual(got, (20_000_000, ""))

    def test_chua_ghi_luong_dung_luong_du_kien_cong_thu_khac(self):
        other = {"ngay": "2026-11-03", "tien": 100_000, "ghichu": "bán đồ cũ", "nhom": "thu"}
        self.assertEqual(rules.plan_income([other], self.START, 20_000_000), (20_100_000, "lương dự kiến, chưa ghi"))

    def test_khoan_thu_bot_tu_sinh_khong_tinh(self):
        gap = {"ngay": "2026-11-05", "tien": 535_000, "ghichu": "lệch đối chiếu", "nhom": "thu", "khong_tk": True}
        got = rules.plan_income([salary("2026-10-28", 20_000_000), gap], self.START, None)
        self.assertEqual(got, (20_000_000, ""))

    def test_thu_khac_truoc_ky_khong_tinh(self):
        old = {"ngay": "2026-10-26", "tien": 300_000, "ghichu": "bán đồ", "nhom": "thu"}
        self.assertEqual(rules.plan_income([old], self.START, 20_000_000), (20_000_000, "lương dự kiến, chưa ghi"))


class PhanDu(unittest.TestCase):
    def test_phan_du_mac_dinh_de_danh(self):
        got = rules.plan_spendable(20_000_000, 0, 0, 0, 0, 0, 0, 29, planned_spend=6_000_000)
        self.assertEqual(got["limit"], 6_000_000)
        self.assertEqual(got["per_day"], 200_000)
        self.assertIn(("để dành phần dư", 14_000_000), got["parts"])

    def test_cho_tieu_mot_phan_du(self):
        got = rules.plan_spendable(20_000_000, 0, 0, 0, 0, 0, 0, 29, planned_spend=6_000_000, spend_share=0.5)
        self.assertEqual(got["limit"], 13_000_000)

    def test_chua_co_muc_chi_du_kien_thi_khong_giu_lai(self):
        got = rules.plan_spendable(20_000_000, 0, 0, 0, 0, 0, 0, 29)
        self.assertEqual(got["limit"], 20_000_000)
        self.assertNotIn("để dành phần dư", [k for k, _ in got["parts"]])


class XuyenSuot(unittest.TestCase):
    """Kịch bản hội đồng BA: lương 28 hằng tháng 20tr, chi đều 200k/ngày. Trước đây "mỗi ngày được tiêu" nhảy
    2,9tr → 11,7tr → 577k → 3.571đ quanh ngày lương; giờ phải ổn định quanh mức chi thật."""

    def setUp(self):
        h.reset()
        h.at(2026, 10, 1, 10)
        h.say("/luong 28 20tr")
        for d in range(1, 29):
            h.at(2026, 10, d, 12)
            h.say("ăn uống 200k")
        h.at(2026, 10, 28, 10)
        h.say("lương 20tr")

    def per_day(self, *when):
        h.at(*when)
        return service.spendable_safe(h.CLOCK["now"].date())["per_day"]

    def test_moi_ngay_duoc_tieu_on_dinh_quanh_ngay_luong(self):
        values = [self.per_day(2026, 10, 28, 12), self.per_day(2026, 10, 31, 12), self.per_day(2026, 11, 1, 12)]
        for v in values:
            self.assertTrue(150_000 < v < 250_000, values)
        self.assertLess(max(values) - min(values), 20_000, values)

    def test_khoan_thu_nho_khong_lam_sup(self):
        before = self.per_day(2026, 11, 3, 12)
        h.say("+ bán đồ cũ 100k")
        after = self.per_day(2026, 11, 3, 12)
        self.assertGreater(after, before - 1000)
        self.assertTrue(150_000 < after < 250_000, after)

    def test_lenh_tieu_du(self):
        h.at(2026, 11, 1, 12)
        text, _ = h.say("/kehoach tieudu 30")
        self.assertIn("được tiêu 30% phần dư", text)
        self.assertEqual(settings_repo.spend_share(), 0.3)
        self.assertGreater(self.per_day(2026, 11, 1, 12), 250_000)
        text, _ = h.say("/kehoach tieudu 0")
        self.assertIn("để dành hết", text)
        self.assertEqual(settings_repo.spend_share(), 0.0)
        text, _ = h.say("/kehoach tieudu 150")
        self.assertIn("/kehoach tieudu 30", text)  # ngoài 0–100%: chỉ cách dùng


class NganSachHangNgay(unittest.TestCase):
    def test_khoan_lon_cua_nhom_hang_ngay_van_tinh(self):
        h.reset()
        h.at(2026, 11, 20, 10)
        h.say("/ngansach hangngay 3tr")
        for d in range(1, 20):
            h.at(2026, 11, d, 12)
            h.say("cà phê 30k")
        h.at(2026, 11, 20, 12)
        text, _ = h.say("đi siêu thị 700k")
        self.assertIn("Chi hằng ngày: 1,27tr/3tr", text)


if __name__ == "__main__":
    unittest.main()
