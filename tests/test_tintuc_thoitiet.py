"""Tìm tin theo từ khóa (/tin) và thời tiết theo nơi (/thoitiet)."""
import io
import unittest
import xml.etree.ElementTree as ET
from contextlib import redirect_stderr
from datetime import datetime, timedelta, timezone
from unittest import mock

from domain.thoitiet import place
from domain.tintuc import rules
from interface.thoitiet import report as thoitiet
from presentation.thoitiet import view as thoitiet_view
from presentation.tintuc import view
from services.thoitiet import place as place_service
from services.tintuc import search

UTC = timezone.utc


class Luat(unittest.TestCase):
    def test_hieu_cua_so_thoi_gian(self):
        self.assertEqual(rules.parse_query(["giá", "vàng"]), ("giá vàng", 168))
        self.assertEqual(rules.parse_query(["giá", "vàng", "24h"]), ("giá vàng", 24))
        self.assertEqual(rules.parse_query(["xăng", "3ngày"]), ("xăng", 72))
        self.assertEqual(rules.parse_query(["x", "99d"]), ("x", 720))  # tối đa 30 ngày
        self.assertEqual(rules.parse_query(["a", "0h"]), ("a", 1))
        self.assertEqual(rules.parse_query([]), ("", 168))
        self.assertEqual((rules.window_label(24), rules.window_label(36), rules.window_label(48)),
                         ("24 giờ qua", "36 giờ qua", "2 ngày qua"))
        self.assertEqual(rules.google_query("giá vàng", 24), '"giá vàng" when:24h')
        self.assertEqual(rules.google_query('"a b" c', 72), '"a b" c when:3d')

    def test_thoi_gian_truoc(self):
        now = datetime(2026, 11, 15, 10, tzinfo=UTC)
        self.assertEqual([rules.ago(now - d, now) for d in (timedelta(seconds=10), timedelta(minutes=59), timedelta(hours=5), timedelta(days=3))],
                         ["1 phút trước", "59 phút trước", "5 giờ trước", "3 ngày trước"])

    def test_loc_ket_qua_google(self):
        day = lambda d: datetime(2026, 11, d, tzinfo=UTC)
        raw = [("Vàng tăng - Báo A", "l1", "Báo A", day(1)), ("Vàng tăng - Báo B", "l2", "Báo B", day(3)),
               ("Clip vàng", "l3", "YouTube", day(2)), ("Vàng giảm", "l4", "", None), ("Vàng giảm", "l5", "Báo C", day(2))]
        got = rules.clean_google(raw)
        self.assertEqual([g[1] for g in got], ["l1", "l4"])  # bỏ youtube và tin trùng; tin không rõ giờ xếp cuối
        self.assertEqual(got[0][0], "Vàng tăng")  # bỏ tên báo cuối tiêu đề

    def test_ten_noi(self):
        self.assertEqual(place.place_of({"name": "Đà Nẵng", "admin1": "Đà Nẵng", "latitude": 1, "longitude": 2, "country_code": "VN"}),
                         ((1, 2), "Đà Nẵng"))
        self.assertEqual(place.place_of({"name": "Hội An", "admin1": "Quảng Nam", "latitude": 1, "longitude": 2, "country_code": "VN"})[1],
                         "Hội An, Quảng Nam")
        self.assertEqual(place.place_of({"name": "Paris", "admin1": "Île-de-France", "latitude": 1, "longitude": 2,
                                         "country_code": "FR", "country": "France"})[1], "Paris, Île-de-France, France")


class DichVu(unittest.TestCase):
    def test_google_loi_thi_tim_trong_rss(self):
        xml = "<c><item><title>Giá vàng tăng</title><link>http://a</link><pubDate>Sun, 01 Nov 2026 02:23:43 GMT</pubDate></item>" \
              "<item><title>Tin khác</title><link>http://b</link></item></c>"
        with mock.patch.object(search, "google_news", side_effect=RuntimeError("down")), \
                mock.patch("infrastructure.marketdata.feed_items",
                           lambda url, count: ET.fromstring(xml).findall("item")), redirect_stderr(io.StringIO()) as err:
            found, backup = search.results("giá vàng", 24)
        self.assertTrue(backup)
        self.assertEqual({f[1] for f in found}, {"http://a"})
        self.assertIn("chuyển sang RSS", err.getvalue())
        with mock.patch.object(search, "google_news", return_value=[("A", "l", "B", None)]):
            self.assertEqual(search.results("a", 24), ([("A", "l", "B", None)], False))

    def test_tim_noi(self):
        vn = {"name": "Huế", "latitude": 1, "longitude": 2, "country_code": "VN"}
        with mock.patch("infrastructure.openmeteo.geocode", side_effect=lambda name, country=None: vn if country else None):
            self.assertEqual(place_service.find_place("hue"), ((1, 2), "Huế"))
        with mock.patch("infrastructure.openmeteo.geocode", return_value=None):
            self.assertIsNone(place_service.find_place("zzz"))


class ManHinh(unittest.TestCase):
    def test_ket_qua_tim_tin(self):
        now = datetime(2026, 11, 15, 10, tzinfo=UTC)
        found = [("Vàng & bạc", "http://x?a=1&b=2", "Báo", now - timedelta(hours=2)), ("Tin", "http://y", "", None)]
        text = view.results_text("giá vàng", 48, found, True, now)
        self.assertIn("🔎 <b>Tin về “giá vàng”</b> · 2 ngày qua", text)
        self.assertIn('• <a href="http://x?a=1&amp;b=2">Vàng &amp; bạc</a>\n   <i>Báo · 2 giờ trước</i>', text)
        self.assertIn("• <a href=\"http://y\">Tin</a>", text)
        self.assertIn("Google News đang lỗi", text)
        self.assertIn("/tin giá vàng 30ngay", view.results_text("giá vàng", 24, [], False, now))
        self.assertEqual(view.headlines_text(["a", "b"]), "📰 <b>Tin nổi bật</b>\na\nb\n\n<i>Tìm theo từ khóa: /tin giá vàng</i>")

    def test_dong_mua(self):
        self.assertEqual(thoitiet_view.rain_line(True, None, None), "🌧️ Đang mưa")
        self.assertEqual(thoitiet_view.rain_line(False, 1, "khoảng 10:00"), "⚠️ Sắp mưa khoảng 10:00")
        self.assertEqual(thoitiet_view.rain_line(False, None, None), "🌂 2 tiếng tới không mưa")

    def test_bao_cao_thieu_mot_phan_van_gui(self):
        now = datetime(2026, 11, 15, 6, 30, tzinfo=timezone(timedelta(hours=7)))
        with mock.patch.object(thoitiet.clock, "now_vn", lambda: now), \
                mock.patch.object(thoitiet, "weather", return_value=["thời tiết"]), \
                mock.patch.object(thoitiet, "rain_outlook", side_effect=RuntimeError("x")), \
                mock.patch.object(thoitiet, "hourly", return_value=[]), redirect_stderr(io.StringIO()) as err:
            text = thoitiet.report((1, 2), "Huế")
        self.assertEqual(text, "<b>🌤️ Thời tiết Huế – 06:30</b>\nthời tiết")
        self.assertIn("mưa 2 tiếng tới", err.getvalue())


if __name__ == "__main__":
    unittest.main()
