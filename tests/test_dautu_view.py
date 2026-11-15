"""Màn hình /dautu: chữ và nút dựng từ số liệu có sẵn (presentation thuần, không kho, không mạng)."""
import unittest
from datetime import date, datetime

from domain.common.dates import VN_TZ
from presentation.dautu import view

CFG = {"ma": "VMEEF", "bat_dau": "2026-09", "gop": {"2026-09": 4_000_000}}


def state(**kw):
    s = {"ym": "2026-10", "plan": 8_000_000, "value": 6_000_000, "units": 300.0, "nav": 15_000.0, "nav_day": date(2026, 10, 2),
         "pending": 0, "cash": 4_000_000, "unpaid": 0, "available": 4_000_000, "need": 2_000_000, "buy": 2_000_000,
         "skip": False, "direct": 2_000_000, "switch": 0, "switch_units": 0, "side_buy": 0, "side": None, "side_value": None,
         "side_nav": None, "side_day": None, "money_now": 4_000_000, "short": False, "ordered": 0, "invested": 5_000_000,
         "cost": 5_000_000, "contributed": 5_000_000, "drawdown": -0.05, "month_change": 0.012, "fund": None,
         "below_milestone": False}
    s.update(kw)
    return s


SESS = {"dong": datetime(2026, 10, 30, 14, 40, tzinfo=VN_TZ), "phien": date(2026, 11, 2), "du_phong": False}


class Chu(unittest.TestCase):
    def test_phan_tram_va_lai_lo(self):
        self.assertEqual((view.pct(0.0123), view.pct(-0.05), view.pct(0.0001)), ("+1,2%", "-5,0%", "0,0%"))
        self.assertEqual((view.arrow(0.012), view.arrow(-0.008), view.arrow(0)), ("🔺1,2%", "🔻0,8%", "0,0%"))
        self.assertEqual(view.gain_text(500, 1_000_000), "⚪ hòa vốn")
        self.assertEqual(view.gain_text(22_000, 3_000_000), "🟢 +22k (+0,7%)")
        self.assertEqual(view.gain_text(-22_000, 3_000_000), "🔴 −22k (−0,7%)")
        self.assertEqual(view.gain_text(50_000, 0), "🟢 +50k")

    def test_dong_nav(self):
        line = view.nav_line(CFG, state())
        self.assertIn("NAV 15.000,00đ (02/10)", line)
        self.assertIn("tháng 🔺1,2%", line)
        self.assertIn("đỉnh 52 tuần −5,0%", line)
        self.assertEqual(view.nav_line(CFG, state(nav=None)), "Chưa lấy được NAV VMEEF")

    def test_quyet_dinh_mua(self):
        buy = view.decision_lines(CFG, state())
        self.assertIn("🎯 Kế hoạch 10/2026 <b>8tr</b> · có 6tr", buy[0])
        self.assertIn("👉 <b>Mua 2.000.000đ</b>", buy[1])
        self.assertIn("💰 Quỹ chờ 4tr", buy[-1])
        self.assertIn("thiếu 1tr, tháng sau tự bù", view.decision_lines(CFG, state(short=True, need=3_000_000))[1])
        self.assertIn("Không mua</b>: quỹ cao hơn kế hoạch 1tr", "\n".join(view.decision_lines(CFG, state(buy=0, need=-1_000_000))))
        self.assertIn("Không mua: cần 2tr nhưng quỹ chờ có 4tr", "\n".join(view.decision_lines(CFG, state(buy=0))))
        before = view.decision_lines(CFG, state(), final=False)
        self.assertIn("cuối tháng mua ~<b>2tr</b>", before[1])
        self.assertEqual(view.decision_lines(CFG, state(skip=True, buy=0))[1], "⏸ Tháng này tạm dừng")

    def test_quy_cho_la_quy_dua_ra_cac_lenh(self):
        s = state(side={"ma": "VFF", "id": 1}, direct=1_000_000, side_buy=980_000, switch=1_000_000, switch_units=70.5,
                  side_value=5_000_000)
        lines = view.order_lines(CFG, s)
        self.assertIn("Mua thêm VMEEF 2tr", lines[0])
        self.assertEqual(lines[1:], ["   1. Mua VMEEF <b>1.000.000đ</b> (tiền góp)", "   2. Mua VFF <b>980.000đ</b>",
                                      "   3. Hoán đổi <b>70,5 ccq VFF → VMEEF</b> (≈ 1tr; bán VFF rồi mua VMEEF, ~7 ngày)"])
        none = state(side={"ma": "VFF", "id": 1}, direct=0, buy=0, need=1)
        self.assertEqual(view.order_lines(CFG, none), ["👉 Tháng này không cần đặt lệnh"])

    def test_tom_tat_danh_muc(self):
        self.assertIn("💼 Đã mua 5tr → ", view.summary_line(state()))
        self.assertTrue(view.summary_line(state()).endswith("300 ccq"))
        both = view.summary_line(state(side={"ma": "VFF"}, side_value=4_000_000))
        self.assertIn("💼 14tr: cổ phiếu 6tr (43%) · VFF 4tr (57%)", both)

    def test_han_dat_lenh_va_ngay_cuoi_thang(self):
        self.assertEqual(view.last_weekday("2026-10"), date(2026, 10, 30))
        self.assertEqual(view.last_weekday("2026-08"), date(2026, 8, 31))
        self.assertEqual(view.last_weekday("2026-05"), date(2026, 5, 29))  # 31/5 là Chủ nhật
        self.assertEqual(view.deadline_text(CFG, "2026-10", SESS, date(2026, 10, 30)), "14:40 hôm nay 30/10")
        self.assertEqual(view.deadline_text(CFG, "2026-10", SESS, date(2026, 10, 2)), "14:40 30/10")
        self.assertEqual(view.deadline_text(CFG, "2026-11", SESS, date(2026, 10, 2)), "14:40 ~30/11")


