"""Bản tin sáng: gợi ý thời tiết (tính thuần), lấy số liệu có dự phòng, chữ hiển thị, ghép bản tin."""
import io
import unittest
from contextlib import redirect_stderr
from datetime import date, datetime, timedelta
from unittest import mock

from domain.bantin import weather as rules
from infrastructure import clock
from interface.bantin import bulletin
from presentation.bantin import view
from services.bantin import data


def hours(feel=24, prob=0, rain=0, humid=50, uv=3, aqi=40, day=date(2026, 11, 15)):
    return [{"time": datetime(day.year, day.month, day.day, h), "feel": feel, "rain_prob": prob, "rain": rain,
             "humid": humid, "uv": uv, "aqi": aqi} for h in range(24)]


class GoiY(unittest.TestCase):
    def test_mo_ta_va_muc_khong_khi(self):
        self.assertEqual(rules.describe(61), ("🌧️", "Mưa nhỏ"))
        self.assertEqual(rules.describe(7), ("🌡️", "Không rõ"))
        self.assertEqual(rules.aqi_level(50), ("🟢", "Tốt"))
        self.assertEqual(rules.aqi_level(135), ("🟠", "Kém"))
        self.assertEqual(rules.aqi_level(999), ("🟤", "Nguy hại"))

    def test_troi_dep_ca_ngay(self):
        lines = rules.tips(hours(), date(2026, 11, 15), datetime(2026, 11, 15, 6))
        self.assertEqual(lines[0], "👕 Sáng 24°C: áo dài tay mỏng")
        self.assertEqual(lines[1], "🧺 Phơi đồ: khô ráo cả ngày, phơi thoải mái")
        self.assertEqual(lines[2], "🏃 Chạy bộ: hợp nhất lúc 7h (24°C, AQI 40)")

    def test_mua_khong_khi_xau_va_het_gio(self):
        wet = rules.tips(hours(prob=80), date(2026, 11, 15), datetime(2026, 11, 15, 6))
        self.assertIn("mang áo mưa", wet[0])
        self.assertEqual(wet[1], "🧺 Phơi đồ: mưa cả ngày, nên phơi trong nhà")
        self.assertEqual(wet[2], "🏃 Chạy bộ: giờ chạy đều có mưa, nên tập trong nhà")
        smog = rules.tips(hours(aqi=180), date(2026, 11, 15), datetime(2026, 11, 15, 6))
        self.assertEqual(smog[2], "🏃 Chạy bộ: không khí xấu (AQI thấp nhất 180), nên tập trong nhà")
        hot = rules.tips(hours(feel=34), date(2026, 11, 15), datetime(2026, 11, 15, 6))
        self.assertEqual(hot[2], "🏃 Chạy bộ: trời nóng, nên tập trong nhà cho mát")
        late = rules.tips(hours(), date(2026, 11, 15), datetime(2026, 11, 15, 21))
        self.assertEqual(len(late), 1)  # quá giờ phơi đồ và chạy bộ
        self.assertEqual(rules.tips(hours(), date(2026, 11, 20), datetime(2026, 11, 15, 6)), [])  # không có dữ liệu ngày đó

    def test_nhan_xet_nang_gat_va_chenh_lech(self):
        hs = hours(uv=10)
        for h in hs:
            if h["time"].hour in (12, 13):
                h["feel"] = 33
            elif h["time"].hour == 7:
                h["feel"] = 20
        first = rules.tips(hs, date(2026, 11, 15), datetime(2026, 11, 15, 6))[0]
        self.assertEqual(first, "👕 Sáng 20°C: áo khoác mỏng; trưa lên 33°C nên mặc nhiều lớp dễ cởi; nắng gắt (UV 10), che chắn kỹ")


