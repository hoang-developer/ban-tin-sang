"""Đọc ảnh hóa đơn: chuẩn hóa giao dịch AI đọc, nhận ra chuyển nội bộ, ghi sổ, danh sách chọn, các lời nhắn."""
import unittest
from datetime import date, datetime

from tests import harness as h

from domain.docanh import receipt
from presentation.docanh import view
from repositories.docanh import receipts as repo
from services.docanh import receipts


def raw(tien, **kw):
    return {"so_tien": tien, "chieu": "chi", "noi_dung": "cà phê", "noi_ban": "Quán", "diem": 0, "nhom": "an", **kw}


class Luat(unittest.TestCase):
    def test_so_tien(self):
        self.assertEqual([receipt.money_of(x) for x in (29000, 29000.6, -5, "29.000đ", "-4,390,000", None, "abc")],
                         [29000, 29001, 0, 29000, 4390000, 0, 0])

    def test_chuan_hoa_giao_dich(self):
        txs = receipt.transactions({"giao_dich": [
            raw(35000), raw(0), "x", raw("1.000.000", chieu="thu", kieu="chi_tieu"), raw(50000, kieu="thu_nhap"),
            raw(70000, kieu="lạ"), raw(80000, noi_dung="  Phin   Sữa  ", ngay="04/11/2026")]})
        self.assertEqual([(t["tien"], t["chieu"], t["kieu"]) for t in txs],
                         [(35000, "chi", "chi_tieu"), (1000000, "thu", "thu_nhap"), (50000, "chi", "chi_tieu"),
                          (70000, "chi", "chi_tieu"), (80000, "chi", "chi_tieu")])
        self.assertEqual(txs[-1]["noi_dung"], "phin sữa")  # chữ thường, gọn khoảng trắng
        old = receipt.transactions({"so_tien": 66000, "chieu": "chi", "noi_dung": "x"})  # kiểu cũ: khoản nằm ngoài cùng
        self.assertEqual(len(old), 1)
        self.assertEqual(receipt.transactions({"loai": "khac"}), [])
        self.assertEqual(len(receipt.transactions({"giao_dich": [raw(1)] * 30})), 20)

    def test_ten_chu_tai_khoan(self):
        self.assertEqual(receipt.person("Trần Thị Mai"), "tran thi mai")
        self.assertEqual(receipt.person("Highlands"), "")  # một chữ không phải tên người
        self.assertEqual(receipt.person("Cty 123 ABC"), "")
        txs = [{"noi_ban": "Trần Thị Mai", "kieu": "tra_the"}, {"noi_ban": "Lê Văn B", "kieu": "chi_tieu"}]
        self.assertEqual(receipt.owner_names(["a b"], txs), ["a b", "tran thi mai"])
        self.assertEqual(receipt.owner_names([f"n{i} x" for i in range(5)], txs)[-1], "tran thi mai")
        self.assertEqual(len(receipt.owner_names([f"n{i} x" for i in range(5)], txs)), 5)

    def test_chuyen_noi_bo(self):
        names = ["tran thi mai"]
        self.assertTrue(receipt.own_transfer({"noi_ban": "Trần Thị Mai", "noi_dung": "gì đó"}, names))
        self.assertTrue(receipt.own_transfer({"noi_ban": "", "noi_dung": "Trần Thị Mai chuyển tiền"}, names))
        self.assertFalse(receipt.own_transfer({"noi_ban": "Trần Thị Mai", "noi_dung": "lương tháng 10"}, names))
        self.assertFalse(receipt.own_transfer({"noi_ban": "Trần Thị Mai", "noi_dung": "x"}, []))
        txs = [{"kieu": "chi_tieu", "noi_ban": "Trần Thị Mai", "noi_dung": "x"}, {"kieu": "tra_no", "noi_ban": "Trần Thị Mai", "noi_dung": "x"}]
        receipt.mark_own_transfers(txs, names)
        self.assertEqual([t["kieu"] for t in txs], ["chuyen_noi_bo", "tra_no"])

    def test_ngay_tren_hoa_don(self):
        today = date(2026, 11, 13)
        self.assertEqual(receipt.receipt_date("04/11/2026", today), date(2026, 11, 4))
        self.assertEqual(receipt.receipt_date("04-11-2026", today), date(2026, 11, 4))
        for bad in ("abc", None, "30/12/2030", "01/01/2020", "31/02/2026"):
            self.assertEqual(receipt.receipt_date(bad, today), today, bad)

    def test_danh_sach_chon(self):
        txs = [{"ngay": "04/11/2026", "tien": 1, "chieu": "chi", "kieu": "chi_tieu"},
               {"ngay": "05/11/2026", "tien": 2, "chieu": "chi", "kieu": "tra_the"},
               {"ngay": "06/11/2026", "tien": 3, "chieu": "chi", "kieu": "chi_tieu"}]
        receipt.prepare_list(txs, date(2026, 11, 13), lambda ngay, tien, chieu: tien == 3)
        self.assertEqual([(t["ngay"], t["da_ghi"], t["chon"]) for t in txs],
                         [("2026-11-04", False, True), ("2026-11-05", False, False), ("2026-11-06", True, False)])


