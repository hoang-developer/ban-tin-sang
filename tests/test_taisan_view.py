"""Màn hình tài sản (presentation thuần) và khám sức khỏe tài chính (service qua harness)."""
import unittest
from datetime import date

from tests import harness as h

from interface.taisan import assets as ts
from presentation.taisan import view
from services.taisan import health


def val(**kw):
    rows = [("tien", "1", "VCB", 25_000_000, None, "chính, ước tính"), ("cp", "3", "FPT", 105_000_000, 95_000_000, "1.000 cp × 105.000đ"),
            ("tietkiem", "2", "BIDV", 50_400_000, 50_000_000, "50tr · 5,5%/năm"), ("no", "4", "Thẻ", 20_000_000, None, "")]
    v = {"rows": rows, "assets": 180_400_000, "debts": 20_000_000, "net": 160_400_000, "notes": [], "lailo": []}
    v.update(kw)
    return v


class ManHinh(unittest.TestCase):
    def test_tong_quan(self):
        text, buttons = view.overview_view(val(lailo=[{"ngay": "2026-05-01", "lai": 1_000_000}]), date(2026, 10, 20), " (↑5,0% so với 20/09)", [])
        self.assertIn("💼 <b>Tài sản ròng: 160.400.000đ</b> (↑5,0% so với 20/09)", text)
        self.assertIn("Tài sản 180,4tr · nợ 20tr", text)
        self.assertIn("📈 Cổ phiếu: <b>105tr</b> (58%) · 🟢 lãi 10tr (+10,5%)", text)
        self.assertIn("🐷 Tiết kiệm: <b>50,4tr</b> (28%) · lãi tới nay 400k", text)
        self.assertIn("• FPT: 105tr · 1.000 cp × 105.000đ 🟢+11%", text)
        self.assertIn("💰 Lãi/lỗ đã chốt năm 2026: <b>+1.000.000đ</b> (1 lần bán)", text)
        self.assertEqual(buttons, view.BUTTONS)
        self.assertEqual(view.overview_view(val(rows=[]), date(2026, 10, 20), "", []), view.USAGE)
        warned, _ = view.overview_view(val(notes=["Cổ phiếu: nguồn giá lỗi"]), date(2026, 10, 20), "", [])
        self.assertIn("<i>⚠️ Cổ phiếu: nguồn giá lỗi</i>", warned)

    def test_lai_lo_va_danh_sach_sua(self):
        self.assertEqual(view.gain_text(190_000, 2_000_000), "🟢 +190k (+10%)")
        self.assertEqual(view.gain_text(-146_000, 1_500_000), "🔴 −146k (−10%)")
        self.assertEqual(view.gain_text(5_000, 0), "🟢 +5k")
        text, rows = view.edit_list_view(val())
        self.assertIn("1. 🏦 VCB: 25tr", text)
        self.assertEqual(rows[0][0], ("❌ 1", "ts:x:1"))
        self.assertEqual(rows[-1], [("↩️ Xong", "ts:xem")])
        self.assertEqual(view.edit_list_view(val(rows=[])), view.USAGE)

    def test_bieu_do(self):
        pie = view.pie_chart(val())
        self.assertEqual(pie["type"], "doughnut")
        self.assertEqual(pie["data"]["datasets"][0]["data"], [105_000_000, 50_400_000, 25_000_000])  # xếp giảm dần, bỏ nợ
        self.assertIn("Tài sản ròng 160.400.000đ", pie["options"]["plugins"]["title"]["text"])
        self.assertIsNone(view.pie_chart(val(rows=[("no", "4", "Thẻ", 20_000_000, None, "")])))
        line = view.line_chart([("2026-10-20", {"rong": 100_000_000}), ("2026-11-20", {"rong": 120_500_000})])
        self.assertEqual((line["data"]["labels"], line["data"]["datasets"][0]["data"]), (["20/10", "20/11"], [100.0, 120.5]))
        self.assertEqual(view.chart_caption(val()), "💼 <b>Tài sản ròng</b>: 160.400.000đ")

    def test_tai_khoan_chinh(self):
        it = {"id": 1, "ten": "VCB", "tien": 25_000_000, "moc_ngay": "2026-10-20",
              "chuyen": [{"ngay": "2026-10-21", "tien": -3_000_000, "ghi": "mua quỹ"}, {"ngay": "2026-10-22", "tien": 500_000, "ghi": "rút"}]}
        self.assertEqual(view.main_line_text(it, 12_300_000), "🏦 VCB còn ~<b>12,3tr</b>")
        text, rows = view.main_view(it, 20_000_000, 155_000, 42_345_000)
        self.assertIn("🏦 <b>VCB ~42.345.000đ</b> (tài khoản chính)", text)
        self.assertIn("📌 Chốt 20/10: 25.000.000đ", text)
        self.assertIn("🔁 Chuyển đi −3tr · về +500k", text)
        self.assertIn("22/10 +500k rút", text)
        self.assertEqual(rows[1][0], ("🔁 Đổi tài khoản chính", "ts:chon"))
        text, rows = view.choose_main_view([])
        self.assertIn("Chưa có tài khoản", text)
        text, rows = view.choose_main_view([({"id": 1, "ten": "VCB", "chinh": True}, 42_000_000), ({"id": 2, "ten": "MoMo"}, 2_000_000)])
        self.assertEqual([r[0] for r in rows[:2]], [("✅ VCB (42tr)", "ts:chinh:1"), ("MoMo (2tr)", "ts:chinh:2")])

    def test_bang_vang(self):
        from domain.vang.gold import GoldLot
        gold = [GoldLot("sjc", 0.1, 130.0, "2026-09-01"), GoldLot("nhan", 0.05, None, None)]
        rows = [("vang", "v0", "Miếng SJC", 14_000_000, 13_000_000, ""), ("vang", "v1", "Nhẫn", 6_800_000, None, "")]
        out = view.gold_lines(rows, gold)
        self.assertEqual(len(out), 2)
        self.assertIn("Miếng SJC", out[0])
        self.assertIn("01/09", out[0])
        self.assertIn("🟢", out[0])
        self.assertIn("?", out[1])  # lần mua không ghi giá