class Nut(unittest.TestCase):
    def test_nut_dat_lenh_theo_trang_thai(self):
        rows = view.buttons(CFG, state(), SESS, True, lambda: None)
        self.assertTrue(rows[0][0][1].startswith("dt:dat:2000000:20261102:2026-10"))
        self.assertIn(("⏸ Tạm dừng tháng này", "dt:bo:2026-10"), [b for r in rows for b in r])
        self.assertIn(("🔄 Cập nhật", "dt:xem"), rows[-2])
        none = view.buttons(CFG, state(), SESS, False, lambda: None)
        self.assertFalse(any(b[1].startswith("dt:dat") for r in none for b in r))  # chưa tới hạn: chưa có nút đặt
        skipped = view.buttons(CFG, state(skip=True), SESS, True, lambda: None)
        self.assertFalse(any(b[1].startswith(("dt:dat", "dt:bo")) for r in skipped for b in r))

    def test_nut_dat_hai_lenh_goi_phien_quy_cho(self):
        s = state(side={"ma": "VFF", "id": 1}, direct=1_000_000, side_buy=980_000, switch=500_000, switch_units=12.3)
        asked = []
        rows = view.buttons(CFG, s, SESS, True, lambda: asked.append(1) or date(2026, 11, 3))
        self.assertEqual(rows[0][0][1], "dt:dat2:1000000:980000:1230:2026-10:20261102:20261103")
        self.assertEqual(asked, [1])
        view.buttons(CFG, state(), SESS, True, lambda: asked.append(2))
        self.assertEqual(asked, [1])  # không có quỹ chờ: không hỏi phiên

    def test_nut_sua_ccq(self):
        self.assertEqual(view.fix_button("VFF"), ("✏️ Fmarket báo số ccq VFF khác", "y:them:sua_ccq:VFF"))