class DichVu(unittest.TestCase):
    def setUp(self):
        h.reset()

    def test_loi_nhac_ai_co_ten_chu_va_nhom(self):
        repo.save_owners(["tran thi mai"])
        text = receipts.prompt(repo.owners())
        self.assertIn("Chủ tài khoản tên: TRAN THI MAI.", text)
        self.assertIn("an (Ăn uống)", text)
        self.assertNotIn("thu (", text)  # nhóm thu nhập không để AI chọn
        self.assertNotIn("Chủ tài khoản tên", receipts.prompt())

    def test_ghi_nho_chu_tai_khoan(self):
        txs = [{"noi_ban": "Trần Thị Mai", "kieu": "tra_the", "noi_dung": "x"}]
        self.assertEqual(receipts.remember_owners(txs), ["tran thi mai"])
        self.assertEqual(repo.owners(), ["tran thi mai"])

    def test_ghi_khoan_va_chong_trung(self):
        now = datetime(2026, 11, 13, 14, 5, tzinfo=h.VN_TZ)
        tx = {"tien": 35000, "chieu": "chi", "ngay": "2026-11-13", "noi_dung": "cà phê", "noi_ban": "", "diem": 0, "nhom": "an",
              "kieu": "chi_tieu"}
        self.assertIsNone(repo.recorded("2026-11-13", 35000, "chi"))
        e = receipts.record_one(dict(tx), now)
        self.assertEqual((e["nhom"], e["gio"], e["anh"]), ("an", "14:05", True))
        self.assertEqual(repo.recorded("2026-11-13", 35000, "chi"), e["id"])
        thu = receipts.record([dict(tx, chieu="thu", tien=1000)], now)[0]
        self.assertEqual(thu["nhom"], "thu")
        learned = receipts.record_one(dict(tx, tien=1, noi_dung="xe buýt"), now, chosen="xe")
        self.assertEqual(learned["nhom"], "xe")
        self.assertEqual(repo.learned()["xe buýt"], "xe")

    def test_nhom_theo_ai_khi_tu_khoa_khong_nhan_ra(self):
        tx = {"tien": 50000, "chieu": "chi", "ngay": "2026-11-13", "noi_dung": "zzz lạ", "noi_ban": "", "nhom": "xe", "kieu": "chi_tieu"}
        e = receipts.entry_from(tx, {}, receipts.groups_repo.config())
        self.assertEqual((e["nhom"], e["ai"]), ("xe", True))


    def test_tra_no_dong_the_khong_nhan_nhom_ai_doan(self):
        cfg = receipts.groups_repo.config()
        for note, kieu in (("đóng thẻ tín dụng lpbank", "chi_tieu"), ("thanh toán nợ vay", "tra_no"), ("thanh toán shopeepay", "chi_tieu")):
            tx = {"tien": 440000, "chieu": "chi", "ngay": "2026-11-04", "noi_dung": note, "noi_ban": "", "nhom": "nha", "kieu": kieu}
            e = receipts.entry_from(tx, {}, cfg)
            self.assertEqual(e["nhom"], "khac", note)  # chưa có nhóm Trả nợ: để ở Khác, không nhận "nhà cửa" của AI
            self.assertNotIn("ai", e)
        tx = {"tien": 50000, "chieu": "chi", "ngay": "2026-11-04", "noi_dung": "zzz lạ", "noi_ban": "", "nhom": "xe", "kieu": "chi_tieu"}
        self.assertTrue(receipts.entry_from(tx, {}, cfg)["ai"])  # khoản lạ khác vẫn nhận nhóm AI đoán


