"""AssetRepo, SalaryRepo, FundRepo: ghi đúng JSON cũ, đọc kho trống ra giá trị mặc định."""
import json
import unittest

from tests import harness as h

import kho
from domain.salary import Salary
from repositories import assets, fund, keys, salary


class AssetRepo(unittest.TestCase):
    def setUp(self):
        h.reset()

    def test_kho_trong_co_san_danh_sach_items(self):
        self.assertEqual(assets.load(), {"items": []})

    def test_luu_va_doc_giu_nguyen_ca_cuc(self):
        data = {"items": [{"id": 1, "loai": "tien", "ten": "VCB", "tien": 5}], "dem": 1, "lailo": [{"ma": "SSI"}]}
        assets.save(data)
        self.assertEqual(kho.get(keys.ASSETS), data)
        self.assertEqual(assets.load(), data)

    def test_lich_su_theo_ngay_va_json_cu(self):
        assets.save_snapshot("2026-11-14", {"rong": 100, "loai": {"tien": 100}})
        assets.save_snapshot("2026-11-13", {"rong": 90, "loai": {"tien": 90}})
        self.assertEqual([d for d, _ in assets.history()], ["2026-11-13", "2026-11-14"])
        self.assertEqual(assets.history()[1][1]["rong"], 100)
        self.assertEqual(json.loads(kho.command("HGET", keys.ASSET_HISTORY, "2026-11-14")),
                         {"rong": 100, "loai": {"tien": 100}})

    def test_gia_da_luu(self):
        self.assertEqual(assets.price_cache("cp"), ({}, None))
        assets.save_price_cache("cp", {"SSI": 20000}, "2026-11-15T10:00")
        self.assertEqual(kho.get("chitieu:gia:cp"), {"gia": {"SSI": 20000}, "luc": "2026-11-15T10:00"})
        self.assertEqual(assets.price_cache("cp"), ({"SSI": 20000}, "2026-11-15T10:00"))


class SalaryRepo(unittest.TestCase):
    def setUp(self):
        h.reset()

    def test_chua_dat_la_none(self):
        self.assertIsNone(salary.load())

    def test_dat_doc_xoa(self):
        salary.save(Salary(5, 19_000_000))
        self.assertEqual(kho.get("chitieu:luong"), {"ngay": 5, "tien": 19_000_000})
        self.assertEqual(salary.load(), Salary(5, 19_000_000))
        salary.clear()
        self.assertIsNone(salary.load())


class FundRepo(unittest.TestCase):
    def setUp(self):
        h.reset()

    def test_mac_dinh_va_luu(self):
        self.assertEqual(fund.load(), {})
        fund.save({"ma": "VMEEF", "lenh": []})
        self.assertEqual(kho.get("chitieu:dautu"), {"ma": "VMEEF", "lenh": []})
        self.assertEqual(fund.load()["ma"], "VMEEF")


if __name__ == "__main__":
    unittest.main()
