"""Kế hoạch tài chính: luật thuần (dự kiến chi, mức nạp quỹ, mỗi ngày được tiêu, việc còn lại, lộ trình), service, dựng tin."""
import unittest
from datetime import date
from types import SimpleNamespace as NS

from tests import harness as h
from tests.test_dongtien import set_main

from domain.kehoach import plan as rules
from interface.kehoach import plan as kehoach_ui
from presentation.kehoach import plan as pview
from repositories.luong import salary as salary_repo
from domain.luong.salary import Salary
from services.kehoach import plan as service
from services.no import debt as debt_service

D = date


def debt(**kw):
    d = {"id": 1, "loai": "no", "ten": "chú Tư", "tien": 10_000_000, "thang": 2_000_000, "lai": 0, "tu": "2026-11"}
    d.update(kw)
    return d


class Domain(unittest.TestCase):
    def test_du_kien_chi_theo_ngan_sach_tong(self):
        self.assertEqual(rules.estimate_spend(15_000_000, 6_000_000, [], D(2026, 11, 10), None), (9_000_000, "ngân sách tổng"))
        self.assertEqual(rules.estimate_spend(5_000_000, 6_000_000, [], D(2026, 11, 10), None), (0, "ngân sách tổng"))

    def test_du_kien_chi_khong_co_so_chi(self):
        self.assertEqual(rules.estimate_spend(None, 0, [], D(2026, 11, 10), None), (0, None))
        self.assertEqual(rules.estimate_spend(None, 0, [], D(2026, 11, 10), 8_000_000), (8_000_000, "tự đặt"))

    def test_du_kien_chi_theo_trung_binh(self):
        few = [{"ngay": "2026-11-01", "tien": 300_000}]  # 10 ngày dữ liệu: chưa đủ 14 ngày
        self.assertEqual(rules.estimate_spend(None, 0, few, D(2026, 11, 10), None), (912_000.0, "TB 10 ngày"))
        self.assertEqual(rules.estimate_spend(None, 0, few, D(2026, 11, 10), 5_000_000), (5_000_000, "tự đặt"))
        many = [{"ngay": "2026-10-20", "tien": 2_200_000}]  # 22 ngày: đủ tin, bỏ qua mức tự đặt
        self.assertEqual(rules.estimate_spend(None, 0, many, D(2026, 11, 10), 5_000_000), (3_040_000.0, "TB 22 ngày"))

    def test_khoan_no_cua_thang(self):
        due, finished, paid_off = debt(), debt(id=2, tien=0), debt(id=3, tien=0, tra=[{"ngay": "2026-11-05", "tien": 1_500_000}])
        got = rules.month_debts([due, finished, paid_off], "2026-11")
        self.assertEqual([(d["id"], need, paid) for d, need, paid in got], [(1, 2_000_000, 0), (3, 1_500_000, 1_500_000)])

    def test_muc_nap_quy(self):
        fund = NS(monthly=10_000_000, missing=60_000_000, months_left=12)
        self.assertEqual(rules.fund_share(fund, 0, 0, 19_000_000, 6_000_000, 10_000_000), (5_000_000, 3_000_000))  # bị chặn bởi phần thu còn lại
        self.assertEqual(rules.fund_share(fund, 0, 7_000_000, None, 0, 0), (7_000_000, 7_000_000))  # nợ xong dư ra 7tr: nạp mức đó, chưa biết thu
        self.assertEqual(rules.fund_share(fund, 4_000_000, 0, 19_000_000, 6_000_000, 15_000_000), (5_300_000, 4_000_000))  # đã nạp 4tr: cơ sở 64tr/12 tháng; phần thu hết nên chỉ giữ số đã nạp, không tụt dưới đó
        self.assertEqual(rules.fund_share(NS(monthly=0, missing=5, months_left=1), 0, 0, 1, 1, 1), (0, 0))
        self.assertEqual(rules.fund_share(NS(monthly=1, missing=0, months_left=1), 0, 0, 1, 1, 1), (0, 0))
        self.assertEqual(rules.fund_share(NS(monthly=1, missing=100, months_left=12), 0, 0, None, 0, 0)[0], 100_000)  # tối thiểu 100k

    def test_phan_con_lai(self):
        self.assertIsNone(rules.leftover(0, 1, 1, 1, 1))
        self.assertEqual(rules.leftover(19_000_000, 6_000_000, 10_000_000, 3_000_000, 1_000_000), -1_000_000)

    def test_moi_ngay_duoc_tieu_theo_ke_hoach(self):
        s = rules.plan_spendable(19_000_000, 6_000_000, 3_000_000, 1_000_000, 2_000_000, 100_000, 500_000, 10)
        self.assertEqual((s["limit"], s["per_day"], s["today_left"], s["basis"]), (9_000_000, 600_000, 500_000, "plan"))
        self.assertEqual(s["parts"], [("thu", 19_000_000), ("trả nợ", 6_000_000), ("quỹ dự phòng", 3_000_000), ("đầu tư", 1_000_000)])

    def test_viec_con_lai(self):
        d = debt()
        n = {"ym": "2026-11", "debts": [(d, 2_000_000, 0)], "fund_left": 200_000, "invest_left": 50_000}
        self.assertEqual(rules.pending_steps(n), [("no", d, 2_000_000, 1), ("dp", None, 200_000, None)])  # đầu tư dưới 100k bỏ qua

    def test_viec_nen_lam_ngay(self):
        d = debt()
        n = {"ym": "2026-11", "debts": [(d, 2_000_000, 0)], "fund_left": 500_000, "fund_added": 0, "fund_target": 3_000_000,
             "fund": NS(monthly=0, days=5)}
        self.assertEqual(rules.urgent_items(n, True, 2), [("no", d, 2_000_000), ("dp", 500_000), ("ghi_chep", 5), ("chuaxep", 2)])
        self.assertEqual([x[0] for x in rules.urgent_items(n, False, 0)], ["no", "ghi_chep"])  # chưa có thu: chưa gợi ý nạp quỹ
        topped = dict(n, fund_added=3_000_000, fund_target=3_000_000, fund_left=500_000)  # đã nạp gần đủ
        self.assertNotIn("dp", [x[0] for x in rules.urgent_items(topped, True, 0)])

    def test_lo_trinh(self):
        bearing, zero = debt(id=1, lai=12.0), debt(id=2, lai=0)
        fund = NS(monthly=10, covered=2, missing=5)
        r = rules.roadmap_state(fund, 20, [bearing, zero], lambda d: (3, "2027-02"), {"tietkiem": 5})
        self.assertEqual((r.done, r.current, r.bearing, r.zero, r.bearing_last), ([True, True, False, False, False], 2, [bearing], [zero], "2027-02"))
        self.assertIsNone(rules.roadmap_state(fund, 20, [bearing], lambda d: None, {}).bearing_last)  # chưa tính được kỳ xong
        done = rules.roadmap_state(NS(monthly=10, covered=6, missing=0), 20, [zero], lambda d: None, {})
        self.assertEqual((done.done, done.current), ([True, True, True, True, False], 4))  # xong tới bước 4: đang ở bước đầu tư
        none = rules.roadmap_state(NS(monthly=0, covered=0, missing=0), 3, [], lambda d: None, {})
        self.assertEqual((none.done, none.current), ([False, False, True, False, False], 0))


