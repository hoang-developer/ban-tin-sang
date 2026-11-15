"""Tài sản: quy tắc thuần (lãi tiết kiệm, tài khoản chính), chữ số lượng/tiền, định giá và tài khoản chính qua service."""
import unittest
from datetime import date

from tests import harness as h

from domain.chitieu.kinds import INCOME, OTHER
from domain.taisan import rules
from domain.taisan.kinds import COINS, TYPES
from domain.taisan.text import gold_amount, gold_name, qty_text, short
from repositories.chitieu import ledger as ledger_repo
from repositories.taisan import assets as assets_repo
from services.taisan import accounts, valuation


class QuyTac(unittest.TestCase):
    def test_lai_tiet_kiem(self):
        it = {"ngay": "2026-01-15", "tien": 36_500_000, "lai": 10.0, "ky": 6}
        interest, maturity = rules.accrued(it, date(2026, 3, 16))
        self.assertEqual((round(interest), maturity), (round(36_500_000 * 0.10 * 60 / 365), date(2026, 7, 15)))
        after, _ = rules.accrued(it, date(2027, 1, 1))  # quá hạn: lãi dừng ở ngày đáo hạn
        self.assertEqual(round(after), round(36_500_000 * 0.10 * 181 / 365))
        flexible = {"ngay": "2026-01-15", "tien": 1_000_000, "lai": 3.65}
        self.assertEqual(rules.accrued(flexible, date(2026, 1, 25)), (1_000_000 * 3.65 / 100 * 10 / 365, None))
        self.assertEqual(rules.accrued(flexible, date(2025, 1, 1))[0], 0)  # trước ngày gửi

    def test_tai_khoan_chinh(self):
        self.assertTrue(rules.can_be_main({"loai": "tien", "ten": "VCB"}))
        for bad in ({"loai": "tien", "ten": "Quỹ dự phòng", "duphong": True}, {"loai": "tien", "ten": "x", "dautu": True},
                    {"loai": "tien", "ten": "TK DNSE"}, {"loai": "cp", "ten": "FPT"}):
            self.assertFalse(rules.can_be_main(bad))
        self.assertTrue(rules.same_name(" Vietcombank ", "vietcombank"))
        it = {"tien": 1_000_000, "moc": 5, "chuyen": [{"tien": -200_000}, {"tien": 50_000}]}
        entries = [{"id": 5, "nhom": INCOME, "tien": 9}, {"id": 6, "nhom": INCOME, "tien": 500_000},
                   {"id": 7, "nhom": "an", "tien": 100_000}, {"id": 8, "nhom": OTHER, "tien": 40_000},
                   {"id": 9, "nhom": "an", "tien": 30_000, "khong_tk": True}]
        income, spend = rules.main_flows(it, date(2026, 11, 1), entries)
        self.assertEqual((income, spend), (500_000, 140_000))  # khoản ≤ mốc và khoản không qua tài khoản bị bỏ
        self.assertEqual(rules.main_balance(it, income, spend), 1_000_000 + 500_000 - 140_000 - 150_000)

    def test_chu_hien_thi(self):
        self.assertEqual([qty_text(x) for x in (1000, 0.05, 1234.5, 66.4)], ["1.000", "0,05", "1.234,5", "66,4"])
        self.assertEqual([gold_amount(x) for x in (0.2, 1, 1.25, 0.01, 0)], ["2 chỉ", "1 lượng", "1 lượng 2,5 chỉ", "0,1 chỉ", "0 chỉ"])
        self.assertEqual((gold_name("sjc"), gold_name("nhan")), ("Miếng SJC", "Nhẫn"))
        self.assertEqual([short(x) for x in (-1_500_000, 35_000, 0)], ["−1,5tr", "35k", "0k"])
        self.assertEqual(COINS["btc"], "bitcoin")
        self.assertIn("quy", TYPES)


