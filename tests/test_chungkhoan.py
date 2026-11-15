"""Chứng khoán: đổi dòng giá VCI/VPS, tổng quan phiên, biến động giá, tin theo mã, chữ hiển thị, lệnh /stock."""
import io
import unittest
from contextlib import redirect_stderr
from datetime import datetime, timezone
from unittest import mock

from domain.chungkhoan import rules
from interface.chungkhoan import stock
from presentation.chungkhoan import view
from services.chungkhoan import market


def vci_row(symbol="FPT", price=100000.0, ref=98000.0, volume=1000):
    return {"listingInfo": {"symbol": symbol, "organName": "FPT & Co", "board": "HSX", "listedShare": 1000},
            "matchPrice": {"matchPrice": price, "referencePrice": ref, "ceilingPrice": 104860.0, "floorPrice": 91140.0,
                           "openPrice": 99000.0, "highest": 101000.0, "lowest": 98500.0, "accumulatedVolume": volume,
                           "accumulatedValue": 123456.0, "foreignBuyValue": 5e9, "foreignSellValue": 2e9},
            "bidAsk": {"bidPrices": [{"price": 99900.0, "volume": 100}], "askPrices": [{"price": 100100.0, "volume": 200}]}}


class Luat(unittest.TestCase):
    def test_dong_gia_vci(self):
        q = rules.from_vci(vci_row())
        self.assertEqual((q["symbol"], q["exchange"], q["value"], q["bids"]), ("FPT", "HOSE", 123456e6, [(99900.0, 100)]))
        self.assertIsNone(rules.from_vci({"listingInfo": {}, "matchPrice": {}}))  # mã không tồn tại

    def test_dong_gia_vps(self):
        r = {"sym": "FPT", "lastPrice": 53.2, "r": 52.0, "c": 55.6, "f": 48.4, "openPrice": "52.5", "highPrice": "53.5",
             "lowPrice": "52.1", "lot": 12, "fBValue": "1000", "fSValue": "400", "g1": "53.1|10|x", "g2": "0|0|x",
             "g3": "0|0|x", "g4": "53.3|15|x", "g5": "0|0|x", "g6": "0|0|x"}
        q = rules.from_vps(r)
        self.assertEqual((q["price"], q["volume"], q["bids"], q["asks"]), (53200.0, 120, [(53100.0, 100)], [(53300.0, 150)]))

    def test_phien_giao_dich(self):
        label = lambda d, h, m: rules.session_label(datetime(2026, 11, d, h, m))
        self.assertEqual(label(16, 8, 0), "Chưa mở cửa, số liệu phiên trước")
        self.assertEqual(label(16, 10, 0), "Phiên sáng")
        self.assertEqual(label(16, 12, 0), "Nghỉ trưa")
        self.assertEqual(label(16, 14, 40), "Khớp lệnh đóng cửa (ATC)")
        self.assertEqual(label(16, 15, 0), "Đã đóng cửa")
        self.assertEqual(label(15, 10, 0), "Cuối tuần, không giao dịch")

    def test_ro_vn30_va_bien_dong(self):
        qs = [{"symbol": s, "price": p, "ref": 100.0, "f_buy": b, "f_sell": 0}
              for s, p, b in [("A", 105.0, 1), ("B", 98.0, 2), ("C", 100.0, 3), ("D", 0, 4), ("E", 101.0, 5)]]
        up, down, net = rules.movers(qs)
        self.assertEqual(([q["symbol"] for q in up], [q["symbol"] for q in down], net), (["A", "E"], ["B"], 11))
        t = [int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp()) + i * 86400 for i in range(40)]
        c = [50.0 + i for i in range(40)]
        changes, low, high = rules.performance(t, c, 2026, now_ts=t[-1])
        self.assertEqual([label for label, _ in changes], ["1 tuần", "1 tháng"])  # chưa có dữ liệu năm trước
        self.assertEqual((low, high), (50000.0, 89000.0))
        changes, *_ = rules.performance(t, c, 2027, now_ts=t[-1])
        self.assertEqual(changes[-1][0], "từ đầu năm")

    def test_gio_dang_rss(self):
        self.assertEqual(rules.published_at("Sun, 01 Nov 2026 02:23:43 GMT").hour, 2)
        self.assertIsNone(rules.published_at("bậy"))
        self.assertIsNone(rules.published_at(None))