class Service(unittest.TestCase):
    def setUp(self):
        h.reset()
        h.at(2026, 11, 10, 10)
        set_main(30_000_000)
        self.day = D(2026, 11, 10)

    def test_thu_nhap_du_kien_tu_ngay_luong(self):
        salary_repo.save(Salary(5, 19_000_000))
        n = service.numbers(self.day)
        self.assertEqual((n["income"], n["income_basis"], n["ym"]), (19_000_000, "lương dự kiến, chưa ghi", "2026-11"))

    def test_khong_co_thu_nhap_thi_khong_tinh_duoc_moi_ngay_duoc_tieu(self):
        self.assertIsNone(service.spendable_safe(self.day))

    def test_cac_khoan_no_trong_so_lieu(self):
        salary_repo.save(Salary(5, 19_000_000))
        debt_service.declare_info({"ten": "bác Vân", "con": 10_000_000, "thang": 2_000_000, "lai": 0, "nay": True}, self.day)
        n = service.numbers(self.day)
        self.assertEqual([(d["ten"], need, paid) for d, need, paid in n["debts"]], [("bác Vân", 2_000_000, 0)])
        self.assertEqual((n["debt_need"], n["debt_left"]), (2_000_000, 2_000_000))
        self.assertEqual([(k, d["ten"], amount) for k, d, amount, _ in service.steps(n) if k == "no"], [("no", "bác Vân", 2_000_000)])

    def test_lam_het_tra_no_va_khong_lam_hai_lan(self):
        salary_repo.save(Salary(5, 19_000_000))
        debt_service.declare_info({"ten": "bác Vân", "con": 10_000_000, "thang": 2_000_000, "lai": 0, "nay": True}, self.day)
        first = service.do_all(h.CLOCK["now"])
        self.assertTrue(all(r.ok for r in first.results))
        self.assertEqual(first.results[0].kind, "no")
        self.assertEqual(debt_service.active()[0]["tien"], 8_000_000)
        second = service.do_all(h.CLOCK["now"])
        self.assertTrue(second is None or "no" not in [r.kind for r in second.results])  # khoản nợ đã trả đủ kỳ này

    def test_khong_con_viec_thi_do_all_la_none(self):
        self.assertIsNone(service.do_all(h.CLOCK["now"]))


