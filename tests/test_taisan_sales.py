"""Bán, rút, thu về: vàng, sổ tiết kiệm, quỹ, khoản cho vay, xóa mục; tiền về tài khoản chính, lãi ghi vào Thu nhập."""
import unittest
from datetime import date

from tests import harness as h

from domain.chitieu.kinds import INCOME
from domain.taisan import rules
from domain.taisan.text import gain_line
from domain.vang.gold import GoldLot
from repositories.chitieu import ledger as ledger_repo
from repositories.taisan import assets as assets_repo
from repositories.vang import gold as gold_repo
from services.taisan import accounts, sales


def entries():
    return ledger_repo.between(date(2026, 10, 1), date(2026, 12, 31))


class Chung(unittest.TestCase):
    def test_tim_muc_theo_ten(self):
        data = {"items": [{"loai": "cp", "ma": "FPT"}, {"loai": "quy", "ma": "VMEEF"}, {"loai": "tien", "ten": "VCB"}]}
        self.assertEqual(rules.find_item(data, "fpt", ("cp", "quy"))["ma"], "FPT")
        self.assertEqual(rules.find_item(data, "vm", ("cp", "quy"))["ma"], "VMEEF")  # tên chứa nhau
        self.assertIsNone(rules.find_item(data, "zz", ("cp", "quy")))
        self.assertIsNone(rules.find_item(data, "", ("cp", "quy")))  # nhiều mục: không đoán
        self.assertEqual(rules.find_item(data, "", ("tien",))["ten"], "VCB")  # chỉ một mục: lấy luôn
        self.assertEqual(rules.removable(data, "vcb")["ten"], "VCB")
        self.assertIsNone(rules.removable({"items": [{"loai": "no", "ten": "Thẻ"}]}, "thẻ"))  # nợ xóa ở sổ nợ

    def test_dong_lai_lo(self):
        self.assertEqual(gain_line(1_000_000, 5_000_000), "🟢 lãi 1.000.000đ (+20,0%)")
        self.assertEqual(gain_line(-200_000, 1_000_000), "🔴 lỗ 200.000đ (−20,0%)")
        self.assertEqual(gain_line(50_000, 0), "🟢 lãi 50.000đ")