class DichVu(unittest.TestCase):
    def test_gia_vci_loi_thi_dung_vps(self):
        with mock.patch("infrastructure.stockfeeds.vci_quotes", side_effect=RuntimeError("down")), \
                mock.patch("infrastructure.stockfeeds.vps_quote", return_value=[]), redirect_stderr(io.StringIO()) as err:
            self.assertIsNone(market.quote("XYZ"))
        self.assertIn("chuyển sang VPS", err.getvalue())

    def test_gia_nhieu_ma(self):
        with mock.patch("infrastructure.stockfeeds.vci_quotes", return_value=[vci_row("FPT"), {"listingInfo": {}, "matchPrice": {}}]):
            self.assertEqual(list(market.quotes(["FPT", "NONE"])), ["FPT"])
        self.assertEqual(market.quotes([]), {})

    def test_chi_tiet_khi_gia_loi(self):
        with mock.patch.object(market, "quote", side_effect=RuntimeError("x")), \
                mock.patch.object(market, "performance", return_value=None), \
                mock.patch.object(market, "news", return_value=[]), redirect_stderr(io.StringIO()):
            q, perf, articles = market.detail("FPT")
        self.assertIsInstance(q, RuntimeError)
        self.assertEqual(view.detail("FPT", q, perf, articles), "⚪ <b>FPT</b>: không lấy được giá, thử lại sau nhé")

    def test_tin_google(self):
        xml = (b"<rss><channel><item><title> A - B </title><link>http://x/1</link><source>B</source>"
               b"<pubDate>Sun, 01 Nov 2026 02:23:43 GMT</pubDate></item></channel></rss>")
        with mock.patch("infrastructure.stockfeeds.google_news_xml", return_value=xml):
            items = market.google_news("q")
            self.assertEqual(items[0][:3], ("A - B", "http://x/1", "B"))
            self.assertEqual(market.news("FPT"), [("A - B", "http://x/1")])


class ManHinh(unittest.TestCase):
    def test_chu_ngan(self):
        self.assertEqual((view.dong(53000), view.dong(0), view.ty(3.32e11), view.ty(8e9), view.volume(2.5e6), view.volume(999)),
                         ("53.000", "–", "332 tỷ", "8,0 tỷ", "2,50 triệu cp", "999 cp"))
        self.assertEqual((view.change(105, 100, 0), view.change(5, 0, 0)), ("+5 (+5,00%)", "+5 (+0,00%)"))
        self.assertEqual((view.color(2, 1), view.color(1, 2), view.color(1, 1)), ("🟢", "🔴", "🟡"))

    def test_chi_tiet_mot_ma(self):
        q = rules.from_vci(vci_row())
        text = view.detail("FPT", q, ([("1 tuần", 2.5)], 80000.0, 120000.0), [("Tin & A", "http://x?a=1&b=2")])
        self.assertIn("<b>FPT</b> · HOSE · FPT &amp; Co", text)
        self.assertIn("🟢 <b>100.000</b>  +2.000 (+2,04%)", text)
        self.assertIn("Khối ngoại: mua 5,0 tỷ · bán 2,0 tỷ · mua ròng 3,0 tỷ", text)
        self.assertIn("1 tuần +2,5%", text)
        self.assertIn('• <a href="http://x?a=1&amp;b=2">Tin &amp; A</a>', text)
        self.assertIn("Vốn hóa 0,1 tỷ", text)
        self.assertEqual(view.detail("ZZZ", None, None, None), "❓ Không tìm thấy mã <b>ZZZ</b>")
        ceil = view.detail("FPT", rules.from_vci(vci_row(price=104860.0)), None, None)
        self.assertIn("🟣", ceil)
        self.assertIn("<i>Không lấy được tin</i>", ceil)
        self.assertIn("<i>Không có tin trong 7 ngày qua</i>", view.detail("FPT", q, None, []))

    def test_tong_quan(self):
        table = {"VN-Index": (1250.0, 1240.0, 15e12, "200", "150", "40")}
        now = datetime(2026, 11, 16, 10, 5)
        text = view.summary(now, view.index_lines(table), view.mover_lines([{"symbol": "A", "price": 105, "ref": 100}], [], -3e9))
        self.assertIn("📈 <b>Chứng khoán – Thứ Hai 16/11, 10:05</b>\n<i>Phiên sáng</i>", text)
        self.assertIn("🟢 VN-Index: <b>1.250,00</b>  +10,00 (+0,81%)\n      GT 15.000 tỷ · ▲200 ▼150 ■40", text)
        self.assertIn("🟢 Tăng mạnh: <b>A</b> +5,00%", text)
        self.assertIn("🌏 Khối ngoại bán ròng 3,0 tỷ", text)


class LenhStock(unittest.TestCase):
    def test_ma_khong_hop_le_va_qua_nhieu(self):
        self.assertEqual(stock.stock_command(["fp", "ok1"]), "Mã không hợp lệ: FP. Ví dụ: /stock FPT")
        with mock.patch.object(stock, "stock_detail", side_effect=lambda s: s):
            text = stock.stock_command(["aaa", "bbb", "ccc", "ddd", "AAA"])
        self.assertTrue(text.startswith("AAA\n\n━━━━━━━━━━\n\nBBB\n\n━━━━━━━━━━\n\nCCC"))
        self.assertTrue(text.endswith("Mỗi lần xem tối đa 3 mã.</i>"))

    def test_tong_quan_dung_vndirect_khi_vps_loi(self):
        with mock.patch.object(market, "summary_data", return_value=(None, None)), \
                mock.patch.object(stock, "stocks", return_value=["dòng VNDirect"]):
            text = stock.market_summary()
        self.assertIn("dòng VNDirect", text)
        self.assertNotIn("Trong rổ VN30", text)


if __name__ == "__main__":
    unittest.main()
