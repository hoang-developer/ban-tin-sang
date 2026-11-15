"""Quy tắc Value Averaging (domain thuần) và tình trạng kỳ đang mở (service)."""
import unittest

from tests import harness as h
from tests.test_dautu import setup_plan

from domain.dautu import plan
from repositories.dautu import fund as fund_repo
from services.dautu import status as status_service


def cfg(**kw):
    base = {"ma": "VMEEF", "bat_dau": "2026-08", "gop": {"2026-08": 4_000_000}, "tang": 0.01}
    base.update(kw)
    return base


class Quytac(unittest.TestCase):
    def test_so_gop_theo_moc_va_thang_tam_dung(self):
        c = cfg(gop={"2026-08": 4_000_000, "2026-10": 5_000_000}, ky={"2026-11": {"bo": True}})
        self.assertEqual([plan.gop_of(c, m) for m in ("2026-08", "2026-09", "2026-10", "2026-11", "2026-12")],
                         [4_000_000, 4_000_000, 5_000_000, 0, 5_000_000])

    def test_goc_cong_goc_roi_nhan_tang_va_gop(self):
        c = cfg(goc=1_000_000)
        self.assertEqual(plan.target(c, "2026-08"), 5_000_000)
        self.assertAlmostEqual(plan.target(c, "2026-09"), 5_000_000 * 1.01 + 4_000_000)
        self.assertEqual(plan.target(c, "2026-07"), 0)  # trước ngày bắt đầu
        c2 = cfg(ke_hoach_them={"2026-09": 2_000_000})
        self.assertAlmostEqual(plan.target(c2, "2026-09"), 4_000_000 * 1.01 + 6_000_000)

    def test_gop_them_chi_khi_co_quy_cho_la_quy(self):
        self.assertEqual(plan.them_of(cfg(them={"2026-08": 1_000_000}), "2026-09"), 0)
        c = cfg(cho={"ma": "VFF", "id": 1}, them={"2026-08": 1_000_000})
        self.assertEqual((plan.them_of(c, "2026-09"), plan.total_of(c, "2026-09")), (1_000_000, 5_000_000))
        c["ky"] = {"2026-09": {"bo": True}}
        self.assertEqual(plan.total_of(c, "2026-09"), 0)

    def test_lenh_cho_quy_chinh(self):
        c = cfg(cho={"ma": "VFF", "id": 1})
        buy_main = {"trang_thai": "cho", "quy": "VMEEF"}
        buy_side = {"trang_thai": "cho", "quy": "VFF"}
        swap = {"trang_thai": "chuyen", "loai": "doi"}
        self.assertEqual([plan.pending_main(c, o) for o in (buy_main, buy_side, swap, {**buy_main, "trang_thai": "khop"})],
                         [True, False, True, False])
        self.assertEqual(plan.contributed_of(cfg(nap={"a": 1, "b": 2}, ngoai={"c": 4}, goc=8)), 15)

    def test_tim_co_phieu_va_ten_quy_cho(self):
        data = {"items": [{"loai": "quy", "ma": "VFF", "sl": 3}, {"loai": "quy", "ma": "VMEEF", "sl": 5}]}
        self.assertEqual(plan.holding(data, cfg())["sl"], 5)
        self.assertEqual(plan.holding(data, cfg(), "VFF")["sl"], 3)
        self.assertIsNone(plan.holding(data, cfg(), "XXX"))
        self.assertEqual(plan.wait_name(cfg()), "Quỹ chờ VMEEF")


class TinhTrang(unittest.TestCase):
    def setUp(self):
        setup_plan()

    def test_wait_item_tao_mot_lan(self):
        data = {"items": [], "next_id": 1}
        c = fund_repo.load()
        a = status_service.wait_item(data, c)
        b = status_service.wait_item(data, c)
        self.assertIs(a, b)
        self.assertEqual((a["ten"], a["tien"], a["dautu"]), (plan.wait_name(c), 0, True))
        self.assertEqual(len(data["items"]), 1)

    def test_trang_thai_ky_dang_mo(self):
        c = fund_repo.load()
        s = status_service.status(c)
        self.assertEqual(s["ym"], status_service.current_period(c))
        self.assertEqual(s["plan"], plan.target(c, s["ym"]))
        self.assertEqual(s["buy"] % plan.STEP, 0)
        self.assertTrue(s["buy"] == 0 or s["buy"] >= plan.MIN_ORDER)
        self.assertEqual(s["contributed"], plan.contributed_of(c))

    def test_chot_ky_da_qua_khong_chot_lai(self):
        c = fund_repo.load()
        h.at(2026, 12, 20, 10)
        first = status_service.close_periods(c)
        self.assertTrue(first)
        self.assertTrue(all(k.get("chot") for ym, k in c["ky"].items() if ym < status_service.current_period(c)))
        self.assertFalse(status_service.close_periods(c))


if __name__ == "__main__":
    unittest.main()
