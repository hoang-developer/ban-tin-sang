"""Kỳ báo cáo, loại thu nhập, ngân sách, tin báo khoản vừa ghi và nút chọn nhóm, báo cáo một kỳ."""
import unittest
from datetime import date

from tests import harness as h

from infrastructure import kho
from repositories import keys
from domain.chitieu import income, period, refs
from infrastructure import ai as ai_client
from domain.chitieu import text as chitieu_text
from presentation.chitieu import view
from repositories.chitieu import budget as budget_repo
from services.chitieu import budget, ledger, report

DAY = date(2026, 10, 20)
CFG = {}


class HamThuan(unittest.TestCase):
    def test_ky_bao_cao(self):
        self.assertEqual(period.period("ngay", DAY)[:3], (DAY, DAY, "hôm nay"))
        week = period.period("tuan", DAY)
        self.assertEqual((week[0], week[1], week[3]), (date(2026, 10, 19), DAY, date(2026, 10, 12)))
        month = period.period("thang", DAY)
        self.assertEqual((month[0], month[1], month[2], month[3], month[4]),
                         (date(2026, 10, 1), DAY, "tháng 10/2026", date(2026, 9, 1), date(2026, 9, 20)))
        last = period.period("thangtruoc", DAY)
        self.assertEqual((last[0], last[1], last[2]), (date(2026, 9, 1), date(2026, 9, 30), "tháng 9/2026"))
        self.assertEqual(period.period("12", DAY)[0], date(2025, 12, 1))  # tháng chưa tới thì là năm trước
        self.assertEqual(period.full_month(2026, 10, DAY)[1], DAY)  # tháng đang chạy: tới hôm nay

    def test_loai_thu_nhap(self):
        for note, kind in (("lương tháng 10", "💼 Lương"), ("thưởng tết", "🎁 Thưởng"), ("lãi bán FPT", "📈 Đầu tư"),
                           ("freelance web", "🧑‍💻 Làm thêm"), ("quà", "💰 Khác"), ("", "💰 Khác")):
            self.assertEqual(income.income_kind(note), kind, note)
        got = income.income_kinds([{"ghichu": "lương", "tien": 10}, {"ghichu": "thưởng", "tien": 30}, {"ghichu": "lương", "tien": 5}])
        self.assertEqual(got, [("🎁 Thưởng", 30), ("💼 Lương", 15)])

    def test_chu_tien_va_ma_khoan(self):
        self.assertEqual([chitieu_text.short(x) for x in (-1_500_000, 999_800, 35_000, 500, 0)], ["−1,5tr", "1tr", "35k", "500đ", "0đ"])
        self.assertEqual(refs.ref({"ngay": "2026-10-05", "id": 7}), "2026-10:7")
        self.assertEqual(refs.button_ref("nhom:2026-10:7:an"), "2026-10:7")
        self.assertIsNone(refs.button_ref("bc:ngay"))


