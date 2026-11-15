"""Khai báo tài sản, mua bán cổ phiếu, nhắc lương và đáo hạn, dòng tiền trung bình."""
import unittest
from datetime import date

from tests import harness as h

from domain.taisan import rules
from domain.taisan.kinds import ALIASES, FX_CODES
from domain.taisan.trade import BROKER_FEE, SELL_TAX, parse_trade
from repositories.chitieu import ledger as ledger_repo
from repositories.luong import salary as salary_repo
from repositories.taisan import assets as assets_repo
from services.taisan import declare, flows, reminders, trade
from domain.luong.salary import Salary


class HamThuan(unittest.TestCase):
    def test_gia_va_ma(self):
        self.assertEqual([rules.stock_price(x) for x in ("95", "95k", "95500", "33,6")], [95_000, 95_000, 95_500, 33_600])
        self.assertEqual([rules.is_etf(x) for x in ("E1VFVN30", "fuevfvnd", "FPT", "VMEEF")], [True, True, False, False])
        self.assertEqual(rules.money_and_name("VCB 25tr".split()), ("VCB", 25_000_000))
        self.assertEqual(rules.money_and_name("xe máy 30tr".split()), ("xe máy", 30_000_000))
        self.assertEqual(rules.money_and_name("25tr".split()), ("Chưa đặt tên", 25_000_000))
        self.assertIsNone(rules.money_and_name(["abc"]))
        self.assertEqual((ALIASES["tk"], ALIASES["ccq"], ALIASES["vay"]), ("tien", "quy", "no"))
        self.assertIn("usd", FX_CODES)

    def test_doc_tin_mua_ban(self):
        self.assertEqual(parse_trade("bán 500 FPT giá 120"), ("ban", 500, "FPT", 120_000))
        self.assertEqual(parse_trade("mua 1.000 FPT giá 95"), ("mua", 1000, "FPT", 95_000))
        self.assertEqual(parse_trade("mua 500 E1VFVN30 giá 33,6"), ("mua", 500, "E1VFVN30", 33_600))
        for bad in ("cà phê 35k", "mua 100 fpt", "mua 100 FPT giá 96\ndòng hai", "mua 0,5 FPT giá 96", "mua 0 FPT giá 96"):
            self.assertIsNone(parse_trade(bad), bad)
        self.assertEqual((SELL_TAX, BROKER_FEE), (0.001, 0.0))


