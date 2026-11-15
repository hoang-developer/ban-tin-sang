"""Ví vàng: domain thuần (bán lấy lô cũ trước) và GoldRepo (đọc/ghi đúng JSON cũ)."""
import unittest

from tests import harness as h

import kho
from domain.gold import GoldLot, holdings_chi, sell_fifo
from repositories import gold as gold_repo
from repositories import keys


def lots():
    return [GoldLot("nhan", 0.2, 123.84, "2026-11-11"), GoldLot("sjc", 0.1, 150.0, "2026-09-01"),
            GoldLot("nhan", 0.1, 148.02, "2026-10-20"), GoldLot("nhan", 0.05, None, None)]


class Domain(unittest.TestCase):
    def test_json_di_va_ve_khong_doi(self):
        for raw in ({"loai": "nhan", "luong": 0.1, "gia": 148.02, "ngay": "2026-10-20"},
                    {"loai": "sjc", "luong": 1.0, "gia": None},
                    {"loai": "nhan", "luong": 0.2, "gia": 120.0, "ghi_chu": "khóa lạ phải giữ"}):
            self.assertEqual(GoldLot.from_dict(raw).to_dict(), raw)

    def test_ban_lo_cu_truoc_va_tinh_von(self):
        sale = sell_fifo(lots(), 2.5, kind="nhan")  # 0,25 lượng nhẫn: lô không ngày, rồi 20/10, rồi lấy thêm từ 11/11
        left = {(g.kind, g.bought): round(g.taels, 6) for g in sale.lots}
        self.assertNotIn(("nhan", None), left)  # lô không ngày hết trước
        self.assertNotIn(("nhan", "2026-10-20"), left)  # rồi lô 20/10 hết
        self.assertEqual(left[("nhan", "2026-11-11")], 0.1)  # lô 11/11: 0,2 − 0,1 lượng
        self.assertEqual(left[("sjc", "2026-09-01")], 0.1)  # miếng SJC không đụng
        # vốn: lô chưa ghi giá = 0; 0,1 lượng × 148,02tr; 0,1 lượng × 123,84tr
        self.assertAlmostEqual(sale.cost, (0.1 * 148.02 + 0.1 * 123.84) * 1e6, places=0)

    def test_khong_chi_dinh_loai_thi_lo_cu_nhat_di_truoc_ke_ca_sjc(self):
        sale = sell_fifo(lots(), 2.5)  # lô không ngày 0,05 + SJC 01/09 0,1 + nhẫn 20/10 0,1 = 0,25 lượng
        self.assertEqual([(g.kind, g.bought) for g in sale.lots], [("nhan", "2026-11-11")])
        self.assertAlmostEqual(sale.cost, (0.1 * 150.0 + 0.1 * 148.02) * 1e6, places=0)

    def test_chi_ban_trong_mot_loai(self):
        sale = sell_fifo(lots(), 1, kind="sjc")
        self.assertEqual([(g.kind, round(g.taels, 6)) for g in sale.lots].count(("sjc", 0.0)), 0)
        self.assertEqual(len(sale.lots), 3)  # lô SJC hết, 3 lô nhẫn còn nguyên
        self.assertAlmostEqual(sale.cost, 0.1 * 150.0 * 1e6, places=0)

    def test_khong_sua_danh_sach_goc(self):
        original = lots()
        sell_fifo(original, 3)
        self.assertEqual([g.taels for g in original], [0.2, 0.1, 0.1, 0.05])

    def test_tong_chi(self):
        self.assertAlmostEqual(holdings_chi(lots()), 4.5)
        self.assertAlmostEqual(holdings_chi(lots(), "nhan"), 3.5)


class Repo(unittest.TestCase):
    def setUp(self):
        h.reset()

    def test_ghi_dung_json_cu(self):
        gold_repo.add(GoldLot("nhan", 0.1, 148.02, "2026-10-20"))
        gold_repo.add(GoldLot("sjc", 1.0, None))
        self.assertEqual(kho.get(keys.GOLD), [{"loai": "nhan", "luong": 0.1, "gia": 148.02, "ngay": "2026-10-20"},
                                              {"loai": "sjc", "luong": 1.0, "gia": None}])
        self.assertEqual([g.kind for g in gold_repo.load()], ["nhan", "sjc"])

    def test_xoa_theo_vi_tri_va_xoa_het(self):
        for g in lots():
            gold_repo.add(g)
        self.assertTrue(gold_repo.remove_at(1))
        self.assertEqual([g.kind for g in gold_repo.load()], ["nhan", "nhan", "nhan"])
        self.assertFalse(gold_repo.remove_at(9))
        self.assertFalse(gold_repo.remove_at(-1))
        gold_repo.clear()
        self.assertEqual(gold_repo.load(), [])
        self.assertEqual(kho.get(keys.GOLD), [])

    def test_kho_trong_la_danh_sach_rong(self):
        self.assertEqual(gold_repo.load(), [])


if __name__ == "__main__":
    unittest.main()
