"""Sổ nợ: luật thuần của domain (đọc câu khai báo, kỳ trả, khớp khoản trả, chấm sức khỏe), service qua kho giả, dựng tin."""
import unittest
from datetime import date

from tests import harness as h

import sochitieu as ct
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
        self.assertEqual(ct.find(ct.ref(r.entry))["ghichu"], "trả nợ bác Vân")
        self.assertEqual(service.by_id(None, d["id"])["tien"], 8_000_000)
        self.assertEqual(service.pay(99, 1, h.CLOCK["now"]).status, "het_hoac_xoa")

    def test_gan_roi_bo_tru(self):
        d = self.declare().debt
        e = {"id": ledger_repo.next_id(), "ngay": "2026-11-10", "gio": "10:00", "tien": 1_000_000, "ghichu": "x", "nhom": "khac"}
        ct.save(e)
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


if __name__ == "__main__":
    unittest.main()