class LayDuLieu(unittest.TestCase):
    def setUp(self):
        self.err = io.StringIO()
        ctx = redirect_stderr(self.err)
        ctx.__enter__()
        self.addCleanup(ctx.__exit__, None, None, None)

    def test_vang_sjc_va_du_phong_pnj(self):
        sjc = {"latestDate": "09:30", "data": [
            {"TypeName": "Vàng SJC 1L, 10L", "BuyValue": 152_300_000, "SellValue": 154_800_000},
            {"TypeName": "Vàng nhẫn SJC 99,99", "BuyValue": 150_100_000, "SellValue": 152_600_000}]}
        with mock.patch("infrastructure.marketdata.sjc_gold", return_value=sjc):
            p = data.gold_prices()
        self.assertEqual((p["sjc"], p["nhan"], p["nguon"]), ((152.3, 154.8), (150.1, 152.6), "SJC Hà Nội, cập nhật 09:30"))
        pnj = {"SJC": {"giamua": 15230, "giaban": 15480}, "N24K": {"giamua": 15010, "giaban": 15260}}
        with mock.patch("infrastructure.marketdata.sjc_gold", side_effect=RuntimeError("down")), \
                mock.patch("infrastructure.marketdata.pnj_gold", return_value=pnj):
            p = data.gold_prices()
        self.assertEqual((p["sjc"], p["nhan_ten"], p["nguon"]), ((152.3, 154.8), "Nhẫn trơn 9999", "nguồn PNJ"))
        self.assertIn("chuyển sang PNJ", self.err.getvalue())

    def test_chi_so_loi_thi_bao_khong_lay_duoc(self):
        def history(vnd, ssi, days=15):
            if vnd == "HNX":
                raise RuntimeError("hết dữ liệu")
            return [1763078400, 1763164800], [1200.0, 1212.0]

        with mock.patch.object(data, "index_history", history):
            rows = data.index_rows()
        self.assertEqual(rows[0], ("VN-Index", 1212.0, 12.0, 1.0, "15/11"))
        self.assertEqual(rows[2], ("HNX", None, None, None, None))
        self.assertIn("chỉ số HNX", self.err.getvalue())

    def test_tin_nong_va_nguon_loi(self):
        import xml.etree.ElementTree as ET
        item = ET.fromstring("<item><title> Tin &amp; A </title><link> http://x/1?a=1&amp;b=2 </link></item>")

        def feed(url, count):
            if "dantri" in url:
                raise RuntimeError("down")
            return [item]

        with mock.patch("infrastructure.marketdata.feed_items", feed):
            feeds = data.news_feeds()
        self.assertEqual(feeds, [("VnExpress", [("Tin & A", "http://x/1?a=1&b=2")]), ("Dân trí", None)])

    def test_khong_khi_chi_lay_cho_hom_nay(self):
        daily = {"daily": {}, "current": {}}
        with mock.patch("infrastructure.openmeteo.daily", return_value=daily), \
                mock.patch("infrastructure.openmeteo.air_now", side_effect=RuntimeError("down")) as air:
            self.assertEqual(data.weather_data(day=1), (daily, None))
            air.assert_not_called()
            self.assertEqual(data.weather_data(day=0), (daily, None))  # lỗi không khí thì bỏ qua
            air.assert_called_once()
        self.assertIn("không khí", self.err.getvalue())