class DichVu(unittest.TestCase):
    def setUp(self):
        h.reset()
        h.at(2026, 10, 20, 10)
        self.now = h.CLOCK["now"]
        real_ai = ai_client.chat
        self.addCleanup(lambda: setattr(ai_client, "chat", real_ai))
        ai_client.chat = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("bận"))
        ledger.add("cà phê 35k\ngrab 80k\nbim bim 20k\nxyz lạ 15k", self.now)
        ledger.add("lương 25tr", self.now)

    def test_tien_do_ngan_sach(self):
        self.assertEqual(budget.progress(["an"], DAY), [])  # chưa đặt ngân sách
        budget_repo_save = kho.put
        budget_repo_save(keys.BUDGET, {"an": 100_000, "tong": 1_000_000, "xe": 50_000})
        self.assertEqual(budget.progress(["an", "khac"], DAY), [("an", 55_000, 100_000), ("tong", 150_000, 1_000_000)])
        self.assertEqual(budget.progress(["xe"], DAY)[0], ("xe", 80_000, 50_000))
        self.assertEqual([p[0] for p in budget.all_progress(DAY)], ["an", "xe", "tong"])  # ngân sách tổng đi kèm cuối
        self.assertEqual(budget_repo.load()["tong"], 1_000_000)

    def test_dong_ngan_sach(self):
        lines = view.budget_lines([("an", 55_000, 100_000), ("xe", 80_000, 50_000), ("tong", 90_000, 100_000)], CFG)
        self.assertEqual(lines[0], "🟢 🍜 Ăn uống: 55k/100k (55%)")
        self.assertEqual(lines[1], "🔴 🛵 Đi lại: 80k/50k (160% · vượt 30k)")
        self.assertTrue(lines[2].startswith("🟡 Tổng chi"))  # 90%
        self.assertEqual(view.budget_label("hangngay", CFG), "Chi hằng ngày")

    def test_bao_cao_ky(self):
        data = report.report_data("thang", DAY)
        self.assertEqual(len(data["items"]), 5)
        self.assertEqual(data["prev_total"], 0)
        text, count = view.report_text(data, CFG)
        self.assertEqual(count, 4)
        self.assertIn("📊 <b>Chi tiêu tháng 10/2026</b> (01/10 – 20/10)", text)
        self.assertIn("💸 Chi <b>150.000đ</b> · 4 khoản", text)
        self.assertIn("💰 Thu 25tr → 🟢 còn <b>24,85tr</b>", text)
        self.assertIn("❓ 1 khoản chưa rõ nhóm: /chuaxep", text)
        empty, n = view.report_text(report.report_data("ngay", date(2026, 1, 5)), CFG)
        self.assertEqual(n, 0)
        self.assertIn("Chưa có khoản nào", empty)

    def test_tin_bao_khoan_vua_ghi(self):
        entries = ledger.recent(DAY, 5)
        one, rows = view.entries_message(entries[:1], DAY, CFG, [])
        self.assertTrue(one.startswith("✅ Đã ghi "))
        self.assertIn("doi:", str([b for r in rows for b in r]))
        many, _ = view.entries_message(entries[:3], DAY, CFG, ["🟢 ngân sách"])
        self.assertIn("✅ Đã ghi 3 khoản", many)
        self.assertIn("🟢 ngân sách", many)
        self.assertEqual(view.entries_message([], DAY, CFG, []), ("🗑 Đã xóa", None))
        unsorted = [e for e in entries if e["nhom"] == "khac"]
        text, rows = view.entries_message(unsorted, DAY, CFG, [])
        self.assertIn("❓ «xyz lạ» thuộc nhóm nào?", text)
        self.assertIn("📦 Để ở Khác", str(rows))
        sorting, _ = view.entries_message(unsorted, DAY, CFG, [], sorting=True)
        self.assertTrue(sorting.startswith(view.SORT_TITLE))

    def test_nut_chon_nhom(self):
        reference = "2026-10:3"
        rows = view.picker(reference, CFG)
        flat = [b for r in rows for b in r]
        self.assertIn((view.classify.name("an", CFG), "nhom:2026-10:3:an"), flat)
        self.assertEqual(rows[-1], [("↩️ Thôi", "giu:2026-10:3"), ("❌ Xóa", "xoa:2026-10:3")])
        replaced = view.with_picker([[("a", "doi:2026-10:3"), ("b", "xoa:2026-10:3")], [("c", "x")]], reference, CFG)
        self.assertIn(("c", "x"), [b for r in replaced for b in r])  # nút của khoản khác giữ nguyên
        self.assertEqual(view.with_picker([[("c", "x")]], "2026-10:9", CFG)[-1], [("c", "x")])  # không có: nút chọn nhóm đặt lên đầu
        self.assertEqual(view.REPORT_BUTTONS[0][0], ("Hôm nay", "bc:ngay"))
        self.assertIn(view.BACK, view.CHI_BUTTONS[-1])


if __name__ == "__main__":
    unittest.main()
