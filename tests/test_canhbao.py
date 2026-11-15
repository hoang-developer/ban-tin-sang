"""Cảnh báo tức thì: luật báo (tính thuần), các bước kiểm tra với nguồn giả, chữ cảnh báo."""
import io
import unittest
import xml.etree.ElementTree as ET
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from unittest import mock

from domain.canhbao import rules
from domain.common.dates import VN_TZ
from interface.canhbao import runner
from presentation.canhbao import view
from services.canhbao import checks

NOW = datetime(2026, 11, 16, 10, 0, tzinfo=VN_TZ)  # thứ hai, đang giờ giao dịch


def slots(mm=None, codes=None):
    base = datetime(2026, 11, 16, 10, 0)
    times = [(base + timedelta(minutes=15 * i)).strftime("%Y-%m-%dT%H:%M") for i in range(9)]
    return list(zip(times, mm or [0.0] * 9, codes or [1] * 9))


class Luat(unittest.TestCase):
    def test_mua(self):
        self.assertEqual(rules.rain_label(1), "mưa nhỏ")
        self.assertEqual(rules.rain_label(5), "mưa vừa")
        self.assertEqual(rules.rain_label(10), "mưa to")
        self.assertEqual(rules.rain_label(40), "mưa rất to")
        self.assertEqual(rules.rain_outlook(slots(), NOW), (False, None, None))
        self.assertEqual(rules.rain_outlook(slots([0.5] + [0] * 8), NOW), (True, None, None))
        raining, start, info = rules.rain_outlook(slots([0, 0, 0, 0.4, 1.2] + [0] * 4, [1, 1, 1, 1, 96, 1, 1, 1, 1]), NOW)
        self.assertEqual((raining, start), (False, datetime(2026, 11, 16, 10, 45, tzinfo=VN_TZ)))
        self.assertEqual(info, {"minutes": 45, "peak": 4.8, "storm": True})

    def test_nghi_giua_hai_lan_bao_mua(self):
        state = {}
        self.assertFalse(rules.rain_cooling(state, NOW))
        rules.mark_rain(state, NOW)
        self.assertTrue(rules.rain_cooling(state, NOW + timedelta(hours=2, minutes=59)))
        self.assertFalse(rules.rain_cooling(state, NOW + timedelta(hours=3)))

    def test_khong_khi(self):
        state = {}
        self.assertEqual(rules.air_step(state, NOW, 80), ("mốc", 1))  # lần đầu trong ngày chỉ lấy mốc
        self.assertEqual(rules.air_step(state, NOW, 140), ("im", 2))  # chưa quá 150
        self.assertEqual(rules.air_step(state, NOW, 160), ("báo", 3))
        self.assertEqual(rules.air_step(state, NOW, 170), ("im", 3))  # không xấu hơn mức đã báo
        self.assertEqual(rules.air_step(state, NOW + timedelta(days=1), 170), ("mốc", 3))

    def test_vang_va_chi_so(self):
        state = {}
        self.assertEqual(rules.gold_step(state, 150.0), (150.0, 0.0, False))
        base, change, alert = rules.gold_step(state, 151.2)
        self.assertEqual((base, round(change, 6), alert), (150.0, 1.2, True))
        self.assertEqual(state["gold_base"], 151.2)
        t = [1763078400, int(datetime(2026, 11, 16, tzinfo=timezone.utc).timestamp())]
        state = {}
        pct, alert = rules.index_alert(state, NOW, t, [1000.0, 1010.0])
        self.assertEqual((round(pct, 6), alert), (1.0, False))
        self.assertEqual(rules.index_alert(state, NOW, t, [1000.0, 1020.0])[1], True)
        self.assertEqual(rules.index_alert(state, NOW, t, [1000.0, 1021.0])[1], False)  # cùng nấc 1,5%
        self.assertIsNone(rules.index_alert({}, NOW + timedelta(days=1), t, [1.0, 1.0]))
        self.assertTrue(rules.in_session(NOW))
        self.assertFalse(rules.in_session(NOW.replace(hour=15, minute=1)))
        self.assertFalse(rules.in_session(NOW + timedelta(days=5)))  # chủ nhật

    def test_ma_cham_gia_va_tin(self):
        state = {}
        self.assertEqual(rules.watch_hits(state, "FPT", 49, 50, 60), [("xuống", 50)])
        self.assertEqual(rules.watch_hits(state, "FPT", 48, 50, 60), [])  # vừa báo rồi
        self.assertEqual(rules.watch_hits(state, "FPT", 55, 50, 60), [])  # quay lại
        self.assertEqual(rules.watch_hits(state, "FPT", 49, 50, 60), [("xuống", 50)])
        self.assertEqual(rules.watch_hits(state, "VNM", 80, None, 70), [("lên", 70)])
        keywords = [("Giá xăng", rules.normalize("Giá xăng"))]
        items = [("GIÁ XĂNG tăng", "http://a"), ("Tin khác", "http://b"), ("Giá xăng giảm", "http://c")]
        got = rules.news_hits(state, "Báo", items, keywords)
        self.assertEqual([h[2] for h in got], ["http://a", "http://c"])
        self.assertEqual(rules.news_hits(state, "Báo", items, keywords), [])  # đã báo
        state["news_seen"] = list(map(str, range(400)))
        rules.trim_seen(state)
        self.assertEqual(len(state["news_seen"]), 300)


