"""Sổ nợ: luật thuần của domain (đọc câu khai báo, kỳ trả, khớp khoản trả, chấm sức khỏe), service qua kho giả, dựng tin."""
import unittest
from datetime import date

from tests import harness as h

from domain.chitieu.refs import ref
from interface.chitieu import context as chitieu_ctx
from repositories.chitieu import ledger as ledger_repo
from domain.no import debt as rules
from domain.no.debt import DebtHealth, DeclareResult, Payment
from presentation.no import debt as pview
from repositories.chitieu import ledger as ledger_repo
from services.no import debt as service

D = date


def debt(**kw):
    d = {"id": 1, "loai": "no", "ten": "chú Tư", "tien": 10_000_000, "thang": 2_000_000, "lai": 0, "tu": "2026-11"}
    d.update(kw)
    return d


class DocCau(unittest.TestCase):
    def test_no_nguoi_than_da_tra_mot_phan(self):
        info = rules.parse_debt("chú Tư 300tr đã trả 32tr, trả 5tr/tháng, không lãi")
        self.assertEqual((info["ten"], info["con"], info["goc"], info["thang"], info["lai"]),
                         ("chú Tư", 268_000_000, 300_000_000, 5_000_000, 0.0))

    def test_tra_gop_co_lai_va_ngay_han(self):
        info = rules.parse_debt("thẻ tín dụng trả góp 8,2tr, trả 4,39tr/tháng, lãi 12%, ngày 5")
        self.assertEqual((info["ten"], info["con"], info["thang"], info["ngay_tra"], info["lai"]),
                         ("thẻ tín dụng trả góp", 8_200_000, 4_390_000, 5, 12.0))

    def test_lai_theo_thang_doi_ra_nam_va_thang_nay_chua_tra(self):
        self.assertEqual(rules.parse_debt("anh Nam 5tr lãi 1%/tháng")["lai"], 12.0)
        self.assertTrue(rules.parse_debt("bác Vân 10tr, mỗi tháng trả 2tr, tháng này chưa trả")["nay"])

    def test_chia_deu_theo_so_ky_va_bo_chu_no_dau_cau(self):
        info = rules.parse_debt("nợ xe máy còn 24tr 12 kỳ")
        self.assertEqual((info["ten"], info["con"], info["thang"]), ("xe máy", 24_000_000, 2_000_000))


