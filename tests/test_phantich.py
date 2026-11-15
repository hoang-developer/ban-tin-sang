"""Phân tích chi tiêu: số liệu thuần (dự báo, đột biến, khoản lạ, câu hỏi), service đọc sổ, màn hình, lệnh giao diện."""
import unittest
from datetime import date, timedelta

from tests import harness as h

from interface.chitieu import commands as chitieu_commands
from domain.phantich import numbers, query
from infrastructure import ai as ai_client
from infrastructure import quickchart
from interface.phantich import analysis
from presentation.phantich import view
from services.chitieu import ledger
from services.phantich import analysis as service

DAY = date(2026, 10, 20)
CFG = {}


def spend(day, amount, note="cà phê", group="an", id_=[0]):
    id_[0] += 1
    return {"id": id_[0], "ngay": day.isoformat(), "tien": amount, "ghichu": note, "nhom": group}


class SoLieu(unittest.TestCase):
    def test_dot_bien(self):
        items = [spend(DAY, t, group="an") for t in (30_000, 40_000, 50_000, 60_000, 900_000)]
        limits = numbers.spike_limits(items, ["an", "xe"])
        self.assertEqual(limits["xe"], 500_000)  # chưa đủ 5 khoản
        self.assertEqual(limits["an"], 300_000)  # 3 lần trung vị 50k = 150k < sàn 300k

    def test_nhom_hang_ngay(self):
        self.assertEqual(numbers.daily_codes(None, CFG), ["an", "cho", "xe"])
        self.assertEqual(numbers.daily_codes(["an", "thu", "zzz"], CFG), ["an"])  # bỏ thu nhập và nhóm không có
        self.assertEqual(numbers.daily_codes(["zzz"], CFG), ["an", "cho", "xe"])

    def test_du_bao_thang(self):
        items = [spend(date(2026, 9, d), 100_000) for d in range(1, 31)] + [spend(DAY - timedelta(days=i), 200_000) for i in range(0, 14)]
        f = numbers.forecast_numbers(DAY, items, {"tong": 5_000_000})
        self.assertEqual(f["left"], 11)
        self.assertEqual(f["spent"], 200_000 * 14)  # tháng 10: 14 ngày, mỗi ngày 200k
        self.assertGreater(f["projected"], f["spent"])
        budget = f["budgets"]["tong"]
        self.assertEqual((budget["limit"], budget["spent"]), (5_000_000, f["spent"]))
        self.assertEqual(f["prev_total"], 3_000_000)
        self.assertIsNone(numbers.allowance({"budgets": {}}))
        per_day, today_left = numbers.allowance(f)
        self.assertAlmostEqual(per_day, (5_000_000 - (f["spent"] - f["today"])) / 12)
        self.assertAlmostEqual(today_left, per_day - f["today"])

    def test_du_bao_hang_ngay_bo_khoan_dot_bien(self):
        items = [spend(DAY - timedelta(days=i), 50_000) for i in range(0, 10)] + [spend(DAY, 2_000_000, "tiệc")]
        f = numbers.daily_numbers(DAY, items, ["an"], {"hangngay": 3_000_000})
        self.assertEqual(len(f["spikes"]), 1)
        self.assertEqual(f["spent"], 500_000)  # khoản 2tr là đột biến: không tính
        self.assertEqual(f["budget"], 3_000_000)
        self.assertIsNotNone(f["room"])
        self.assertIsNone(numbers.daily_numbers(DAY, items, ["an"], {})["room"])

    def test_khoan_la_thuong_va_tang_vot(self):
        history = [spend(DAY - timedelta(days=i), 50_000, group="an") for i in range(1, 8)]
        big = spend(DAY, 400_000, "tiệc", "an")
        self.assertEqual(numbers.unusual([big], history), [(big, 50_000)])
        self.assertEqual(numbers.unusual([big], history[:4]), [])  # chưa đủ 5 khoản để so
        self.assertEqual(numbers.unusual([spend(DAY, 100_000, group="an")], history), [])  # chưa tới 200k
        weeks = [spend(DAY - timedelta(days=d), 100_000, group="an") for d in range(8, 34, 2)] + \
                [spend(DAY - timedelta(days=d), 300_000, group="an") for d in (1, 2, 3)]
        got = numbers.surges(weeks, DAY, ["an", "khac"])
        self.assertEqual([g[0] for g in got], ["an"])
        self.assertEqual(numbers.surges(weeks[:2], DAY, ["an"]), [])  # chưa đủ 4 tuần dữ liệu

    def test_thoi_quen_va_ngay_trong_tuan(self):
        items = [spend(DAY, 35_000, "cà phê 11/10"), spend(DAY, 35_000, "cà phê 12/10"), spend(DAY, 90_000, "", "xe")]
        got = numbers.habits(items, lambda code: f"nhóm {code}")
        self.assertEqual(got, [("nhóm xe", 1, 90_000), ("cà phê", 2, 70_000)])
        stats = numbers.weekday_stats([spend(date(2026, 10, 19), 100_000), spend(date(2026, 10, 24), 300_000)], date(2026, 10, 19), date(2026, 10, 25))
        self.assertEqual(stats, (5, 2, 100_000, 300_000))
        self.assertIsNone(numbers.weekday_stats([], DAY, DAY))  # kỳ một ngày: thiếu loại ngày