class Buoc(unittest.TestCase):
    def test_bao_mua(self):
        state = {}
        with mock.patch("infrastructure.openmeteo.minutely", return_value=slots([0, 0.4] + [0] * 7)):
            alerts, note = checks.check_rain(state, NOW)
        self.assertEqual(alerts[0]["kind"], "rain")
        self.assertEqual(note, "mưa: báo mưa lúc 10:15")
        self.assertEqual(checks.check_rain(state, NOW + timedelta(hours=1)), ([], "mưa: vừa báo, đang chờ"))

    def test_vang_chi_so_va_ma(self):
        with mock.patch("infrastructure.marketdata.pnj_gold", return_value={"SJC": {"giaban": 15200}}):
            state = {"gold_base": 150.0}
            alerts, note = checks.check_gold(state, NOW)
        self.assertEqual((alerts[0]["kind"], alerts[0]["price"], note), ("gold", 152.0, "vàng SJC 152,0: đã báo"))
        t = [1763078400, int(datetime(2026, 11, 16, tzinfo=timezone.utc).timestamp())]
        with mock.patch.object(checks, "index_history", return_value=(t, [1000.0, 1030.0])):
            alerts, note = checks.check_index({}, NOW)
            self.assertEqual((alerts[0]["kind"], note), ("index", "VN-Index +3.00%: đã báo"))
            self.assertEqual(checks.check_index({}, NOW + timedelta(hours=7)), ([], "VN-Index: ngoài giờ giao dịch"))
            alerts, note = checks.check_watchlist({}, NOW, {"FPT": (50, 60)})
            self.assertEqual(note, "cổ phiếu: FPT 1030.0")
        self.assertEqual(checks.check_watchlist({}, NOW, {}), ([], "cổ phiếu: chưa có mã theo dõi"))

    def test_tin_va_chay_het_cac_buoc(self):
        def items(url, count):
            if "tuoitre" in url:
                raise RuntimeError("down")
            return ET.fromstring("<c><item><title>Lãi suất giảm</title><link>http://x/1</link></item></c>").findall("item")

        with mock.patch("infrastructure.marketdata.feed_items", items), redirect_stderr(io.StringIO()) as err:
            alerts, note = checks.check_news({}, NOW, ["lãi suất"])
        self.assertEqual(len(alerts), 1)  # các báo trả cùng một link nên chỉ báo lần đầu
        self.assertEqual(note, "tin: 1 tin mới khớp từ khóa")
        self.assertIn("tin Tuổi Trẻ", err.getvalue())
        boom = mock.Mock(side_effect=RuntimeError("x"), __name__="check_boom")
        with mock.patch.object(checks, "CHECKS", [boom, lambda s, n: ([{"kind": "x"}], "ok")]), \
                redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
            self.assertEqual(checks.run({}, NOW), [{"kind": "x"}])
        self.assertEqual(out.getvalue(), "- ok\n")
        self.assertIn("check_boom", err.getvalue())


class ChuCanhBao(unittest.TestCase):
    def test_tung_loai(self):
        start = datetime(2026, 11, 16, 10, 45, tzinfo=VN_TZ)
        self.assertEqual(view.alert_text({"kind": "rain", "start": start, "minutes": 45, "peak": 4.8, "storm": True}),
                         "☔ <b>Sắp mưa</b>: khoảng 10:45 (~45 phút nữa) Hà Nội có mưa vừa kèm dông ⛈️. Nhớ mang áo mưa!")
        self.assertIn("mức kém", view.alert_text({"kind": "air", "icon": "🟠", "label": "Kém", "aqi": 160}))
        self.assertIn("Vàng SJC giảm 1,5 triệu</b> 📉", view.alert_text({"kind": "gold", "base": 152.0, "price": 150.5, "change": -1.5}))
        self.assertIn("VN-Index tăng mạnh", view.alert_text({"kind": "index", "close": 1230.0, "pct": 2.5}))
        self.assertIn("FPT xuống 50.000đ</b>: giá hiện tại 49.000đ", view.alert_text(
            {"kind": "watch", "symbol": "FPT", "word": "xuống", "target": 50, "price": 49}))
        self.assertEqual(view.alert_text({"kind": "news", "keyword": "giá xăng", "source": "Báo", "link": "http://a?x=1&y=2",
                                          "title": "A <b>"}),
                         '📰 <b>giá xăng</b> · Báo: <a href="http://a?x=1&amp;y=2">A &lt;b&gt;</a>')

    def test_mo_ta_mua_cho_thoi_tiet(self):
        start = datetime(2026, 11, 16, 10, 15, tzinfo=VN_TZ)
        with mock.patch("services.canhbao.checks.rain_outlook",
                        return_value=(False, start, {"minutes": 15, "peak": 1.0, "storm": False})):
            self.assertEqual(runner.rain_outlook(NOW, name="TP.HCM"),
                             (False, start, "khoảng 10:15 (~15 phút nữa) TP.HCM có mưa nhỏ"))
        with mock.patch("services.canhbao.checks.rain_outlook", return_value=(False, None, None)):
            self.assertEqual(runner.rain_outlook(NOW), (False, None, None))


if __name__ == "__main__":
    unittest.main()