class Ban(unittest.TestCase):
    def setUp(self):
        h.reset()
        h.at(2026, 10, 20, 10)
        for line in ("/taisan tien VCB 25tr", "/taisan tietkiem BIDV 50tr 5,5% 6 thang", "/taisan tietkiem Sổ B 10tr 3%",
                     "/taisan quy VMEEF 66,4 15", "/taisan khac Cho Tư vay 10tr", "/taisan khac Xe 200tr"):
            h.say(line)
        gold_repo.add(GoldLot("sjc", 0.2, 130.0, "2026-09-01"))
        gold_repo.add(GoldLot("nhan", 0.1, 125.0, "2026-10-01"))
        data = assets_repo.load()
        accounts.set_main(data, next(it for it in data["items"] if it["ten"] == "VCB"))
        assets_repo.save(data)
        h.at(2026, 10, 25, 10)
        self.now = h.CLOCK["now"]

    def main_balance(self):
        return accounts.main_balance(accounts.main_account(), self.now.date())

    def test_ban_vang_lay_lo_dan_tu_lan_mua_cu(self):
        before = self.main_balance()
        text = sales.sell_gold(1, 14_000_000, self.now, "sjc")
        self.assertIn("Bán 1 chỉ vàng = <b>14.000.000đ</b> · vốn 13.000.000đ → 🟢 lãi 1.000.000đ (+7,7%)", text)
        self.assertEqual(self.main_balance(), before + 14_000_000)
        self.assertEqual(round(sum(g.taels for g in gold_repo.load() if g.kind == "sjc"), 2), 0.1)
        income = [e for e in entries() if e["nhom"] == INCOME]
        self.assertEqual([(e["tien"], e["khong_tk"]) for e in income], [(1_000_000, True)])  # lãi là thu, không cộng tk lần nữa
        self.assertEqual(assets_repo.load()["lailo"][-1]["lai"], 1_000_000)

    def test_ban_vang_loi_thi_khong_ghi_thu(self):
        sales.sell_gold(None, 20_000_000, self.now)
        self.assertEqual(gold_repo.load(), [])
        self.assertEqual([e for e in entries() if e["nhom"] == INCOME], [])
        self.assertEqual(assets_repo.load()["lailo"][-1]["lai"], 20_000_000 - 26_000_000 - 12_500_000)

    def test_ban_vang_sai(self):
        self.assertIn("Ví chỉ có 3 chỉ, không bán được 10 chỉ", sales.sell_gold(10, 5_000_000, self.now))
        sales.sell_gold(None, 1, self.now)
        self.assertIn("Ví vàng đang trống", sales.sell_gold(1, 1, self.now))

    def test_tat_toan_so(self):
        before = self.main_balance()
        text = sales.close_saving("bidv", None, self.now)
        self.assertIn("Tất toán sổ BIDV: gốc 50.000.000đ → nhận <b>50.037.671đ</b> (lãi 37.671đ)", text)
        self.assertEqual(self.main_balance(), before + 50_037_671)
        self.assertNotIn("BIDV", [it["ten"] for it in assets_repo.load()["items"] if "ten" in it])
        self.assertEqual(assets_repo.load().get("lailo", []), [])  # lãi tiết kiệm là thu nhập, không là lãi/lỗ mua bán
        self.assertIn("Không thấy sổ «zzz». Đang có: Sổ B", sales.close_saving("zzz", None, self.now))
        sales.close_saving("sổ b", 10_500_000, self.now, to_main=False)
        self.assertIn("Chưa có sổ tiết kiệm nào", sales.close_saving("x", None, self.now))

    def test_ban_quy(self):
        text = sales.sell_fund("vmeef", 500_000, None, self.now)  # tính ccq theo NAV gần nhất
        self.assertIn("Bán", text)
        self.assertIn("ccq VMEEF", text)
        item = next(it for it in assets_repo.load()["items"] if it.get("ma") == "VMEEF")
        self.assertLess(item["sl"], 66.4)
        self.assertIn("Chỉ đang có", sales.sell_fund("vmeef", 1, 9999, self.now))
        self.assertIn("Chưa có quỹ ABC", sales.sell_fund("abc", 1, None, self.now))
        sales.sell_fund("vmeef", 1_000_000, item["sl"], self.now)
        self.assertFalse([it for it in assets_repo.load()["items"] if it.get("ma") == "VMEEF"])  # bán hết thì bỏ mục

    def test_thu_no_cho_vay(self):
        before = self.main_balance()
        self.assertIn("Không thấy khoản cho «Lan» vay", sales.collect_loan("Lan", 1_000_000, self.now))
        text = sales.collect_loan("tư", 4_000_000, self.now)
        self.assertIn("đã thu 4.000.000đ · còn 6.000.000đ", text)
        self.assertEqual(self.main_balance(), before + 4_000_000)
        text = sales.collect_loan("tư", 9_000_000, self.now)
        self.assertIn("trả hết", text)
        self.assertIn("thừa 3.000.000đ", text)
        self.assertEqual(self.main_balance(), before + 10_000_000)  # chỉ cộng phần thật sự thu
        self.assertFalse([it for it in assets_repo.load()["items"] if "tư" in (it.get("ten") or "").lower()])

    def test_xoa_muc(self):
        self.assertIn("Không thấy «zzz»", sales.remove_named("zzz"))
        self.assertIn("Đây là tài khoản chính", sales.remove_named("vcb"))
        self.assertIn("Đã xóa Xe", sales.remove_named("xe"))
        self.assertFalse([it for it in assets_repo.load()["items"] if it.get("ten") == "Xe"])


if __name__ == "__main__":
    unittest.main()