class CauHoi(unittest.TestCase):
    def test_nhan_ra_cau_hoi(self):
        for q in ("tháng này cà phê hết bao nhiêu?", "so sánh tháng 10 với tháng 9", "tiêu nhiều hơn không", "ngày nào tiêu nhiều nhất"):
            self.assertTrue(query.is_question(q), q)
        for t in ("cà phê 35k", "", "bao nhiêu\ndòng hai"):
            self.assertFalse(query.is_question(t), t)

    def test_khoang_ngay(self):
        spans = query.periods_in("so thang 10 voi tuan truoc va 3 ngay qua", DAY)
        self.assertEqual([(a, b) for _, a, b in spans], [(date(2026, 10, 1), DAY), (date(2026, 10, 12), date(2026, 10, 18)), (date(2026, 10, 18), DAY)])
        self.assertEqual(query.month_of(12, DAY)[0], date(2025, 12, 1))  # tháng chưa tới thì là năm trước
        self.assertEqual(query.month_range(2026, 2, DAY), (date(2026, 2, 1), date(2026, 2, 28)))
        self.assertEqual(query.previous_span(date(2026, 10, 1), date(2026, 10, 31)), (date(2026, 9, 1), date(2026, 9, 30)))
        self.assertEqual(query.previous_span(date(2026, 10, 19), date(2026, 10, 20)), (date(2026, 10, 12), date(2026, 10, 13)))
        self.assertEqual(query.same_period({"tu": date(2026, 10, 1), "den": DAY, "tu2": date(2026, 9, 1), "den2": date(2026, 9, 30)}),
                         (date(2026, 9, 1), date(2026, 9, 20)))  # tháng đang dở thì so cùng kỳ

    def test_hieu_cau_hoi_theo_luat(self):
        spec = query.rule_spec("tuần này tiêu vào đâu nhiều nhất?", DAY, CFG, {})
        self.assertEqual((spec["kieu"], spec["tu"], spec["den"]), ("nhom", date(2026, 10, 19), DAY))
        spec = query.rule_spec("liệt kê các lần đổ xăng tháng này", DAY, CFG, {})
        self.assertEqual((spec["kieu"], spec["tu_khoa"]), ("liet_ke", ["đổ xăng"]))
        spec = query.rule_spec("so sánh tháng 10 với tháng 9", DAY, CFG, {})
        self.assertEqual(spec["kieu"], "so_sanh")
        self.assertTrue(query.rule_spec("lương tháng này", DAY, CFG, {})["thu"])
        self.assertEqual(query.rule_spec("ăn uống hôm qua", DAY, CFG, {})["nhom"], ["an"])

    def test_kiem_tra_bo_loc_cua_ai(self):
        spec = query.clean_spec({"kieu": "xxx", "tu": "2030-01-01", "den": "bậy", "nhom": ["an", 5, "thu"], "tu_khoa": ["a" * 40, " "]}, DAY, CFG)
        self.assertEqual(spec["kieu"], "tong")
        self.assertEqual(spec["den"], DAY)
        self.assertLessEqual(spec["tu"], spec["den"])
        self.assertEqual(spec["nhom"], ["an"])  # bỏ thu nhập, kiểu không phải mã nhóm
        self.assertEqual([len(w) for w in spec["tu_khoa"]], [30])
        cmp_spec = query.clean_spec({"kieu": "so_sanh", "tu": "2026-10-01", "den": "2026-10-20"}, DAY, CFG)
        self.assertEqual((cmp_spec["tu2"], cmp_spec["den2"]), (date(2026, 9, 1), date(2026, 9, 20)))

    def test_khop_dung_dau(self):
        self.assertTrue(query.has_word("phở bò kèm trứng", "phở"))
        self.assertFalse(query.has_word("tào phớ", "phở"))  # "phớ" khác "phở"
        self.assertFalse(query.has_word("chè đỗ đen tào phớ gánh", "phở"))
        self.assertTrue(query.has_word("pho bo", "phở"))  # ghi chú không dấu: không biết dấu đúng
        self.assertTrue(query.has_word("tào phớ", "pho"))  # gõ không dấu: khớp mọi dấu
        self.assertTrue(query.has_word("Phở Bò", "phở"))

    def test_khop_khoan(self):
        spec = {"thu": False, "nhom": ["an"], "tu_khoa": ["cafe"]}
        self.assertTrue(query.matches({"nhom": "an", "ghichu": "Cafe sáng"}, spec))
        self.assertFalse(query.matches({"nhom": "xe", "ghichu": "cafe"}, spec))
        self.assertFalse(query.matches({"nhom": "thu", "ghichu": "cafe"}, spec))  # chi mà khoản là thu


