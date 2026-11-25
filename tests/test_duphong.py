"""Quỹ dự phòng: luật thuần của domain (không kho, không giờ giả) và service qua kho giả."""
import unittest
from datetime import date

from tests import harness as h

from domain.common.dates import add_months
from domain.duphong.reserve import MIN_DAYS, build_status, milestone, monthly_amounts, record_deposit
from repositories.duphong import reserve as reserve_repo
from services.duphong import reserve as service

DAY = date(2026, 11, 10)


def status(cfg=None, essential=(0, {}, 0), rows=(), flows=(0, 0, 0), day=DAY):
    return build_status(cfg or {}, day, essential, list(rows), flows)


class Domain(unittest.TestCase):
    def test_chi_tu_dat_tinh_muc_tieu_va_so_thang_con_lai(self):
        s = status({"chi": 12_000_000, "thang": 6, "bat_dau": "2026-11-10"}, rows=[("Quỹ dự phòng", 6_000_000)])
        self.assertEqual((s.monthly, s.target, s.missing, s.balance), (12_000_000, 72_000_000, 66_000_000, 6_000_000))
        self.assertEqual(s.covered, 0.5)
        self.assertEqual(s.deadline, date(2027, 11, 10))
        self.assertEqual((s.months_left, s.per_month, s.overdue, s.manual), (12, 5_500_000, False, True))

    def test_chua_du_ngay_ghi_chep_thi_chua_tinh_chi_thiet_yeu(self):
        self.assertEqual(status(essential=(9_000_000, {"an": 9_000_000}, MIN_DAYS - 1)).monthly, 0)
        s = status(essential=(9_000_000, {"an": 9_000_000}, MIN_DAYS))
        self.assertEqual((s.monthly, s.target, s.manual), (9_000_000, 54_000_000, False))

    def test_qua_han_va_du_quy(self):
        late = status({"chi": 10_000_000, "han": 6, "bat_dau": "2026-01-01"}, rows=[("x", 1_000_000)])
        self.assertTrue(late.overdue)
        self.assertEqual(late.months_left, 1)  # còn thiếu thì tối thiểu 1 tháng
        full = status({"chi": 10_000_000, "thang": 1}, rows=[("x", 10_000_000)])
        self.assertEqual((full.missing, full.per_month, full.overdue), (0, 0, False))

    def test_du_thu_chi_chi_tinh_khi_du_20_ngay(self):
        self.assertIsNone(status(flows=(5, 9, 19)).surplus)
        self.assertEqual(status(flows=(5, 9, 20)).surplus, 4)
        self.assertIsNone(status(flows=(5, 0, 30)).surplus)  # không có thu: không tính

    def test_chi_theo_ky_khong_nhan_theo_ngay(self):
        totals = {"an": 150_000, "nha": 5_000_000, "tra_no": 5_000_000}
        got = monthly_amounts(totals, {"nha", "tra_no"}, 15)  # 15 ngày dữ liệu: nhà, nợ đã trả đúng một lần
        self.assertEqual((got["nha"], got["tra_no"]), (5_000_000, 5_000_000))
        self.assertAlmostEqual(got["an"], 150_000 * 30.4 / 15)  # ăn uống thì quy theo ngày
        got = monthly_amounts(totals, {"nha", "tra_no"}, 90)  # 90 ngày = 3 tháng: chia 3
        self.assertAlmostEqual(got["nha"], 5_000_000 / 3)
        self.assertEqual(monthly_amounts({"nha": 7_000_000}, {"nha"}, 45)["nha"], 7_000_000)  # 45 ngày vẫn là 1 tháng
        # hai lần trả ở hai tháng lịch khác nhau thì là hai tháng dù 45 ngày chỉ làm tròn thành 1
        self.assertEqual(monthly_amounts({"nha": 10_000_000}, {"nha"}, 45, {"nha": 2})["nha"], 5_000_000)
        self.assertEqual(monthly_amounts({"nha": 15_000_000}, {"nha"}, 90, {"nha": 1})["nha"], 5_000_000)  # trả theo quý
        self.assertEqual(monthly_amounts({"nha": 5_000_000}, {"nha"}, 26, {"nha": 1})["nha"], 5_000_000)  # cửa sổ 20/10 tới 14/11
        self.assertEqual(monthly_amounts({"nha": 7_000_000}, {"nha"}, 60)["nha"], 3_500_000)

    def test_moc_vua_vuot(self):
        two = {"chi": 10, "thang": 6}
        mk = lambda covered: status(two, rows=[("x", covered * 10)])  # noqa: E731
        self.assertEqual(milestone(mk(0.5), mk(1.2)), "đủ 1 tháng chi")
        self.assertEqual(milestone(mk(2.9), mk(3.1)), "đủ 3 tháng chi")
        self.assertEqual(milestone(mk(5.9), mk(6.0)), "ĐẠT MỤC TIÊU")
        self.assertIsNone(milestone(mk(1.2), mk(1.5)))  # không vượt mốc mới
        self.assertIsNone(milestone(status(), status(rows=[("x", 5)])))  # chưa có chi thiết yếu

    def test_ghi_nhan_nap_va_rut(self):
        cfg = record_deposit({}, DAY, 2_000_000)
        self.assertEqual(cfg, {"bat_dau": "2026-11-10", "nap": {"2026-11": 2_000_000}})
        cfg = record_deposit(cfg, date(2026, 11, 20), 1_000_000)
        self.assertEqual(cfg["nap"], {"2026-11": 3_000_000})
        # rút thì số đã nạp của tháng giảm theo (lỗi cũ: nạp 2,6tr rồi rút 2tr vẫn ghi "đã nạp 2,6tr")
        self.assertEqual(record_deposit(cfg, DAY, -500_000)["nap"], {"2026-11": 2_500_000})
        self.assertEqual(record_deposit(cfg, DAY, -9_000_000)["nap"], {"2026-11": 0})  # không xuống dưới 0
        self.assertEqual(record_deposit({"nap": {}}, DAY, -1_000_000)["nap"], {"2026-11": 0})  # tháng chưa nạp gì
        many = {"nap": {f"2025-{m:02d}": 1 for m in range(1, 13)}, "bat_dau": "2025-01-01"}
        kept = record_deposit(many, DAY, 5)["nap"]
        self.assertEqual((len(kept), "2025-01" in kept, kept["2026-11"]), (12, False, 5))  # chỉ giữ 12 tháng gần nhất
        self.assertEqual(len(many["nap"]), 12)  # cấu hình gốc không bị sửa

    def test_cong_thang(self):
        self.assertEqual(add_months(date(2026, 1, 31), 1), date(2026, 2, 28))
        self.assertEqual(add_months(date(2026, 11, 10), 14), date(2028, 1, 10))