class DichVu(unittest.TestCase):
    def setUp(self):
        h.reset()
        h.at(2026, 10, 20, 10)

    def items(self):
        return assets_repo.load()["items"]

    def test_khai_bao_roi_cap_nhat(self):
        data = assets_repo.load()
        self.assertIn("Đã thêm 🏦 Tiền, tài khoản: VCB 25.000.000đ", declare.add_simple(data, "tien", ["VCB", "25tr"]))
        self.assertIn("Đã cập nhật", declare.add_simple(data, "tien", ["vcb", "30tr"]))  # cùng tên: cập nhật
        self.assertEqual([(it["ten"], it["tien"]) for it in data["items"]], [("VCB", 30_000_000)])
        self.assertIsNone(declare.add_simple(data, "tien", ["VCB"]))

    def test_so_tiet_kiem(self):
        data = assets_repo.load()
        text = declare.add_saving(data, "BIDV 50tr 5,5% 6 thang 01/08/2026".split())
        self.assertIn("Đã thêm sổ tiết kiệm BIDV 50.000.000đ, lãi 5,5%/năm, đáo hạn 01/02/2027", text)
        self.assertIn("không kỳ hạn", declare.add_saving(data, "Sổ B 10tr 3% không kỳ hạn".split()))
        self.assertIn("Đã cập nhật sổ tiết kiệm bidv 60.000.000đ, lãi 6%/năm, đáo hạn 20/10/2027",
                      declare.add_saving(data, "bidv 60tr 6% 12 thang".split()))
        self.assertIsNone(declare.add_saving(data, "X 10tr".split()))  # thiếu lãi
        self.assertIsNone(declare.add_saving(data, "X 10tr 5% 31/2".split()))  # ngày sai

    def test_co_phieu_quy_coin_ngoai_te(self):
        data = assets_repo.load()
        self.assertIn("Đã khai báo 📈 Cổ phiếu FPT: 1.000, giá vốn 95.000đ", declare.add_holding(data, "cp", ["FPT", "1000", "95"]))
        self.assertIn("🧺 ETF E1VFVN30", declare.add_holding(data, "cp", ["E1VFVN30", "200", "30"]))  # mã ETF vào ETF
        self.assertIn("Không thấy mã ZZZZ trên sàn", declare.add_holding(data, "cp", ["ZZZZ", "10", "5"]))
        self.assertIsNone(declare.add_holding(data, "cp", ["FPT", "-5", "3"]))
        self.assertIsNone(declare.add_holding(data, "quy", ["VMEEF"]))
        self.assertIn("🪙 Tiền số BTC: 0,01", declare.add_holding(data, "coin", ["btc", "0,01"]))
        self.assertIn("Đã khai báo ngoại tệ USD: 500", declare.add_fx(data, "usd", ["500"]))
        self.assertIsNone(declare.add_fx(data, "eur", ["abc"]))
        before = len([it for it in data["items"] if it.get("ma") == "FPT"])
        declare.add_holding(data, "cp", ["FPT", "2000", "90"])
        self.assertEqual((before, len([it for it in data["items"] if it.get("ma") == "FPT"])), (1, 1))  # khai báo lại: ghi đè

    def test_vang(self):
        self.assertIn("Đã thêm", declare.add_gold("sjc 1 luong 140".split()))
        self.assertIn("Đã thêm", declare.add_gold("nhan 0,1 chi 148,02 20/10".split()))
        self.assertIsNone(declare.add_gold(["sai"]))
        self.assertIsNone(declare.add_gold("sjc 5000 luong".split()))

    def test_mua_ban_co_phieu(self):
        data = assets_repo.load()
        declare.add_holding(data, "cp", ["FPT", "1000", "95"])
        assets_repo.save(data)
        now = h.CLOCK["now"]
        self.assertIn("Mua 100 FPT × 96.000đ = <b>9.600.000đ</b>", trade.trade("mua 100 FPT giá 96", now))
        fpt = next(it for it in self.items() if it["ma"] == "FPT")
        self.assertEqual(fpt["sl"], 1100)
        sold = trade.trade("bán 200 FPT giá 110", now)
        self.assertIn("Thuế 0,1% −22.000đ → về <b>21.978.000đ</b>", sold)
        self.assertIn("🟢 <b>lãi", sold)
        self.assertIn("Lãi đã ghi vào Thu nhập", sold)
        self.assertEqual(next(it for it in self.items() if it["ma"] == "FPT")["sl"], 900)
        self.assertEqual(len(assets_repo.load()["lailo"]), 1)
        self.assertIn("không bán được 5.000", trade.trade("bán 5000 FPT giá 110", now))
        self.assertIn("Chưa có ZZZ trong danh mục", trade.trade("bán 10 ZZZ giá 5", now))
        self.assertIsNone(trade.trade("mua 10 ZZZ giá 5", now))  # không phải mã chứng khoán: để ghi như khoản chi
        self.assertIsNone(trade.trade("cà phê 35k", now))
        trade.trade("bán 900 FPT giá 100", now)
        self.assertFalse([it for it in self.items() if it.get("ma") == "FPT"])  # bán hết thì bỏ mục

    def test_tien_di_ve_dnse_hay_tai_khoan_chinh(self):
        data = assets_repo.load()
        declare.add_simple(data, "tien", ["DNSE", "10tr"])
        declare.add_holding(data, "cp", ["FPT", "100", "95"])
        assets_repo.save(data)
        self.assertEqual(trade.broker_cash(assets_repo.load())["ten"], "DNSE")
        now = h.CLOCK["now"]
        self.assertIn("Tiền tài khoản DNSE: còn 9.040.000đ", trade.trade("mua 10 FPT giá 96", now))
        self.assertIn("Tiền tài khoản DNSE: 10.039.000đ", trade.trade("bán 10 FPT giá 100", now))

    def test_nhac_luong_va_dao_han(self):
        self.assertIsNone(reminders.salary_due(date(2026, 10, 20)))  # chưa đặt ngày lương
        salary_repo.save(Salary(20, 25_000_000))
        self.assertIsNone(reminders.salary_due(date(2026, 10, 19)))
        text, buttons = reminders.salary_due(date(2026, 10, 20))
        self.assertIn("Hôm nay ngày lương", text)
        self.assertEqual(buttons[0][0], ("✅ Đã nhận 25tr", "ts:luong:25000000"))
        self.assertIn("Đã qua ngày lương 20", reminders.salary_due(date(2026, 10, 23))[0])
        self.assertIsNone(reminders.salary_due(date(2026, 10, 24)))
        ledger_repo.save({"id": ledger_repo.next_id(), "ngay": "2026-10-20", "gio": "09:00", "tien": 25_000_000,
                          "ghichu": "lương tháng 10", "nhom": "thu"})
        self.assertIsNone(reminders.salary_due(date(2026, 10, 21)))  # đã ghi lương tháng này
        data = assets_repo.load()
        declare.add_saving(data, "BIDV 50tr 5,5% 3 thang 01/11/2026".split())
        assets_repo.save(data)
        self.assertEqual(reminders.maturity_notes(date(2026, 1, 1)), [])
        notes = reminders.maturity_notes(date(2027, 1, 30))
        self.assertEqual(len(notes), 1)
        self.assertIn("Sổ BIDV 50tr đáo hạn 01/02", notes[0])
        self.assertEqual(reminders.maturity_notes(date(2027, 1, 30)), [])  # mỗi sổ nhắc một lần

    def test_dong_tien_trung_binh(self):
        self.assertEqual(flows.monthly_flows(date(2026, 10, 20)), (0, 0, 0))
        h.say("ăn trưa 300k")
        h.at(2026, 10, 30, 10)
        h.say("lương 25tr")
        spend, income, days = flows.monthly_flows(date(2026, 10, 30))
        self.assertEqual(days, 11)
        self.assertAlmostEqual(spend, 300_000 / 11 * 30.4)
        self.assertAlmostEqual(income, 25_000_000 / 11 * 30.4)


if __name__ == "__main__":
    unittest.main()