class DichVu(unittest.TestCase):
    def setUp(self):
        h.reset()
        h.at(2026, 10, 20, 12)
        self.now = h.CLOCK["now"]
        self.real = (None, ai_client.chat, quickchart.chart_png)
        self.addCleanup(lambda: (setattr(ai_client, "chat", self.real[1]),
                                 setattr(quickchart, "chart_png", self.real[2])))
        ai_client.chat = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("bận"))
        self.charts = []
        quickchart.chart_png = lambda chart, w=800, hh=500: (self.charts.append(chart), b"png")[1]
        for d in range(1, 21):
            h.at(2026, 10, d, 12)
            ledger.add("cà phê 35k\ngrab 80k\nđi chợ 250k", h.CLOCK["now"])
        h.at(2026, 10, 20, 12)

    def test_du_bao_va_nhom_hang_ngay(self):
        f = service.forecast(DAY)
        self.assertEqual(f["left"], 11)
        self.assertGreater(f["projected"], f["spent"])
        self.assertEqual(service.daily_groups(), ["an", "cho", "xe"])
        service.set_daily_groups(["xe", "xe", "an"])
        self.assertEqual(service.daily_groups(), ["xe", "an"])
        service.reset_daily_groups()
        self.assertEqual(service.daily_groups(), ["an", "cho", "xe"])
        self.assertEqual(service.daily_spent(DAY), service.daily_forecast(DAY)["spent"])

    def test_canh_bao_chi_bao_mot_lan(self):
        chitieu_commands.ngansach(["đi", "lại", "2tr"])
        first = service.alerts_data(DAY)
        again = service.alerts_data(DAY)
        self.assertTrue(first[1])  # đi lại đang trên đà vượt ngân sách
        self.assertEqual(again, ([], []))  # mỗi chuyện một lần mỗi tuần

    def test_cau_hoi_va_bo_loc(self):
        spec = service.spec_for("tháng này cà phê hết bao nhiêu?", DAY)
        self.assertEqual(spec["tu_khoa"], ["cà phê"])
        items, other = service.query_items(spec)
        self.assertEqual((len(items), other), (20, None))
        ai_client.chat = lambda *a, **k: ('{"kieu": "so_sanh", "tu": "2026-10-01", "den": "2026-10-20", "nhom": ["an"]}', "m")
        spec = service.spec_for("so sánh ăn uống", DAY)
        self.assertEqual((spec["kieu"], spec["nhom"]), ("so_sanh", ["an"]))
        items, other = service.query_items(spec)
        self.assertEqual(other, [])  # tháng 9 chưa có khoản nào
        ai_client.chat = lambda *a, **k: ("không phải json", "m")
        self.assertEqual(service.spec_for("tháng này cà phê hết bao nhiêu?", DAY)["tu_khoa"], ["cà phê"])  # AI hỏng: hiểu theo luật

    def test_nhan_xet_tu_ai(self):
        ai_client.chat = lambda *a, **k: ("- điểm một\n2. điểm hai\n• điểm ba\n• dư\n💡 gợi ý\n💡 dư", "m")
        notes = service.commentary_notes("tháng 10/2026", "số liệu")
        self.assertEqual(notes, ["• điểm một", "• điểm hai", "• điểm ba", "💡 gợi ý"])
        ai_client.chat = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("bận"))
        self.assertEqual(service.commentary_notes("x", "y"), [])


