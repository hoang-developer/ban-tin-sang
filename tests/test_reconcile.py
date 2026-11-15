"""Đối chiếu tài sản tháng: luật thuần của domain, service qua kho giả, và dựng tin."""
import unittest
from datetime import date, datetime

from tests import harness as h
from tests.test_doichieu import setup
from tests.test_dongtien import item, main_balance

from domain.doichieu.reconcile import (DAY, GapBooked, ScreenState, SetResult, Slot, color, gap_of, has_pending_order,
                                       make_record, total_gap, unit_of)
from presentation.doichieu import reconcile as view
from repositories.doichieu import reconcile as reconcile_repo
from services.doichieu import reconcile as service


class Domain(unittest.TestCase):
    def test_don_vi(self):
        self.assertEqual(unit_of({"loai": "quy", "ma": "vmeef"}), "ccq")
        self.assertEqual(unit_of({"loai": "etf", "ma": "e1vfvn30"}), "ccq")
        self.assertEqual(unit_of({"loai": "cp", "ma": "fpt"}), "cp")
        self.assertEqual(unit_of({"loai": "coin", "ma": "btc"}), "BTC")
        self.assertEqual(unit_of({"loai": "ngoaite", "ma": "usd"}), "usd")

    def test_mau_nho_hon_la_tot_voi_tai_san_va_nguoc_lai_voi_no(self):
        self.assertEqual((color(500), color(-500)), ("🟢", "🔴"))
        self.assertEqual((color(500, debt=True), color(-500, debt=True)), ("🔴", "🟢"))

    def test_lech_tien_duoi_1000_coi_nhu_khop_con_so_luong_thi_chinh_xac(self):
        self.assertEqual(gap_of(30_000_500, 30_000_000, "đ"), 0)
        self.assertEqual(gap_of(30_001_000, 30_000_000, "đ"), 1_000)
        self.assertAlmostEqual(gap_of(100.0001, 100, "cp"), 0.0001)  # số lượng: lệch nhỏ vẫn giữ
        self.assertEqual(gap_of(29_500_000, 30_000_000, "đ"), -500_000)

    def test_ban_ghi(self):
        rec = make_record({"loai": "tien", "ten": "VCB"}, 30_000_000, 29_500_000, "đ", -500_000)
        self.assertEqual(rec, {"ten": "VCB", "bot": 30_000_000, "that": 29_500_000, "lech": -500_000, "don_vi": "đ"})
        debt = make_record({"loai": "no", "ten": "bác Vân"}, 10, 8, "đ", -2)
        self.assertTrue(debt["no"])
        qty = make_record({"loai": "cp", "ma": "fpt"}, 100, 120.123456, "cp", 20.123456)
        self.assertEqual((qty["lech"], qty["ten"]), (20.1235, "fpt"))  # số lượng làm tròn 4 chữ số

    def test_tong_lech_chi_tinh_tien_khong_tinh_no_va_so_luong(self):
        done = {"1": {"lech": -500, "don_vi": "đ"}, "2": {"lech": 200, "don_vi": "đ"},
                "3": {"lech": 99, "don_vi": "đ", "no": True}, "4": {"lech": 5, "don_vi": "cp"}}
        self.assertEqual(total_gap(done), -300)

    def test_lenh_cho_khop(self):
        cfg = {"ma": "VMEEF", "lenh": [{"trang_thai": "cho", "quy": "VFF"}, {"loai": "doi", "trang_thai": "chuyen", "quy": "VFF"}]}
        self.assertTrue(has_pending_order({"loai": "quy", "ma": "VFF"}, cfg))  # lệnh mua VFF chờ khớp
        self.assertTrue(has_pending_order({"loai": "quy", "ma": "VMEEF"}, cfg))  # hoán đổi đang chuyển sang VMEEF
        self.assertFalse(has_pending_order({"loai": "quy", "ma": "OTHER"}, cfg))
        self.assertFalse(has_pending_order({"loai": "tien", "ma": "VFF"}, cfg))  # chỉ quỹ mở
        self.assertFalse(has_pending_order({"loai": "quy", "ma": "VFF"}, {}))


