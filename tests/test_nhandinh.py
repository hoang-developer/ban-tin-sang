"""Nhận định trong phiên: số liệu ngành và khuyến nghị (tính thuần), AI lọc mã lạ, công tắc tự gửi, chữ, lệnh."""
import io
import unittest
from contextlib import redirect_stderr
from datetime import datetime, timedelta, timezone
from unittest import mock

from tests import harness as h

from domain.nhandinh import rules
from infrastructure import ai as ai_client
from interface.nhandinh import analysis
from presentation.nhandinh import view
from repositories.nhandinh import cache
from services.nhandinh import ai as ai_service
from services.nhandinh import data as service


def quote(price, ref=100000.0, value=50e9, buy=3e9, sell=1e9, listed=1e9):
    return {"price": price, "ref": ref, "value": value, "f_buy": buy, "f_sell": sell, "listed": listed}


def sample():
    quotes = {"AAA": quote(104000.0), "BBB": quote(98000.0, value=60e9), "CCC": quote(100000.0, value=5e9), "NOREF": quote(1, ref=0)}
    names = {"AAA": "Thép", "BBB": "Thép", "CCC": "Khác"}
    stocks, sectors = rules.board(quotes, names)
    recs = rules.rec_rows({"AAA": [{"firm": "HSC", "type": "buy", "targetPrice": 120, "avgTargetPrice": 125},
                                   {"firm": "VCI", "type": "HOLD", "targetPrice": 110}]}, {"AAA": 104000.0})
    index = {"VN-Index": (1250.0, 1240.0, 15e12, "200", "150", "40")}
    news = [{"nguon": "CafeF", "tieu_de": "AAA tăng", "link": "http://x?a=1&b=2", "luc": None, "tom_tat": "tóm tắt"}]
    return {"index": index, "stocks": stocks, "sectors": sectors, "recs": recs, "news": news, "symbols": {"AAA", "BBB", "CCC"}}


class Luat(unittest.TestCase):
    def test_ten_nganh_va_khuyen_nghi(self):
        names = rules.industry_names([{"vietnameseName": "Dịch vụ tài chính", "codeList": "AAA, BBB"},
                                      {"vietnameseName": "Ngành   lạ", "codeList": "CCC"}, {"vietnameseName": None, "codeList": ""}])
        self.assertEqual(names, {"AAA": "Chứng khoán, tài chính", "BBB": "Chứng khoán, tài chính", "CCC": "Ngành lạ"})
        recs = rules.recommendations_by_code([{"code": "AAA", "firm": "HSC", "extra": 1}, {"code": "AAA", "firm": "VCI"}])
        self.assertEqual([r["firm"] for r in recs["AAA"]], ["HSC", "VCI"])
        self.assertNotIn("extra", recs["AAA"][0])

    def test_tin_gop(self):
        now = datetime(2026, 11, 13, 10, tzinfo=timezone.utc)
        item = lambda title, hours: {"tieu_de": title, "luc": now - timedelta(hours=hours) if hours is not None else None}
        got = rules.merge_news([[item("A", 1), item("Cũ", 30)], None, [item("a", 2), item("Không giờ", None), item("B", 0.5)]], 18, now)
        self.assertEqual([i["tieu_de"] for i in got], ["B", "A", "Không giờ"])  # bỏ tin cũ và tin trùng tiêu đề

    def test_bang_nganh(self):
        stocks, sectors = rules.board({"AAA": quote(104000.0), "BBB": quote(98000.0, value=60e9), "CCC": quote(100000.0, value=5e9),
                                       "X": quote(1, ref=0)}, {"AAA": "Thép", "BBB": "Thép", "CCC": "Khác"})
        self.assertEqual([s["ma"] for s in stocks], ["AAA", "BBB", "CCC"])  # bỏ mã thiếu giá tham chiếu
        self.assertEqual([g["ten"] for g in sectors], ["Thép"])  # bỏ ngành "Khác"
        self.assertAlmostEqual(sectors[0]["pct"], 1.0)
        self.assertEqual((sectors[0]["tang"], sectors[0]["giam"]), (1, 1))

    def test_khuyen_nghi_xep_hang(self):
        recs = rules.rec_rows({"AAA": [{"firm": "HSC", "type": "buy", "avgTargetPrice": 125}, {"firm": "VCI", "type": "HOLD"}],
                               "BBB": [{"firm": "SSI", "type": "x", "targetPrice": 0}]}, {"AAA": 100000.0})
        self.assertEqual([(r["ma"], r["so"], r["loai"], r["muc_tieu"]) for r in recs], [("AAA", 2, "MUA", 125000), ("BBB", 1, "x", 0)])
        self.assertAlmostEqual(recs[0]["con_tang"], 25.0)
        self.assertIsNone(recs[1]["con_tang"])

    def test_chu_so_gon(self):
        self.assertEqual((rules.pct(1.234), rules.pct(-2.5), rules.whole_pct(45.4), rules.billions(1.643e12)), ("+1,2%", "-2,5%", "+45%", "1.643 tỷ"))
        self.assertEqual([rules.signed_billions(x) for x in (0.4e9, 5e9, -3e12)], ["0 tỷ", "+5 tỷ", "−3.000 tỷ"])
        self.assertEqual([rules.pt_short(x) for x in (33000, 53600, 109461)], ["33k", "53,6k", "109k"])
        self.assertEqual([rules.session_name(datetime(2026, 11, 13, *t)) for t in ((8, 0), (10, 0), (12, 0), (14, 0), (14, 45))],
                         ["trước phiên", "phiên sáng", "nghỉ trưa", "phiên chiều", "sau phiên"])