class HoiTheoDau(unittest.TestCase):
    def setUp(self):
        h.reset()
        h.at(2026, 11, 15, 12)
        self.real = ai_client.chat
        self.addCleanup(lambda: setattr(ai_client, "chat", self.real))
        ai_client.chat = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("bận"))
        for note in ("phở bò 40k", "tào phớ 25k", "phở bò kèm trứng 74k", "ăn tào phớ 24k", "chè đỗ đen tào phớ gánh 18k"):
            ledger.add(note, h.CLOCK["now"])

    def test_an_pho_khong_lan_tao_pho(self):
        text = analysis.hoi("tháng này ăn phở bao nhiêu lần và hết bao nhiêu tiền?", date(2026, 11, 15))
        self.assertIn("Tổng: <b>114.000đ</b> · 2 khoản", text)
        self.assertNotIn("tào phớ", text)
        self.assertIn("phở bò kèm trứng", text)


class ManHinh(unittest.TestCase):
    def setUp(self):
        DichVu.setUp(self)  # cùng dữ liệu mẫu
        self.addCleanup(lambda: (setattr(ai_client, "chat", self.real[1]),
                                 setattr(quickchart, "chart_png", self.real[2])))

    def test_chu_ngan(self):
        self.assertEqual((view.approx(232_143), view.times(2.0), view.times(1.25), view.trend(12.4), view.trend(-8)),
                         ("232.000đ", "2", "1,2", "🔺12%", "🔻8%"))
        self.assertEqual(view.vnd_round(1234.6), "1.235đ")
        self.assertEqual(view.habit_text("cà phê", 3, 105_000), "cà phê 105k (3 lần)")
        self.assertEqual(view.daily_label(["an", "xe"], CFG), "ăn uống, đi lại")
        self.assertEqual(view.span_text(DAY, DAY), "Thứ Ba 20/10/2026")

    def test_man_hinh_du_bao(self):
        text = analysis.forecast_text(DAY)
        self.assertIn("🔮 <b>Dự báo tháng 10</b> · còn 11 ngày", text)
        self.assertIn("➡️ Cả tháng", text)
        daily = analysis.daily_text(DAY)
        self.assertIn("🔮 <b>Chi hằng ngày tháng 10</b>", daily)
        self.assertIn("Mọi khoản: /dubao tatca", daily)
        self.assertIn("Đang tính là chi tiêu hằng ngày", analysis.dubao(["nhom"]))
        self.assertIn("Không thấy nhóm: zzz", analysis.dubao(["nhom", "zzz"]))
        self.assertIn("giờ tính: ăn uống", analysis.dubao(["nhom", "ăn", "uống"]))
        self.assertIn("Về mặc định", analysis.dubao(["nhom", "macdinh"]))

    def test_hoi_va_bieu_do_va_nhan_xet(self):
        self.assertEqual(analysis.hoi("  ", DAY), view.HOI_HELP)
        text = analysis.hoi("tháng này cà phê hết bao nhiêu?", DAY)
        self.assertIn("Tổng: <b>700.000đ</b> · 20 khoản", text)
        reply = analysis.chart_reply("thang", DAY)
        self.assertEqual(len(reply["photos"]), 2)
        self.assertEqual(self.charts[0]["type"], "doughnut")
        self.assertIn("Chưa có khoản chi nào", analysis.chart_reply("ngay", date(2025, 1, 5)))
        self.assertIn("📌 <b>Số liệu tháng 10/2026</b>", analysis.commentary("thang", DAY))
        self.assertNotIn("Nhận xét", analysis.commentary("thang", DAY))  # AI giả đang bận
        self.assertIn("Chưa có khoản chi nào", analysis.commentary("ngay", date(2025, 1, 5)))

    def test_chua_noi_kho(self):
        real = common_ready()
        try:
            self.assertEqual(analysis.hoi("x", DAY), view_need())
        finally:
            real()


def common_ready():
    from interface import common
    saved = common.kho.ready
    common.kho.ready = lambda: False
    return lambda: setattr(common.kho, "ready", saved)


def view_need():
    from presentation.chitieu.view import NEED_STORE
    return NEED_STORE


if __name__ == "__main__":
    unittest.main()