class KyTra(unittest.TestCase):
    def test_con_phai_tra_trong_thang(self):
        d = debt()
        self.assertEqual(rules.month_left(d, "2026-11"), 2_000_000)
        self.assertEqual(rules.month_left(d, "2026-10"), 0)  # chưa tới kỳ đầu
        paid = debt(tien=8_000_000, tra=[{"ngay": "2026-11-10", "tien": 2_000_000, "ref": "r"}])
        self.assertEqual(rules.month_left(paid, "2026-11"), 0)
        near = debt(tien=8_030_000, tra=[{"ngay": "2026-11-10", "tien": 1_970_000, "ref": "r"}])
        self.assertEqual(rules.month_left(near, "2026-11"), 0)  # thiếu dưới 2% coi như đủ

    def test_lich_tra_xong(self):
        self.assertEqual(rules.schedule(debt(tu="2026-12"), D(2026, 11, 10)), (5, "2027-04"))
        self.assertEqual(rules.schedule(debt(), D(2026, 11, 10)), (5, "2027-03"))
        paid = debt(tien=8_000_000, tra=[{"ngay": "2026-11-10", "tien": 2_000_000, "ref": "r"}])
        self.assertEqual(rules.schedule(paid, D(2026, 11, 10)), (4, "2027-03"))  # tháng này đủ: kỳ kế là tháng sau
        self.assertIsNone(rules.schedule(debt(thang=None), D(2026, 11, 10)))
        self.assertIsNone(rules.schedule(debt(tien=0), D(2026, 11, 10)))

    def test_han_tra(self):
        self.assertEqual(rules.pay_day(debt(ngay_tra=31), D(2026, 2, 10)), 28)  # hạn ngày 31, tháng 2 chỉ 28 ngày
        self.assertEqual(rules.pay_day(debt(), D(2026, 11, 10), salary_day=5), 7)  # 2 ngày sau ngày lương
        self.assertEqual(rules.pay_day(debt(), D(2026, 11, 10)), 10)

    def test_tong_hop_theo_danh_sach(self):
        items = [debt(), debt(id=2, ten="đã xong", tien=0, thang=3_000_000, xong="2026-10-20"), {"loai": "tien", "ten": "VCB"}]
        self.assertEqual([d["id"] for d in rules.debts_of(items)], [1, 2])
        self.assertEqual([d["id"] for d in rules.active_of(items)], [1])
        self.assertEqual(rules.due_now(items, D(2026, 11, 10)), [(items[0], 2_000_000)])
        self.assertEqual(rules.monthly_total(items), 2_000_000)
        self.assertEqual(rules.freed(items, "2026-11"), (3_000_000, ["đã xong"]))
        self.assertEqual(rules.freed(items, "2026-10"), (0, []))  # xong trong tháng 10 thì tháng 10 chưa dư ra
        self.assertEqual(rules.month_progress(items, D(2026, 11, 10)), (0, 2_000_000))

    def test_tra_roi_bo_tra(self):
        d = debt(tien=3_000_000)
        e = {"ngay": "2026-11-10", "tien": 3_000_000}
        p = rules.apply_payment(d, e, "2026-11:7", D(2026, 11, 10))
        self.assertEqual((p.finished, p.left, p.monthly, d["tien"], d["xong"]), (True, 0, 2_000_000, 0, "2026-11-10"))
        rules.undo_payment(d, e, "2026-11:7")
        self.assertEqual((d["tien"], d["tra"], "xong" in d), (3_000_000, [], False))
        part = rules.apply_payment(debt(), {"ngay": "2026-11-10", "tien": 2_000_000}, "r", D(2026, 11, 10))
        self.assertEqual((part.finished, part.left, part.schedule), (False, 8_000_000, (4, "2027-03")))


class Khop(unittest.TestCase):
    def setUp(self):
        self.tu = debt(thang=5_000_000)
        self.the = debt(id=2, ten="thẻ tín dụng", thang=4_390_000)
        self.items = [self.tu, self.the]

    def test_ten_trong_ghi_chu(self):
        e = {"nhom": "tra_no", "ghichu": "trả nợ chú Tư", "tien": 1}
        self.assertIs(rules.match(e, self.items, "tra_no", "khac"), self.tu)

    def test_khong_thuoc_nhom_tra_no_thi_can_chu_tra_hoac_gop(self):
        self.assertIsNone(rules.match({"nhom": "an", "ghichu": "chú Tư", "tien": 5_000_000}, self.items, "tra_no", "khac"))

    def test_nhom_khac_so_them_so_tien_voi_muc_tra(self):
        e = {"nhom": "khac", "ghichu": "trả góp tháng 11", "tien": 4_390_000}
        self.assertIs(rules.match(e, self.items, "tra_no", "khac"), self.the)
        far = {"nhom": "khac", "ghichu": "trả góp tháng 11", "tien": 3_000_000}
        self.assertIsNone(rules.match(far, self.items, "tra_no", "khac"))

    def test_khop_ngang_nhau_thi_khong_doan(self):
        a, b = debt(id=3, ten="anh Nam"), debt(id=4, ten="anh Hùng")
        self.assertIsNone(rules.match({"nhom": "tra_no", "ghichu": "trả anh", "tien": 1}, [a, b], "tra_no", "khac"))

    def test_tim_theo_chu_trong_lenh(self):
        self.assertIs(rules.find_by_name_words(self.items, "chu tu 5tr"), self.tu)
        self.assertIsNone(rules.find_by_name_words(self.items, "xyz 5tr"))