class ManHinh(unittest.TestCase):
    def test_man_hinh_chinh_va_nhac(self):
        info = {"top": [{"ma": "VIC"}, {"ma": "FPT"}], "top_luc": "30/09"}
        text, rows = view.view_text(CFG, state(), True, SESS, info, date(2026, 10, 2), lambda: None)
        self.assertIn("📈 <b>VMEEF: góp 4tr/tháng</b>", text)
        self.assertIn("⏰ Hạn đặt lệnh: 14:40 30/10", text)
        self.assertIn("🔟 Top 10 (30/09): VIC, FPT\n⚠️ Có nhóm Vingroup: VIC", text)
        self.assertTrue(rows)
        text, _ = view.view_text({**CFG, "tat": True, "ke_hoach_them": {"2026-11": 1_000_000}}, state(), True, SESS, None,
                                 date(2026, 10, 2), lambda: None)
        self.assertIn("(đang tắt: /dautu bat)", text)
        self.assertIn("🔁 Đang rải vào VMEEF: còn 1tr, tới 11/2026", text)
        self.assertNotIn("🔟", text)
        remind, _ = view.reminder_view(CFG, state(), SESS, False, lambda: None, lambda: None)
        self.assertIn("hôm nay là hạn đặt lệnh tháng 10", remind)
        self.assertIn("khớp phiên 02/11", remind)
        again, _ = view.reminder_view(CFG, state(side={"ma": "VFF"}), SESS, True, lambda: date(2026, 11, 3), lambda: date(2026, 11, 3))
        self.assertIn("còn tới 14:40 để đặt lệnh tháng 10", again)
        self.assertIn(", VFF phiên 03/11", again)

    def test_lich_su_lenh(self):
        text, rows = view.history_view({"ma": "VMEEF"})
        self.assertIn("Chưa có lệnh nào", text)
        cfg = {"ma": "VMEEF", "cho": {"ma": "VFF", "id": 1}, "lenh": [
            {"dat": "2026-09-09", "phien": "2026-09-10", "trang_thai": "khop", "tien": 1_000_000, "ccq": 64.69, "nav": 15458.06},
            {"dat": "2026-09-30", "phien": "2026-10-01", "trang_thai": "cho", "tien": 980_000, "quy": "VFF"},
            {"dat": "2026-09-22", "phien": "2026-10-01", "trang_thai": "chuyen", "loai": "doi", "quy": "VFF", "ccq_ra": 100,
             "ban": "2026-09-24", "tien": 2_000_000}]}
        text, rows = view.history_view(cfg)
        self.assertIn("🧾 <b>Các lệnh VMEEF</b> và VFF", text)
        self.assertIn("• đặt 09/09 → phiên 10/09: 1tr → 64,69 ccq, NAV 15.458,06", text)
        self.assertIn("• VFF đặt 30/09 → phiên 01/10: 980k · chờ khớp", text)
        self.assertIn("hoán đổi 100 ccq VFF → VMEEF · ✅ bán 24/09 ≈ 2tr, 🔁 chờ mua", text)
        self.assertEqual(rows[0], [view.fix_button("VMEEF")])

    def test_bieu_do(self):
        chart = view.chart_config(CFG, [("2026-09", {"muc": 4_000_000, "gt": 3_900_000}),
                                        ("2026-10", {"muc": 8_040_000, "gt": 8_100_000})])
        self.assertEqual(chart["data"]["labels"], ["9/2026", "10/2026"])
        self.assertEqual(chart["data"]["datasets"][0]["data"], [4.0, 8.04])
        self.assertEqual(chart["data"]["datasets"][1]["data"], [3.9, 8.1])
        self.assertIn("VMEEF: kế hoạch và thực tế", chart["options"]["plugins"]["title"]["text"])
        self.assertEqual(view.chart_caption(CFG, state()), "📊 <b>VMEEF</b>: kế hoạch 8tr · đang có 6tr")


if __name__ == "__main__":
    unittest.main()