class Service(unittest.TestCase):
    def setUp(self):
        h.reset()
        h.at(2026, 11, 10, 10)

    def test_nap_cong_so_da_nap_va_bao_moc(self):
        service.set_monthly(10_000_000)
        c = service.change(12_000_000, DAY, from_main=False)
        self.assertEqual((c.before.balance, c.after.balance, c.milestone), (0, 12_000_000, "đủ 1 tháng chi"))
        self.assertEqual(reserve_repo.deposited_in("2026-11"), 12_000_000)
        r = service.change(-11_000_000, DAY, from_main=False)
        self.assertEqual((r.after.balance, r.milestone), (1_000_000, None))
        self.assertEqual(reserve_repo.deposited_in("2026-11"), 1_000_000)  # rút 11tr thì đã nạp trong tháng còn 1tr

    def test_rut_qua_so_du_chi_tru_phan_that_da_rut(self):
        service.change(2_000_000, DAY, from_main=False)
        service.change(-5_000_000, DAY, from_main=False)  # quỹ chỉ có 2tr: chỉ rút được 2tr
        self.assertEqual((service.status(DAY).balance, reserve_repo.deposited_in("2026-11")), (0, 0))

    def test_tien_nha_hai_thang_khong_nhan_doi(self):
        """Lỗi cũ: 45 ngày dữ liệu có hai lần trả nhà 5tr (01/10, 01/11) thì tiền nhà thành 10tr/tháng, mục tiêu quỹ +62%."""
        h.at(2026, 10, 1, 9)
        h.say("tiền nhà 5tr")
        for d in range(1, 15):
            h.at(2026, 11, d, 9)
            if d == 1:
                h.say("tiền nhà 5tr")
            h.say("ăn trưa 100k")
        h.at(2026, 11, 14, 10)
        _, by_group, days = service.essential(date(2026, 11, 14))
        self.assertEqual(days, 45)
        self.assertEqual(round(by_group["nha"]), 5_000_000)  # đúng 5tr/tháng

    def test_tinh_tai_san_vao_quy(self):
        h.say("/taisan tietkiem TCB 50tr 5% 6 thang 01/11/2026")
        t = service.toggle("tcb")
        self.assertEqual((t.found, t.label, t.enabled), (True, "TCB", True))
        self.assertEqual(service.toggle("TCB").enabled, False)
        miss = service.toggle("không có")
        self.assertEqual((miss.found, miss.available), (False, ["TCB"]))
        self.assertEqual(service.savings_books(), [("TCB", 5, False)])

    def test_chi_thiet_yeu_it_ngay_khong_nhan_doi_tien_nha(self):
        for day, text in ((3, "tiền nhà 5tr"), (3, "tiền điện 5tr"), (10, "phở 40k"), (10, "đi chợ 300k")):
            h.at(2026, 11, day, 10)
            h.say(text)
        h.at(2026, 11, 18, 9)
        total, by_group, days = service.essential(h.CLOCK["now"].date())
        self.assertEqual(days, 16)
        self.assertEqual(by_group["nha"], 10_000_000)  # tiền nhà và tiền điện cùng nhóm: đúng 10tr, không nhân đôi
        self.assertAlmostEqual(by_group["cho"], 300_000 * 30.4 / 16)
        self.assertAlmostEqual(total, sum(by_group.values()))

    def test_tien_tra_no_khong_tinh_vao_chi_thiet_yeu(self):
        from services.chitieu import groups
        h.at(2026, 11, 3, 10)
        groups.nhom_them("Trả nợ: trả nợ, trả góp")
        groups.reset()
        debt = groups.find_group("trả nợ")
        self.assertTrue(debt)
        for text in ("trả góp tủ lạnh 5tr", "tiền nhà 5tr", "phở 40k"):
            h.say(text)
        h.at(2026, 11, 18, 9)
        total, by_group, _ = service.essential(h.CLOCK["now"].date())
        self.assertNotIn(debt, by_group)
        self.assertNotIn(debt, service.essential_groups())
        self.assertEqual(by_group["nha"], 5_000_000)
        self.assertAlmostEqual(total, 5_000_000 + 40_000 * 30.4 / 16)

    def test_hoa_don_the_va_no_vay_khong_tinh_du_nam_o_nha_cua(self):
        from repositories.chitieu import ledger as ledger_repo
        h.at(2026, 11, 5, 10)
        h.say("tiền nhà 5tr")
        for ngay, tien, note in (("2026-11-05", 4_390_000, "thanh toán nợ vay"), ("2026-11-04", 440_000, "đóng thẻ tín dụng lpbank"),
                                 ("2026-11-06", 386_310, "thanh toán shopeepay")):
            ledger_repo.save({"id": ledger_repo.next_id(), "ngay": ngay, "tien": tien, "ghichu": note, "nhom": "nha", "ai": True})
        h.at(2026, 11, 18, 9)
        _, by_group, _ = service.essential(h.CLOCK["now"].date())
        self.assertEqual(by_group["nha"], 5_000_000)  # chỉ còn tiền nhà thật

    def test_cai_dat(self):
        service.set_months(9)
        service.set_deadline(18, DAY)
        service.set_monthly(8_000_000)
        self.assertEqual(reserve_repo.load(), {"thang": 9, "han": 18, "bat_dau": "2026-11-10", "chi": 8_000_000})
        service.clear_monthly()
        self.assertNotIn("chi", reserve_repo.load())


class KhamSucKhoe(unittest.TestCase):
    def test_nhan_xet_ai_chi_cho_toi_da_15_giay(self):
        from tests.test_dongtien import setup_month
        from infrastructure import ai as ai_client
        from interface.taisan import assets
        h.reset()
        setup_month()
        calls = []
        real = ai_client.chat
        self.addCleanup(lambda: setattr(ai_client, "chat", real))
        ai_client.chat = lambda system, user, **kw: (calls.append(kw), ("• nhận xét một\n✅ việc nên làm", "m"))[1]
        text = assets.health(h.CLOCK["now"].date())
        self.assertEqual(calls[0]["budget"], 15)  # Vercel cắt hàm ở 60 giây: AI không được chiếm hết
        self.assertLessEqual(calls[0]["timeout"], 12)
        self.assertIn("🩺 <b>Sức khỏe tài chính", text)
        self.assertIn("💡 <b>Việc nên làm</b>", text)
        ai_client.chat = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("bận"))
        self.assertIn("🩺 <b>Sức khỏe tài chính", assets.health(h.CLOCK["now"].date()))  # AI lỗi vẫn có bảng chấm điểm


if __name__ == "__main__":
    unittest.main()