class ManHinh(unittest.TestCase):
    def test_danh_sach(self):
        txs = [{"chieu": "chi", "noi_dung": "cà phê", "noi_ban": "", "ngay": "2026-11-13", "tien": 35000, "chon": True, "kieu": "chi_tieu"},
               {"chieu": "thu", "noi_dung": "", "noi_ban": "Cty", "ngay": "2026-11-05", "tien": 19000000, "chon": True, "kieu": "thu_nhap"},
               {"chieu": "chi", "noi_dung": "", "noi_ban": "", "ngay": "2026-11-13", "tien": 5000000, "chon": False, "kieu": "tra_the"},
               {"chieu": "chi", "noi_dung": "x", "noi_ban": "", "ngay": "2026-11-13", "tien": 1000, "chon": False, "kieu": "chi_tieu", "da_ghi": True}]
        text, rows = view.render_list("u1", txs, date(2026, 11, 13))
        self.assertIn("📷 <b>Đọc được 4 giao dịch</b>", text)
        self.assertIn("✅ 1. <b>−35.000đ</b> cà phê", text)
        self.assertIn("✅ 2. <b>+19.000.000đ</b> Cty · 05/11", text)
        self.assertIn("⏭ 3. <b>−5.000.000đ</b> không rõ nội dung <i>(trả thẻ tín dụng", text)
        self.assertIn("<i>(đã ghi trước đó)</i>", text)
        self.assertIn("Sẽ ghi: thu 19.000.000đ · chi 35.000đ", text)
        self.assertEqual(rows[0], [("✅ 1", "anh:chon:u1:0"), ("✅ 2", "anh:chon:u1:1"), ("⏭ 3", "anh:chon:u1:2"), ("⏭ 4", "anh:chon:u1:3")])
        self.assertEqual(rows[-1], [("✅ Ghi 2 khoản", "anh:ghi:u1"), ("❌ Bỏ", "anh:bo:u1")])
        _, none_rows = view.render_list("u2", [dict(txs[2])], date(2026, 11, 13))
        self.assertEqual(none_rows[-1], [("❌ Bỏ", "anh:bo:u2")])

    def test_trung(self):
        self.assertEqual(view.duplicate({"chieu": "thu", "tien": 2000, "ngay": "2026-11-05"}),
                         "📷 Giao dịch +2.000đ ngày 05/11 đã ghi trước đó. Xem lại: /lichsu")


class LuongAnh(unittest.TestCase):
    def setUp(self):
        h.reset()
        h.at(2026, 11, 13, 14)

    def test_hoa_don_ghi_luon_va_nut_diem(self):
        h.AI.photo = {"loai": "hoa_don", "giao_dich": [raw(29000, noi_dung="phin sữa đá", noi_ban="Highlands", diem=9000, ngay="04/11/2026")]}
        text, buttons = h.send_photo()
        self.assertIn("📷 Đọc từ ảnh · Highlands", text)
        self.assertIn("anh:diem:9000", buttons)
        toast, _, buttons = h.press("anh:diem:9000", text="x")
        self.assertEqual(toast, "Đã ghi 9.000đ vào Thu nhập")

    def test_danh_sach_chon_va_ghi(self):
        h.AI.photo = {"loai": "danh_sach", "giao_dich": [raw(35000, ngay="13/11/2026"), raw(5_000_000, kieu="tra_the", ngay="13/11/2026")]}
        text, buttons = h.send_photo()
        self.assertIn("Đọc được 2 giao dịch", text)
        unique = buttons[0].split(":")[2]
        self.assertEqual(h.press(f"anh:chon:{unique}:9")[0], None)
        toast, body, _ = h.press(f"anh:ghi:{unique}")
        self.assertEqual(toast, "Đã ghi 1 khoản")
        self.assertEqual(h.press(f"anh:ghi:{unique}")[0], "Danh sách này đã hết hạn hoặc đã ghi, gửi lại ảnh nhé")

    def test_anh_khong_dung_duoc(self):
        h.AI.photo = {"loai": "khac", "giao_dich": []}
        self.assertEqual(h.send_photo()[0], view.NOTHING_FOUND)
        h.AI.photo = None
        self.assertEqual(h.send_photo()[0], view.UNREADABLE)


if __name__ == "__main__":
    unittest.main()