class ManHinh(unittest.TestCase):
    def test_thoi_tiet_va_khong_khi(self):
        w = {"current": {"temperature_2m": 21.4}, "daily": {
            "weather_code": [61, 3], "temperature_2m_max": [27.5, 25.1], "temperature_2m_min": [19.2, 18.0],
            "precipitation_probability_max": [70, 20]}}
        self.assertEqual(view.weather_lines(w, 0), ["🌧️ Mưa nhỏ, 19–28°C (bây giờ 21°C)", "☔ Khả năng mưa: 70% – nhớ mang ô!"])
        self.assertEqual(view.weather_lines(w, 1), ["☁️ Nhiều mây, 18–25°C", "☔ Khả năng mưa: 20%"])
        self.assertEqual(view.air_lines({"us_aqi": 135.4, "pm2_5": 48.2}),
                         ["🟠 Không khí: AQI 135 – Kém (PM2.5: 48 µg/m³)", "😷 Nên đeo khẩu trang khi ra ngoài"])
        self.assertEqual(len(view.air_lines({"us_aqi": 40, "pm2_5": 9})), 1)

    def test_vang_chung_khoan_tin(self):
        p = {"sjc": (152.3, 154.8), "nhan": (150.1, 152.6), "nhan_ten": "Nhẫn SJC 9999", "nguon": "nguồn X"}
        self.assertEqual(view.gold_lines(p)[0], "Miếng SJC: mua <b>152,3</b> – bán <b>154,8</b>")
        lines = view.stock_lines([("VN-Index", 1231.5, 3.5, 0.29, "15/11"), ("HNX", 1200.0, -2.0, -0.17, "15/11"),
                                  ("VN30", 1300.0, 0.0, 0.0, "15/11"), ("UPCoM", None, None, None, None)])
        self.assertEqual(lines[0], "<i>Phiên 15/11</i>")
        self.assertTrue(lines[1].startswith("🟢 VN-Index: <b>1.231,50</b>"))
        self.assertTrue(lines[2].startswith("🔴 HNX"))
        self.assertTrue(lines[3].startswith("🟡 VN30"))
        self.assertEqual(lines[4], "⚪ UPCoM: <i>không lấy được</i>")
        self.assertEqual(view.stock_lines([("A", None, None, None, None)]), ["⚪ A: <i>không lấy được</i>"])
        news = view.news_lines([("Báo", [("A <b>", "http://x/?a=1&b=2")]), ("Lỗi", None)])
        self.assertEqual(news, ["<u>Báo</u>", '• <a href="http://x/?a=1&amp;b=2">A &lt;b&gt;</a>', "<i>Lỗi: không lấy được tin</i>"])

    def test_muc_loi_va_am_lich(self):
        self.assertEqual(view.section("T", lambda: ["a", "b"]), "<b>T</b>\na\nb")
        with redirect_stderr(io.StringIO()):
            self.assertEqual(view.section("T", lambda: 1 / 0), "<b>T</b>\n<i>Không lấy được dữ liệu</i>")
        self.assertIn("hôm nay mùng 1", view.lunar_line(date(2026, 11, 9)))
        self.assertIn("mai là rằm", view.lunar_line(date(2026, 11, 22)))
        self.assertIn("Chủ Nhật, 15/11/2026", view.header(datetime(2026, 11, 15, 6, tzinfo=clock.VN_TZ)))


class GhepBanTin(unittest.TestCase):
    def test_moi_muc_loi_van_gui_cac_muc_khac(self):
        now = datetime(2026, 11, 15, 6, tzinfo=clock.VN_TZ)
        with mock.patch.object(clock, "now_vn", lambda: now), \
                mock.patch.object(data, "weather_data", side_effect=RuntimeError("x")), \
                mock.patch.object(data, "today_tips", return_value=["gợi ý"]), \
                mock.patch.object(data, "gold_prices", side_effect=RuntimeError("x")), \
                mock.patch.object(data, "index_rows", return_value=[("VN-Index", 1.0, 1.0, 1.0, "15/11")]), \
                mock.patch.object(data, "news_feeds", return_value=[]), \
                redirect_stderr(io.StringIO()):
            text = bulletin.build_message()
        self.assertIn("☀️ <b>Bản tin sáng – Chủ Nhật, 15/11/2026</b>", text)
        self.assertEqual(text.count("Không lấy được dữ liệu"), 2)  # thời tiết và vàng
        self.assertIn("<b>💡 Gợi ý hôm nay</b>\ngợi ý", text)
        self.assertIn("🟢 VN-Index", text)

    def test_nut_duoi_ban_tin(self):
        self.assertEqual([b[1] for row in bulletin.BUTTONS for b in row], ["bantin", "vn30", "mua"])


if __name__ == "__main__":
    unittest.main()