class SucKhoe(unittest.TestCase):
    def test_khong_no(self):
        self.assertTrue(rules.debt_health([], 100, None, D(2026, 11, 10), [], lambda d: 10).none)

    def test_cham_theo_thu_nhap(self):
        items = [debt()]
        r = rules.debt_health(items, 100_000_000, 20_000_000, D(2026, 11, 10), [], lambda d: 10)
        self.assertEqual((r.basis, r.share, r.score, r.mark), ("thu", 10.0, 20, "✅"))
        self.assertTrue(r.has_zero and not r.has_bearing)

    def test_cham_theo_tai_san_khi_chua_biet_thu_nhap_va_tru_diem_khi_tre_han(self):
        items = [debt(lai=12.0, tien=40_000_000)]
        due = rules.due_now(items, D(2026, 11, 20))
        r = rules.debt_health(items, 100_000_000, None, D(2026, 11, 20), due, lambda d: 10)
        self.assertEqual((r.basis, r.ratio, r.late), ("tai_san", 40.0, ["chú Tư"]))
        self.assertEqual((r.score, r.mark), (3, "⚠️"))  # 8 điểm, trễ hạn 5 ngày trở lên trừ 5
        self.assertEqual(r.bearing_last, "2026-11"[:0] + rules.schedule(items[0], D(2026, 11, 20))[1])


class Service(unittest.TestCase):
    def setUp(self):
        h.reset()
        h.at(2026, 11, 10, 10)
        self.day = D(2026, 11, 10)

    def declare(self, **extra):
        return service.declare_info({"ten": "bác Vân", "con": 10_000_000, "thang": 2_000_000, "lai": 0, **extra}, self.day)

    def test_them_roi_sua_cung_ten_khong_tao_trung(self):
        r = self.declare()
        self.assertEqual((r.status, r.created, r.debt["tien"], r.debt["tu"]), ("ok", True, 10_000_000, "2026-12"))
        r2 = service.declare_info({"ten": "Bác Vân", "thang": 3_000_000}, self.day)
        self.assertEqual((r2.created, r2.debt["thang"], r2.debt["tu"], r2.debt["id"]), (False, 3_000_000, "2026-12", r.debt["id"]))
        self.assertEqual(len(service.debts()), 1)
        self.assertEqual(self.declare(nay=True).debt["tu"], "2026-11")  # "tháng này chưa trả": kỳ đầu là tháng này

    def test_khoan_moi_thieu_so_con_no(self):
        r = service.declare_info({"ten": "abc"}, self.day)
        self.assertEqual((r.status, r.name), ("thieu_con", "abc"))
        self.assertEqual(service.debts(), [])
        self.assertIsNone(service.declare("   ", self.day))

    def test_tra_no_ghi_khoan_chi_va_tru_du_no(self):
        d = self.declare(nay=True).debt
        r = service.pay(d["id"], 2_000_000, h.CLOCK["now"])
        self.assertEqual((r.status, r.payment.left, r.entry["no"], r.entry["tien"]), ("ok", 8_000_000, d["id"], 2_000_000))
        self.assertEqual(chitieu_ctx.find(ref(r.entry))["ghichu"], "trả nợ bác Vân")
        self.assertEqual(service.by_id(None, d["id"])["tien"], 8_000_000)
        self.assertEqual(service.pay(99, 1, h.CLOCK["now"]).status, "het_hoac_xoa")

    def test_gan_roi_bo_tru(self):
        d = self.declare().debt
        e = {"id": ledger_repo.next_id(), "ngay": "2026-11-10", "gio": "10:00", "tien": 1_000_000, "ghichu": "x", "nhom": "khac"}
        ledger_repo.save(e)
        payment = service.assign(e, d["id"], self.day)
        self.assertEqual((payment.left, e["no"]), (9_000_000, d["id"]))
        self.assertIsNone(service.assign(e, d["id"], self.day))  # đã trừ rồi
        back = service.unassign(e)
        self.assertEqual((back["tien"], "no" in e), (10_000_000, False))
        self.assertIsNone(service.assign(e, 99, self.day))  # khoản nợ không còn

    def test_nhac_toi_da_hai_lan_moi_thang(self):
        self.declare(nay=True, ngay_tra=10)
        self.assertEqual(service.reminders(D(2026, 11, 9)), [])  # chưa tới hạn
        first = service.reminders(D(2026, 11, 10))
        self.assertEqual([(d["ten"], left) for d, left in first], [("bác Vân", 2_000_000)])
        self.assertEqual(service.reminders(D(2026, 11, 11)), [])  # đã nhắc giai đoạn 1
        self.assertEqual(len(service.reminders(D(2026, 11, 15))), 1)  # 5 ngày sau hạn: nhắc lần 2
        self.assertEqual(service.reminders(D(2026, 11, 20)), [])

    def test_xoa_khoan_no(self):
        d = self.declare().debt
        self.assertTrue(service.remove(d["id"]))
        self.assertFalse(service.remove(d["id"]))