class Service(unittest.TestCase):
    def setUp(self):
        setup()
        h.at(2026, 11, 15, 10)

    def now(self):
        return h.CLOCK["now"]

    def test_liet_ke_ngan(self):
        slots = service.items(date(2026, 11, 15))
        self.assertEqual([(s.item["ten"], s.value, s.unit) for s in slots],
                         [("VCB", 30_000_000, "đ"), ("MoMo", 2_000_000, "đ"), ("TCB", 50_000_000, "đ"), ("bác Vân", 10_000_000, "đ")])

    def test_khop_roi_lech_roi_ngan_khong_con(self):
        vcb = item("VCB")["id"]
        self.assertEqual(service.set_value(vcb, 30_000_500, self.now()).status, "khop")  # lệch dưới 1.000đ
        lech = service.set_value(vcb, 29_500_000, self.now())
        self.assertEqual((lech.status, lech.gap, lech.unit), ("lech", 29_500_000 - 30_000_500, "đ"))  # bot tính từ số vừa chốt 30.000.500
        self.assertEqual(main_balance(), 29_500_000)
        self.assertEqual(service.set_value(999, 1, self.now()).status, "khong_con")

    def test_so_luong_khong_am(self):
        h.say("/taisan cp FPT 100 95")
        fpt = item("FPT")["id"]
        self.assertEqual(service.set_value(fpt, -1, self.now()).status, "so_am")
        ok = service.set_value(fpt, 120, self.now())
        self.assertEqual((ok.status, ok.gap, ok.unit), ("lech", 20, "cp"))
        self.assertEqual(item("FPT")["sl"], 120)

    def test_danh_dau_khop(self):
        self.assertFalse(service.mark_ok(999, date(2026, 11, 15)))
        self.assertTrue(service.mark_ok(item("MoMo")["id"], date(2026, 11, 15)))
        self.assertEqual(len(service.remaining(date(2026, 11, 15))), 3)
        self.assertEqual(service.all_ok(date(2026, 11, 15)), 3)
        self.assertEqual(service.remaining(date(2026, 11, 15)), [])

    def test_ghi_khoan_lech_mot_lan(self):
        vcb = item("VCB")["id"]
        service.set_value(vcb, 29_500_000, self.now())
        self.assertEqual(service.book_gap(vcb, self.now()), GapBooked("ok", -500_000))
        self.assertEqual(service.book_gap(vcb, self.now()), GapBooked("da_xu_ly"))
        self.assertEqual(service.book_gap(12345, self.now()), GapBooked("da_xu_ly"))
        self.assertTrue(reconcile_repo.load_month("2026-11")["muc"][str(vcb)]["ghi"])

    def test_nhac_va_viec_can_lam(self):
        self.assertIsNone(service.todo_count(date(2026, 11, 14)))
        self.assertEqual(service.todo_count(date(2026, 11, 15)), 4)
        self.assertIsNone(service.morning_count(date(2026, 11, 14)))
        self.assertEqual(service.morning_count(date(2026, 11, 15)), 4)
        self.assertIsNone(service.morning_count(date(2026, 11, 15)))  # mỗi tháng nhắc một lần
        service.all_ok(date(2026, 11, 15))
        self.assertIsNone(service.todo_count(date(2026, 11, 20)))  # xong rồi


class Presentation(unittest.TestCase):
    def setUp(self):
        h.reset()

    def test_man_hinh_trong(self):
        text, rows = view.screen_view(date(2026, 11, 15), ScreenState([], {}))
        self.assertIn("Chưa có tài sản nào để đối chiếu", text)
        self.assertEqual(rows[0][0], ("➕ Thêm", "y:them"))

    def test_ket_qua_ghi_so_thuc(self):
        vcb = {"id": 7, "loai": "tien", "ten": "VCB", "chinh": True}
        self.assertEqual(view.set_value_view(SetResult("khong_con"))[0], "Ngăn này không còn trong tài sản")
        self.assertEqual(view.set_value_view(SetResult("so_am"))[0], "Số lượng không âm nhé")
        text, rows = view.set_value_view(SetResult("lech", vcb, 30_000_000, 29_500_000, "đ", -500_000))
        self.assertIn("🔴 VCB (chính): bot 30tr → thật 29,5tr · lệch −500k", text)
        self.assertEqual(rows[0][0], ("🧾 Ghi 500k là chi chưa ghi", "dc:ghi:7"))
        text, rows = view.set_value_view(SetResult("khop", vcb, 30_000_000, 30_000_000, "đ"))
        self.assertTrue(text.endswith("· khớp"))
        self.assertEqual(rows, [[("🔄 Tiếp tục đối chiếu", "dc:xem")]])

    def test_dong_khoan_lech_va_nhac(self):
        self.assertEqual(view.gap_booked_text(GapBooked("da_xu_ly")), "Khoản lệch này đã xử lý rồi")
        self.assertIn("khoản thu chưa ghi", view.gap_booked_text(GapBooked("ok", 200_000)))
        text, buttons = view.morning_view(date(2026, 11, 15), 4)
        self.assertIn("đối chiếu tài sản tháng 11: 4 ngăn", text)
        self.assertEqual(buttons, [[("🔄 Bắt đầu đối chiếu", "dc:xem")]])
        self.assertEqual(view.todo_view(date(2026, 11, 20), 2), ("🔄 Đối chiếu tài sản tháng 11: còn 2 ngăn", ("🔄 Đối chiếu", "dc:xem")))
        self.assertEqual(DAY, 15)


if __name__ == "__main__":
    unittest.main()