class Presentation(unittest.TestCase):
    def test_dau_tien_do(self):
        self.assertEqual((pview.mark(100, 100), pview.mark(97, 100), pview.mark(50, 100), pview.mark(0, 100), pview.mark(0, 0)),
                         ("✅", "🟡", "🟡", "⬜", "⬜"))  # đủ từ 98%

    def test_dong_moi_ngay_duoc_tieu(self):
        self.assertEqual(pview.room_text(0, 0), "🔴 Hết phần chi tiêu tháng này")
        self.assertEqual(pview.room_text(250_000, 180_000), "🟢 Hôm nay còn 180k · mức 250k/ngày")
        self.assertEqual(pview.room_text(250_000, -50_000, bold=True), "🔴 Hôm nay quá <b>50k</b> · mức 250k/ngày")
        tong = {"per_day": 250_000, "today_left": 1, "limit": 15_000_000, "basis": "tong", "parts": None}
        self.assertEqual(pview.basis_text(tong), "ngân sách tổng 15tr/tháng")
        plan = {"basis": "plan", "limit": 9_000_000, "parts": [("thu", 19_000_000), ("trả nợ", 6_000_000), ("đầu tư", 0)]}
        self.assertEqual(pview.basis_text(plan), "thu 19tr − trả nợ 6tr = 9tr chi tiêu/tháng")  # bỏ phần bằng 0

    def test_nhan_viec(self):
        d = debt(ten="một khoản nợ có cái tên rất là dài dòng")
        self.assertTrue(pview.step_label("no", d, None).startswith("Trả một khoản nợ có cái"))
        self.assertEqual(pview.step_label("dp", None, None), "Nạp quỹ dự phòng")
        self.assertEqual(pview.step_label("dt", None, "VMEEF"), "Để vào quỹ chờ VMEEF")

    def test_toi_da_ba_viec_va_mac_dinh(self):
        items = [("no", debt(), 2_000_000), ("dp", 500_000), ("ghi_chep", 5), ("chuaxep", 2)]
        lines = pview.next_action_lines(items)
        self.assertEqual(len(lines), 3)
        self.assertEqual(lines[0], "Trả chú Tư 2tr")
        self.assertEqual(pview.next_action_lines([]), ["Không có việc gấp 👌"])

    def test_tai_khoan_chinh_khong_du_tien(self):
        self.assertIn("🔴 không đủ", pview.main_note({"ten": "VCB"}, 1_000_000, 2_000_000))
        self.assertEqual(pview.main_note(None, 0, 0), "<i>Chưa chọn tài khoản chính: không trừ số dư tài khoản nào</i>")


class Giao_dien(unittest.TestCase):
    def test_steps_giu_dang_cu(self):
        d = debt()
        n = {"ym": "2026-11", "debts": [(d, 2_000_000, 0)], "fund_left": 200_000, "invest_left": 150_000,
             "invest": {"ma": "VMEEF"}}
        self.assertEqual(kehoach_ui.steps(n), [("no", "Trả chú Tư", 2_000_000, 1), ("dp", "Nạp quỹ dự phòng", 200_000, None),
                                               ("dt", "Để vào quỹ chờ VMEEF", 150_000, None)])


if __name__ == "__main__":
    unittest.main()