class Presentation(unittest.TestCase):
    def test_dong_bao_tra(self):
        done = pview.payment_lines(Payment("chú Tư", True, 0, 2_000_000, None))
        self.assertEqual(done[0], "🎉 Đã trả xong nợ chú Tư!")
        self.assertIn("dư ra 2tr", done[1])
        part = pview.payment_lines(Payment("chú <Tư>", False, 8_000_000, 2_000_000, (4, "2027-03")))
        self.assertEqual(part, ["💳 Đã trừ vào nợ chú &lt;Tư&gt;: còn 8tr · còn 4 tháng, xong khoảng 03/2027"])
        self.assertEqual(len(pview.payment_lines(Payment("x", True, 0, None, None))), 1)  # không có mức trả: không gợi ý dư ra

    def test_thieu_so_con_no_va_ten_rut_gon(self):
        text = pview.declare_text(DeclareResult("thieu_con", name="abc"), D(2026, 11, 10))
        self.assertIn("Chưa có khoản nợ «abc»", text)
        self.assertEqual(pview.short_name({"ten": "một cái tên rất rất dài"}, 10), "một cái t…")

    def test_dong_suc_khoe(self):
        self.assertEqual(pview.health_line(DebtHealth(none=True)), (20, "✅", "Nợ: không có"))
        score, mark, line = pview.health_line(DebtHealth(basis="thu", monthly=2_000_000, share=10, score=20, mark="✅",
                                                         has_zero=True, zero_total=10_000_000, late=["a<b"]))
        self.assertEqual((score, mark), (20, "✅"))
        self.assertEqual(line, "Nợ: trả 2tr/tháng = 10% thu (nên < 30%) · nợ không lãi 10tr · ⬜ tháng này: a&lt;b")


def loan(**kw):
    """Vay 100tr lãi 12%/năm, khai báo 25/11/2026, trả 10tr/tháng từ tháng 12."""
    d = {"id": 1, "loai": "no", "ten": "vay ngân hàng", "tien": 100_000_000, "goc": 100_000_000, "thang": 10_000_000,
         "lai": 12.0, "ngay": "2026-11-25", "ngay_lai": "2026-11-25", "tu": "2026-12"}
    d.update(kw)
    return d


