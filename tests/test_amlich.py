"""Âm lịch: đổi qua lại dương ↔ âm, can chi, ngày mùng 1 và rằm tới."""
import unittest
from datetime import date

from domain.amlich import lunar


class AmLich(unittest.TestCase):
    def test_doi_duong_sang_am(self):
        self.assertEqual(lunar.to_lunar(date(2026, 2, 17))[:3], (1, 1, 2026))  # Tết Bính Ngọ
        self.assertEqual(lunar.label(date(2026, 2, 17)), "1/1 Bính Ngọ")

    def test_doi_am_sang_duong(self):
        self.assertEqual(lunar.to_solar(1, 1, 2026), date(2026, 2, 17))
        self.assertEqual(lunar.can_chi(2026), "Bính Ngọ")

    def test_ngay_am_ke_tiep(self):
        today = date(2026, 11, 15)
        d = lunar.next_date(5, 10, True, today)
        self.assertGreaterEqual(d, today)
        self.assertEqual(lunar.to_lunar(d)[:2], (5, 10))
        self.assertEqual(lunar.next_date(20, 11, False, today), date(2026, 11, 20))

    def test_mung_mot_va_ram(self):
        moons = lunar.next_moon_days(date(2026, 11, 15))
        self.assertTrue(moons)


if __name__ == "__main__":
    unittest.main()