class KhamSucKhoe(unittest.TestCase):
    def setUp(self):
        h.reset()
        h.at(2026, 10, 1, 10)
        for line in ("tien VCB 60tr", "tietkiem BIDV 40tr 5% 6 thang", "cp FPT 1000 95", "coin btc 0,01"):
            ts.taisan(line.split())
        for i in range(25):
            h.at(2026, 10, 1 + i, 10)
            h.say("ăn trưa 200k")
        h.say("lương 20tr")
        h.at(2026, 10, 27, 10)

    def test_cac_muc_cham(self):
        checks, v, (spend, income, days) = health.health_checks(date(2026, 10, 27), lambda day, val_, inc: (10, "⚠️", "Nợ: thử"))
        self.assertEqual(len(checks), 5)
        self.assertTrue(checks[0][2].startswith("Quỹ dự phòng"))
        self.assertTrue(checks[1][2].startswith("Để dành"))
        self.assertEqual(checks[2], (10, "⚠️", "Nợ: thử"))  # chấm nợ do nơi gọi đưa vào
        self.assertTrue(checks[3][2].startswith("Phân bổ"))
        self.assertTrue(checks[4][2].startswith(("Lỗ ≥ 20%", "Không khoản nào lỗ")))
        self.assertGreater(v["assets"], 0)
        self.assertGreaterEqual(days, 20)

    def test_chua_co_du_lieu(self):
        h.reset()
        h.at(2026, 10, 27, 10)
        checks, v, flows = health.health_checks(date(2026, 10, 27), lambda *a: (None, "❔", "Nợ"))
        self.assertTrue(all(c[0] is None for c in checks))
        self.assertIn("Chưa đủ dữ liệu để khám", ts.health(date(2026, 10, 27)))

    def test_tin_kham_day_du(self):
        text = ts.health(date(2026, 10, 27))
        self.assertIn("🩺 <b>Sức khỏe tài chính", text)
        self.assertIn("Tài sản ròng", text)
        self.assertNotIn("Việc nên làm", text)  # AI giả đang bận: không có lời khuyên


if __name__ == "__main__":
    unittest.main()