class DichVu(unittest.TestCase):
    def setUp(self):
        h.reset()
        self.real = (ai_client.chat, None)
        self.addCleanup(lambda: (setattr(ai_client, "chat", self.real[0])))

    def test_ai_chi_giu_dong_dung_dang_va_ma_that(self):
        ai_client.chat = lambda *a, **k: ("🔥 Thép +1%\n- 🎯 AAA tăng, 2 CTCK\n🎯 ZZZ lạ mã ngoài dữ liệu\nkhông biểu tượng\n⚠️ Rủi ro <b>", "m")
        with redirect_stderr(io.StringIO()) as err:
            lines = ai_service.ai_lines({**sample(), "symbols": {"AAA", "ZZZ"}})
        self.assertEqual(lines, ["🔥 Thép +1%", "🎯 AAA tăng, 2 CTCK", "⚠️ Rủi ro &lt;b&gt;"])
        self.assertIn("bỏ dòng có mã ngoài dữ liệu", err.getvalue())

    def test_ai_khong_co_khoa_hoac_loi(self):
        import os
        ai_client.chat = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("bận"))
        with redirect_stderr(io.StringIO()):
            self.assertEqual(ai_service.ai_lines(sample()), [])
        del os.environ["GEMINI_API_KEY"]
        self.assertEqual(ai_service.ai_lines(sample()), [])

    def test_du_lieu_gui_ai_co_so_lieu(self):
        text = ai_service.ai_input(sample())
        self.assertIn("THỊ TRƯỜNG: VN-Index 1.250,00", text)
        self.assertIn("KHUYẾN NGHỊ CỦA CÁC CTCK (30 ngày): AAA · 2 CTCK MUA", text)
        self.assertIn("- [CafeF] AAA tăng: tóm tắt", text)

    def test_cong_tac_tu_gui(self):
        self.assertFalse(cache.auto_off())
        cache.set_auto(False)
        self.assertTrue(cache.auto_off())
        cache.set_auto(True)
        self.assertFalse(cache.auto_off())

    def test_du_lieu_it_doi_chi_lay_mot_lan(self):
        calls = []
        self.assertEqual(cache.remembered("nhandinh:thu", 60, lambda: calls.append(1) or {"a": 1}), {"a": 1})
        self.assertEqual(cache.remembered("nhandinh:thu", 60, lambda: calls.append(1) or {"a": 2}), {"a": 1})
        self.assertEqual(calls, [1])


class ManHinh(unittest.TestCase):
    def test_bang_nganh_va_khuyen_nghi(self):
        data = sample()
        now = datetime(2026, 11, 13, 10, 15)
        text = view.nganh_text(data, now)
        self.assertIn("🔥 <b>Ngành trên HOSE</b> · 10:15 13/11", text)
        self.assertIn("VN-Index <b>1.250,00</b> (+0,8%)", text)
        self.assertIn("🟢 <b>Thép</b> +1,0%", text)
        self.assertIn("💰 Hút tiền nhất: Thép", text)
        detail = view.recommendation_detail("AAA", [{"firm": "HSC", "type": "BUY", "targetPrice": 120, "reportDate": "2026-11-12"}], 100000.0)
        self.assertIn("12/11 HSC MUA 120k (+20%)", detail)
        self.assertIn("Nguồn VNDirect", detail)
        self.assertIn("<b>AAA</b> · 2 CTCK MUA · mục tiêu 125k (+20%)", view.recommendation_list(data["recs"]))

    def test_tin_va_ban_tom_tat(self):
        data = sample()
        self.assertEqual(view.news_line(data["news"][0]), '• <a href="http://x?a=1&amp;b=2">AAA tăng</a> (CafeF)')
        lines = view.short_fallback(data)
        self.assertTrue(lines[0].startswith("🔥 Thép"))
        self.assertIn("🎯 AAA +4,0%: 2 CTCK khuyến nghị MUA, mục tiêu 125k (+20%)", lines)
        self.assertEqual(view.headline(datetime(2026, 11, 13, 10, 15), data)[:30], "🧠 <b>Nhận định 10:15</b> · VN-")


class Lenh(unittest.TestCase):
    def setUp(self):
        h.reset()

    def test_bat_tat_tu_gui(self):
        self.assertIn("Đã tắt", analysis.nhandinh(["tat"]))
        self.assertTrue(cache.auto_off())
        self.assertIsNone(analysis.scheduled(h.CLOCK["now"]))
        self.assertIn("Đã bật", analysis.nhandinh(["bat"]))
        self.assertFalse(cache.auto_off())

    def test_ngay_nghi_khong_gui(self):
        with mock.patch.object(analysis, "gather", return_value={"index": {"VN-Index": (1, 1, 0, 0, 0, 0)}}):
            self.assertIsNone(analysis.scheduled(h.CLOCK["now"]))
        with mock.patch.object(analysis, "gather", return_value={"index": {}}):
            self.assertIsNone(analysis.scheduled(h.CLOCK["now"]))

    def test_nut_bam(self):
        self.assertEqual(analysis.on_button("zzz"), (None, None))
        self.assertEqual(analysis.on_button("moi")[0], "Đang tổng hợp lại…")
        self.assertEqual([analysis.on_button(a)[1][0] for a in ("nganh", "kn", "tin")], ["send"] * 3)

    def test_khuyen_nghi_mot_ma_khong_co(self):
        with mock.patch.object(analysis, "recommendations", return_value={}):
            self.assertIn("Không có khuyến nghị nào cho ZZZ", analysis.khuyennghi(["zzz"]))


if __name__ == "__main__":
    unittest.main()