class DichVu(unittest.TestCase):
    def setUp(self):
        h.reset()
        h.at(2026, 10, 20, 10)
        for line in ("/taisan tien VCB 25tr", "/taisan tien MoMo 2tr", "/taisan tietkiem BIDV 50tr 5,5% 6 thang",
                     "/taisan no Thẻ 20tr", "/taisan cp FPT 1000 95"):
            h.say(line)

    def test_dinh_gia_nhieu_loai(self):
        v = valuation.valuation(date(2026, 10, 20))
        kinds = {r[0] for r in v["rows"]}
        self.assertEqual(kinds, {"tien", "tietkiem", "no", "cp"})
        self.assertEqual(v["debts"], 20_000_000)
        self.assertAlmostEqual(v["net"], v["assets"] - v["debts"])
        cp = next(r for r in v["rows"] if r[0] == "cp")
        self.assertEqual(cp[2], "FPT")
        self.assertIn("1.000 cp ×", cp[5])
        later = valuation.valuation(date(2027, 5, 1))  # lãi tiết kiệm cộng dồn tới ngày đáo hạn
        saving = lambda val: next(r[3] for r in val["rows"] if r[0] == "tietkiem")  # noqa: E731
        self.assertGreater(saving(later), saving(v))

    def test_luu_tai_san_rong_va_so_sanh(self):
        v = valuation.valuation(date(2026, 10, 20))
        valuation.snapshot(date(2026, 10, 20), v)
        self.assertEqual(valuation.history()[-1][0], "2026-10-20")
        self.assertEqual(assets_repo.history()[-1][1]["rong"], round(v["net"]))
        self.assertEqual(valuation.compare_line(date(2026, 10, 20), v["net"]), "")  # chưa có lần lưu trước đó
        self.assertIn("so với 20/10", valuation.compare_line(date(2026, 11, 20), v["net"] * 1.1))
        self.assertIn("↑10,0%", valuation.compare_line(date(2026, 11, 20), v["net"] * 1.1))
        self.assertIn("↓", valuation.compare_line(date(2026, 11, 20), v["net"] * 0.5))

    def test_tai_khoan_chinh(self):
        data = assets_repo.load()
        self.assertIsNone(accounts.main_account(data))
        vcb = next(it for it in data["items"] if it["ten"] == "VCB")
        accounts.set_main(data, vcb)
        assets_repo.save(data)
        self.assertEqual(accounts.main_account()["ten"], "VCB")
        h.say("cà phê 35k")
        h.say("lương 20tr")
        h.at(2026, 10, 21, 10)
        income, spend = accounts.main_flows(accounts.main_account(), date(2026, 10, 21))
        self.assertEqual((income, spend), (20_000_000, 35_000))
        self.assertEqual(accounts.main_balance(accounts.main_account(), date(2026, 10, 21)), 25_000_000 + 20_000_000 - 35_000)
        d = assets_repo.load()
        note = accounts.move_main(d, -3_000_000, "mua quỹ")
        self.assertIn("VCB −3tr → ~", note)
        self.assertIsNone(accounts.move_main(d, 0, "x"))
        assets_repo.save(d)
        self.assertEqual(accounts.main_balance(accounts.main_account(), date(2026, 10, 21)), 25_000_000 + 20_000_000 - 35_000 - 3_000_000)

    def test_doi_tai_khoan_chinh_va_tim_theo_ten(self):
        data = assets_repo.load()
        self.assertEqual(accounts.find_account(data, "vcb")["ten"], "VCB")
        self.assertIsNone(accounts.find_account(data, ""))
        self.assertIsNone(accounts.find_account(data, "không có"))
        first = accounts.pick_main(data["items"][0]["id"])
        self.assertEqual(first["ten"], "VCB")
        self.assertIsNone(accounts.pick_main(9999))
        momo = next(it["id"] for it in assets_repo.load()["items"] if it["ten"] == "MoMo")
        accounts.pick_main(momo)
        self.assertEqual(accounts.main_account()["ten"], "MoMo")
        old = next(it for it in assets_repo.load()["items"] if it["ten"] == "VCB")
        self.assertFalse(old.get("chinh"))  # tài khoản cũ thôi tự trừ

    def test_gop_lich_su_chuyen(self):
        data = assets_repo.load()
        accounts.set_main(data, data["items"][0])
        assets_repo.save(data)
        for _ in range(160):
            d = assets_repo.load()
            accounts.move_main(d, -1000, "chuyển", date(2026, 10, 20))
            assets_repo.save(d)
        main = accounts.main_account()
        self.assertLessEqual(len(main["chuyen"]), 150)  # gộp các lần cũ vào số chốt cho gọn
        self.assertEqual(accounts.main_balance(main, date(2026, 10, 20)), 25_000_000 - 160_000)

    def test_khoan_giua_hai_ngay_o_so_chi_tieu(self):
        h.say("cà phê 35k")
        h.at(2026, 10, 25, 10)
        h.say("grab 120k")
        got = ledger_repo.between(date(2026, 10, 20), date(2026, 10, 25))
        self.assertEqual(sorted(e["tien"] for e in got), [35_000, 120_000])
        self.assertEqual([e["tien"] for e in ledger_repo.between(date(2026, 10, 21), date(2026, 10, 24))], [])


if __name__ == "__main__":
    unittest.main()