class LaiGiamDan(unittest.TestCase):
    """Lỗi cũ: nợ có lãi bị trừ như nợ không lãi (100tr, 12%, trả 10tr: còn 90tr, 10 kỳ; đúng ≈ 91tr, 11 kỳ)."""

    def test_lai_don_theo_ngay_tren_du_no_giam_dan(self):
        d = loan()
        self.assertEqual(round(rules.accrued_interest(d, D(2026, 12, 25))), 986_301)  # 100tr × 12% × 30/365
        self.assertEqual(rules.accrued_interest(d, D(2026, 11, 25)), 0)  # cùng ngày khai báo
        self.assertEqual(rules.accrued_interest(d, D(2026, 11, 1)), 0)  # trước mốc: không âm
        self.assertEqual(rules.accrued_interest(loan(lai=0), D(2026, 12, 25)), 0)  # không lãi
        self.assertEqual(rules.accrued_interest(loan(lai=None), D(2026, 12, 25)), 0)  # chưa rõ lãi: không tự đoán

    def test_so_ky_con_lai_theo_cong_thuc_tra_gop(self):
        n, last = rules.schedule(loan(), D(2026, 11, 25))
        self.assertEqual((n, last), (11, "2027-10"))  # trước đây bot báo 10 kỳ, xong 09/2027
        self.assertEqual(rules.schedule(loan(lai=0), D(2026, 11, 25)), (10, "2027-09"))  # nợ không lãi giữ nguyên
        self.assertEqual(rules.schedule(loan(lai=None), D(2026, 11, 25)), (10, "2027-09"))  # chưa rõ lãi: như không lãi

    def test_muc_tra_khong_du_lai_thi_no_khong_bao_gio_het(self):
        d = loan(thang=900_000)  # lãi một tháng 1tr > 900k
        self.assertTrue(rules.interest_only(d))
        self.assertIsNone(rules.schedule(d, D(2026, 11, 25)))
        self.assertFalse(rules.interest_only(loan()))
        self.assertTrue(rules.interest_only(loan(thang=1_000_000)))  # trả đúng bằng lãi tháng: dư nợ đứng yên, không bao giờ hết
        self.assertFalse(rules.interest_only(loan(thang=1_100_000)))
        self.assertFalse(rules.interest_only(loan(lai=0, thang=1)))

    def test_tra_truoc_lai_roi_toi_goc(self):
        d = loan()
        pay = rules.apply_payment(d, {"ngay": "2026-12-25", "tien": 10_000_000}, "r1", D(2026, 12, 25))
        self.assertEqual((d["tien"], pay.interest, pay.principal, pay.left), (90_986_301, 986_301 // 1, 9_013_699, 90_986_301))
        self.assertEqual(pay.schedule, (10, "2027-10"))
        self.assertEqual(d["ngay_lai"], "2026-12-25")  # lần sau dồn lãi từ đây
        self.assertEqual((d["tra"][-1]["lai"], d["tra"][-1]["goc"]), (986_301, 9_013_699))

    def test_tra_khong_du_lai_thi_lai_chua_tra_cong_vao_du_no(self):
        d = loan(thang=500_000)
        pay = rules.apply_payment(d, {"ngay": "2026-12-25", "tien": 500_000}, "r1", D(2026, 12, 25))
        self.assertEqual((pay.interest, pay.principal), (500_000, 0))
        self.assertEqual(d["tien"], 100_486_301)  # 986k lãi - 500k đã trả = 486k nợ thêm
        self.assertTrue(pay.interest_only)

    def test_tra_het_va_tra_du(self):
        d = loan(tien=5_000_000)
        pay = rules.apply_payment(d, {"ngay": "2026-12-25", "tien": 6_000_000}, "r1", D(2026, 12, 25))
        self.assertEqual((d["tien"], pay.finished, pay.extra), (0, True, 6_000_000 - 5_000_000 - 49_315))  # lãi 30 ngày 49.315
        self.assertEqual(d["xong"], "2026-12-25")

    def test_hoan_tac_khoan_tra_tra_lai_dung_du_no_va_moc_lai(self):
        d = loan()
        e = {"ngay": "2026-12-25", "tien": 10_000_000}
        rules.apply_payment(d, e, "r1", D(2026, 12, 25))
        rules.undo_payment(d, e, "r1")
        self.assertEqual((d["tien"], d["ngay_lai"], d["tra"]), (100_000_000, "2026-11-25", []))
        small = loan(thang=500_000)
        e = {"ngay": "2026-12-25", "tien": 500_000}
        rules.apply_payment(small, e, "r2", D(2026, 12, 25))  # trả không đủ lãi: dư nợ tăng
        rules.undo_payment(small, e, "r2")
        self.assertEqual(small["tien"], 100_000_000)

    def test_khoan_no_cu_chua_co_moc_lai_lay_ngay_tra_gan_nhat(self):
        d = loan(ngay_lai=None, tra=[{"ngay": "2026-12-10", "tien": 1, "ref": "x"}])
        d.pop("ngay_lai")
        self.assertEqual(rules.accrual_start(d), D(2026, 12, 10))
        d["tra"] = []
        self.assertEqual(rules.accrual_start(d), D(2026, 11, 25))  # chưa trả lần nào: ngày khai báo dư nợ
        self.assertIsNone(rules.accrual_start({"tien": 1}))

    def test_no_khong_lai_khong_doi(self):
        d = loan(lai=0)
        pay = rules.apply_payment(d, {"ngay": "2026-12-25", "tien": 10_000_000}, "r1", D(2026, 12, 25))
        self.assertEqual((d["tien"], pay.interest, pay.principal), (90_000_000, 0, None))
        self.assertEqual(d["tra"][-1], {"ngay": "2026-12-25", "tien": 10_000_000, "ref": "r1"})  # không thêm trường lạ
        self.assertEqual(d["ngay_lai"], "2026-11-25")  # nợ không lãi không dồn lãi, không đổi mốc

    def test_khai_bao_dat_moc_dan_lai(self):
        d = {"id": 1, "loai": "no", "ten": "x", "tien": 0}
        info = {"con": 50_000_000, "goc": None, "thang": 5_000_000, "lai": 12.0, "ngay_tra": None, "nay": False}
        rules.apply_info(d, info, D(2026, 11, 25), True)
        self.assertEqual((d["ngay"], d["ngay_lai"]), ("2026-11-25", "2026-11-25"))
        free = {"id": 2, "loai": "no", "ten": "y", "tien": 0}
        rules.apply_info(free, {**info, "lai": 0}, D(2026, 11, 25), True)
        self.assertNotIn("ngay_lai", free)  # nợ không lãi: dữ liệu như cũ
        rules.apply_info(free, {"con": None, "goc": None, "thang": None, "lai": 12.0, "ngay_tra": None, "nay": False},
                         D(2026, 12, 1), False)
        self.assertEqual(free["ngay_lai"], "2026-12-01")  # chuyển sang nợ có lãi: dồn lãi từ ngày đó
        rules.apply_info(free, {"con": None, "goc": None, "thang": 6_000_000, "lai": None, "ngay_tra": None, "nay": False},
                         D(2026, 12, 20), False)
        self.assertEqual(free["ngay_lai"], "2026-12-01")  # chỉ đổi mức trả: không dời mốc


class TrenBotNoCoLai(unittest.TestCase):
    def setUp(self):
        h.reset()
        h.at(2026, 11, 25, 10)

    def test_kich_ban_100tr_lai_12_tra_10tr(self):
        text, _ = h.say("/no vay ngân hàng 100tr, trả 10tr/tháng, lãi 12%")
        self.assertIn("10tr/tháng · xong ~10/2027 (11 tháng)", text)  # trước đây: xong ~09/2027 (10 tháng)
        h.at(2026, 12, 25, 10)
        text, _ = h.record("trả nợ vay ngân hàng 10tr")
        self.assertIn("còn 90,99tr · lần này gồm lãi 986k, gốc 9,01tr · còn 10 tháng, xong khoảng 10/2027", text)
        self.assertIn("còn 90,99tr · lãi 12%/năm", h.say("/no")[0])

    def test_xoa_khoan_tra_hoan_lai_du_no(self):
        h.say("/no vay ngân hàng 100tr, trả 10tr/tháng, lãi 12%")
        h.at(2026, 12, 25, 10)
        h.say("trả nợ vay ngân hàng 10tr")
        text, _ = h.say("/xoa")
        self.assertIn("còn 100tr", h.say("/no")[0])

    def test_muc_tra_khong_du_lai_co_canh_bao(self):
        text, _ = h.say("/no vay ngân hàng 100tr, trả 500k/tháng, lãi 12%")
        self.assertIn("chưa đủ trả lãi", text)
        self.assertIn("nợ sẽ không giảm", text)
        self.assertNotIn("xong ~", text)

    def test_tra_du_co_canh_bao(self):
        h.say("/no Hùng 5tr, trả 5tr/tháng, lãi 12%")
        text, _ = h.record("trả nợ Hùng 6tr")
        self.assertIn("Đã trả xong nợ Hùng", text)
        self.assertIn("Bạn trả dư", text)

    def test_no_khong_lai_nhu_cu(self):
        text, _ = h.say("/no chú Tư 100tr, trả 10tr/tháng, không lãi")
        self.assertIn("10tr/tháng · xong ~09/2027 (10 tháng)", text)
        h.at(2026, 12, 25, 10)
        text, _ = h.record("trả nợ chú Tư 10tr")
        self.assertIn("còn 90tr · còn 9 tháng", text)
        self.assertNotIn("lần này gồm lãi", text)


class VayMoiCoTien(unittest.TestCase):
    """Lỗi cũ: vay mới 10tr chỉ ghi sổ nợ, tiền vay không vào tài khoản nên tài sản ròng giảm 10tr."""

    def setUp(self):
        h.reset()
        h.at(2026, 11, 20, 10)

    def test_the_vay_moi_hoi_tien_vao_tai_khoan_chinh(self):
        from tests.test_dongtien import main_balance, net, set_main
        set_main(50_000_000)
        h.AI.replies["vay anh Nam 10tr"] = {"viec": "no_moi", "ten": "anh Nam", "tien": 10_000_000, "lai": 0}
        _, buttons = h.say("vay anh Nam 10tr")
        _, _, buttons = h.press(h.button(buttons, "y:bo:moi_thang"))
        _, done, buttons = h.press(h.button(buttons, "y:ok:"))
        self.assertIn("tiền đã về VCB, bấm nút dưới để cộng 10tr", done)
        self.assertEqual((net(), main_balance()), (40_000_000, 50_000_000))  # khai báo nợ một mình: tài sản ròng giảm
        button = h.button(buttons, "no:vao:")
        toast, _, _ = h.press(button)
        self.assertEqual(toast, "🏦 VCB +10tr → ~60tr")
        self.assertEqual((net(), main_balance()), (50_000_000, 60_000_000))  # tiền vay vào: tài sản ròng như cũ
        self.assertEqual(h.press(button)[0], "Đã cộng tiền vay vào tài khoản rồi")  # chỉ một lần
        self.assertEqual(main_balance(), 60_000_000)

    def test_lenh_no_cung_hoi_va_khai_bao_no_cu_thi_khong_bam(self):
        from tests.test_dongtien import main_balance, net, set_main
        set_main(50_000_000)
        text, buttons = h.say("/no chú Tư 5tr, trả 1tr/tháng, không lãi")
        self.assertIn("bấm nút dưới để cộng 5tr", text)
        self.assertTrue(any(b.startswith("no:vao:") for b in buttons))
        self.assertEqual(net(), 45_000_000)
        text, buttons = h.say("/no chú Tư trả 2tr/tháng")  # cập nhật khoản đã có: không hỏi tiền vay nữa
        self.assertNotIn("bấm nút dưới", text)
        self.assertFalse(any(b.startswith("no:vao:") for b in buttons))
        self.assertEqual(main_balance(), 50_000_000)  # không bấm thì không cộng gì

    def test_chua_co_tai_khoan_chinh_thi_khong_hoi(self):
        text, buttons = h.say("/no chú Tư 5tr, trả 1tr/tháng, không lãi")
        self.assertNotIn("bấm nút dưới", text)
        self.assertFalse(any(b.startswith("no:vao:") for b in buttons))

    def test_khoan_no_da_xoa_thi_nut_het_tac_dung(self):
        from tests.test_dongtien import main_balance, set_main
        set_main(50_000_000)
        _, buttons = h.say("/no chú Tư 5tr, trả 1tr/tháng, không lãi")
        button = h.button(buttons, "no:vao:")
        debt_id = button.split(":")[2]
        h.press(f"no:x:{debt_id}")
        self.assertEqual(h.press(button)[0], "Khoản nợ này đã xóa")
        self.assertEqual(main_balance(), 50_000_000)


if __name__ == "__main__":
    unittest.main()
