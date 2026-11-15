"""AssetRepo, SalaryRepo, FundRepo: ghi đúng JSON cũ, đọc kho trống ra giá trị mặc định."""
import json
import unittest

from tests import harness as h

import kho
from domain.salary import Salary
from repositories import assets, fund, keys, ledger, salary


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


class LedgerRepo(unittest.TestCase):
    def setUp(self):
        h.reset()

    def entry(self, rid, day="2026-11-15", **extra):
        return {"id": rid, "ngay": day, "gio": "10:00", "nhom": "an", "tien": 35000, "ghichu": "cà phê", **extra}

    def test_thang_trong(self):
        self.assertEqual(ledger.load("2026-11"), [])

    def test_ghi_doc_theo_thang_xep_theo_ma(self):
        ledger.save(self.entry(3))
        ledger.save(self.entry(1))
        ledger.save(self.entry(2, day="2026-10-31"))
        self.assertEqual([e["id"] for e in ledger.load("2026-11")], [1, 3])
        self.assertEqual([e["id"] for e in ledger.load("2026-10")], [2])

    def test_json_giu_tieng_viet_va_bo_khoa_tam(self):
        ledger.save(self.entry(1, _chon=True, ai=True))
        raw = kho.command("HGET", keys.ledger_month("2026-11"), 1)
        self.assertIn("cà phê", raw)  # không escape unicode
        self.assertEqual(json.loads(raw), self.entry(1, ai=True))  # khóa "_chon" không lưu

    def test_ghi_de_cung_ma(self):
        ledger.save(self.entry(1))
        ledger.save(self.entry(1, tien=50000))
        self.assertEqual(ledger.find("2026-11", 1)["tien"], 50000)
        self.assertEqual(len(ledger.load("2026-11")), 1)

    def test_tim_va_xoa(self):
        ledger.save(self.entry(1))
        self.assertEqual(ledger.find("2026-11", "1")["id"], 1)  # mã đi qua nút bấm là chuỗi
        self.assertIsNone(ledger.find("2026-11", 9))
        ledger.remove("2026-11", 1)
        self.assertIsNone(ledger.find("2026-11", 1))
        self.assertEqual(ledger.load("2026-11"), [])

    def test_ma_khoan_tang_dan(self):
        self.assertEqual(ledger.last_id(), 0)
        self.assertEqual([ledger.next_id(), ledger.next_id()], [1, 2])
        self.assertEqual(ledger.last_id(), 2)
        self.assertEqual(kho.get("chitieu:dem"), 2)


if __name__ == "__main__":
    unittest.main()
