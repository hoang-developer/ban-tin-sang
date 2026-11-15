"""Hiểu tin nhắn: việc bán/rút/thu về, một câu nhiều việc, trả lời thẳng câu hỏi tài chính, bộ đo danhgia."""
import unittest

from tests import harness as h
from tests.test_dongtien import item, main_balance, set_main

import danhgia
from infrastructure import kho
import taisan as ts


def ask(sentence, reply):
    h.AI.replies[sentence] = reply
    return h.say(sentence)


class ViecMoi(unittest.TestCase):
    def setUp(self):
        h.reset()
        set_main(10_000_000)

    def test_ban_vang_lay_lo_cu_truoc_tien_ve_tai_khoan(self):
        h.say("/taisan vang nhan 0,1 chi 148,02 20/10\n/taisan vang nhan 0,2 chi 123,84 11/11")
        text, buttons = ask("bán 0,2 chỉ nhẫn được 2tr7", {"viec": "ban_vang", "chi": 0.2, "tien": 2700000})
        self.assertIn("Bán 0,2 chỉ vàng, nhận 2.700.000đ", text)
        self.assertIn("Về VCB", text)
        _, done, _ = h.press(h.button(buttons, "y:ok:"))
        self.assertIn("Bán 0,2 chỉ vàng = 2.700.000đ", done)
        gold = kho.get("vivang")
        self.assertEqual([round(g["luong"] * 10, 2) for g in gold], [0.1])  # lô 20/10 (0,1) bán hết, lô 11/11 còn 0,1
        self.assertEqual(gold[0]["gia"], 123.84)
        self.assertEqual(main_balance(), 12_700_000)

    def test_tat_toan_so_tinh_goc_cong_lai(self):
        h.say("/taisan tietkiem TCB 50tr 5% 6 thang 13/05/2026")
        text, buttons = ask("tất toán sổ TCB", {"viec": "tat_toan", "ten": "TCB"})
        self.assertIn("Nhận về bao nhiêu?", text)
        _, card, buttons = h.press("y:bo:tien")
        self.assertIn("Tất toán sổ TCB (gốc + lãi tới hôm nay)", card)
        _, done, _ = h.press(h.button(buttons, "y:ok:"))
        self.assertIn("gốc 50.000.000đ → nhận 51.260.274đ (lãi 1.260.274đ)", done)
        self.assertFalse(any(it["loai"] == "tietkiem" for it in ts.load()["items"]))
        self.assertEqual(main_balance(), 10_000_000 + 51_260_274)
        self.assertTrue(any("lãi tiết kiệm TCB" in e["ghichu"] for e in h.month_entries()))

    def test_ban_quy_va_thu_no_va_xoa(self):
        h.say("/taisan quy VMEEF 100 15000")
        _, buttons = ask("bán 30 ccq VMEEF được 450k", {"viec": "ban_quy", "ma": "VMEEF", "ccq": 30, "tien": 450000})
        _, done, _ = h.press(h.button(buttons, "y:ok:"))
        self.assertIn("Bán 30 ccq VMEEF = 450.000đ", done)
        self.assertEqual(next(it for it in ts.load()["items"] if it.get("ma") == "VMEEF")["sl"], 70)
        _, buttons = ask("cho Hùng vay 2tr", {"viec": "cho_vay", "ten": "Hùng", "tien": 2000000})
        h.press(h.button(buttons, "y:ok:"))
        _, buttons = ask("Hùng trả 1tr", {"viec": "thu_no", "ten": "Hùng", "tien": 1000000})
        _, done, _ = h.press(h.button(buttons, "y:ok:"))
        self.assertIn("Cho Hùng vay: đã thu 1.000.000đ · còn 1.000.000đ", done)
        self.assertEqual(main_balance(), 10_000_000 + 450_000 - 2_000_000 + 1_000_000)
        h.say("/taisan tien MoMo 300k")
        _, buttons = ask("bỏ ví momo đi", {"viec": "xoa_tai_san", "ten": "MoMo"})
        _, done, _ = h.press(h.button(buttons, "y:ok:"))
        self.assertIn("Đã xóa MoMo", done)
        self.assertFalse(any(it.get("ten") == "MoMo" for it in ts.load()["items"]))


class NhieuViec(unittest.TestCase):
    def setUp(self):
        h.reset()
        set_main(10_000_000)
        h.say("/dautu batdau 4tr VMEEF")

    def test_mot_the_lam_ca_ba_viec(self):
        sentence = "nhận lương 19tr, chuyển 4tr vào quỹ chờ, ăn tối 200k"
        text, buttons = ask(sentence, {"viec": "nhieu", "ds": [
            {"viec": "thu", "tien": 19000000, "ghi_chu": "lương"},
            {"viec": "quy_cho", "tien": 4000000, "chieu": "nap"},
            {"viec": "chi", "tien": 200000, "ghi_chu": "ăn tối"}]})
        self.assertIn("1. 💰 Thu 19.000.000đ lương", text)
        self.assertIn("2. 📈 Để 4.000.000đ vào quỹ chờ đầu tư VMEEF", text)
        self.assertIn("3. 🧾 Chi 200.000đ ăn tối", text)
        _, done, _ = h.press(h.button(buttons, "y:ok:"))
        self.assertIn("Đã để 4.000.000đ vào quỹ chờ VMEEF", done)
        self.assertEqual(sorted(e["tien"] for e in h.month_entries()), [200_000, 19_000_000])
        self.assertEqual(main_balance(), 10_000_000 + 19_000_000 - 4_000_000 - 200_000)

    def test_viec_thieu_thong_tin_thi_hoi_roi_moi_ra_the(self):
        text, _ = ask("gửi tiết kiệm VCB 5tr và ăn tối 200k", {"viec": "nhieu", "ds": [
            {"viec": "tiet_kiem", "ten": "VCB", "tien": 5000000}, {"viec": "chi", "tien": 200000, "ghi_chu": "ăn tối"}]})
        self.assertIn("Lãi suất bao nhiêu", text)
        text, _ = h.say("4,7")
        self.assertIn("Kỳ hạn mấy tháng", text)
        text, buttons = h.say("6 tháng")
        self.assertIn("1. 🐷 Sổ tiết kiệm VCB: 5.000.000đ, lãi 4,7%/năm, kỳ hạn 6 tháng", text)
        self.assertIn("2. 🧾 Chi 200.000đ ăn tối", text)
        h.press(h.button(buttons, "y:ok:"))
        self.assertTrue(any(it["loai"] == "tietkiem" for it in ts.load()["items"]))
        self.assertEqual([e["tien"] for e in h.month_entries()], [200_000])


    def test_bo_viec_thua_sau_khi_rut_tien(self):
        import troly
        a = troly.clean({"viec": "nhieu", "ds": [{"viec": "tat_toan", "ten": "TCB"},
                                                  {"viec": "chuyen_tk", "den": "VCB"}]}, "sổ TCB đáo hạn, rút về VCB")
        self.assertEqual(a, {"viec": "tat_toan", "ten": "TCB"})
        a = troly.clean({"viec": "nhieu", "ds": [{"viec": "du_phong", "tien": 2000000, "chieu": "rut"},
                                                  {"viec": "chi", "tien": 2000000, "ghi_chu": "sửa xe"}]})
        self.assertEqual([j["viec"] for j in a["ds"]], ["du_phong", "chi"])  # rút ra rồi tiêu: giữ cả hai


class TraLoi(unittest.TestCase):
    def setUp(self):
        h.reset()
        set_main(10_000_000)

    def test_cau_hoi_tai_chinh_tra_loi_bang_so_lieu(self):
        sentence = "tôi còn nợ bao nhiêu"
        text, buttons = ask(sentence, {"viec": "tra_loi", "cau": "Bạn không còn khoản nợ nào.", "man": "no"})
        self.assertIn("💬 Bạn không còn khoản nợ nào.", text)
        self.assertIn("no:xem", buttons)
        system = h.AI.calls[-1][0]
        self.assertIn("SỐ LIỆU", system)  # câu hỏi: AI được xem số liệu bot tính sẵn
        self.assertIn("Tài khoản: VCB (chính) 10tr", system)
        self.assertIn("Nợ: không có", system)

    def test_cau_khong_phai_hoi_thi_khong_gui_so_lieu(self):
        ask("nạp 1tr vào quỹ dự phòng", {"viec": "du_phong", "tien": 1000000, "chieu": "nap"})
        self.assertNotIn("SỐ LIỆU", h.AI.calls[-1][0])


class BoDo(unittest.TestCase):
    def setUp(self):
        h.reset()

    def test_cham_diem(self):
        self.assertEqual(danhgia.plan("cà phê 35k"), [{"viec": "chi", "tien": 35000, "ngay": "2026-11-20"}])
        self.assertEqual(danhgia.plan("mua 100 FPT giá 95")[0]["gia"], 95000)
        self.assertTrue(danhgia.score([{"viec": "co_phieu", "gia": 95}], danhgia.plan("mua 100 FPT giá 95")))
        self.assertFalse(danhgia.score([{"viec": "chi"}], [{"viec": "chi"}, {"viec": "thu"}]))  # thừa việc: sai
        self.assertTrue(danhgia.score([{"viec": "tra_loi", "chua": ["271"]}],
                                      [{"viec": "tra_loi", "cau": "Bạn còn nợ 271,2tr."}]))
        h.AI.replies["tôi còn nợ bao nhiêu"] = {"viec": "tra_loi", "cau": "Bạn còn nợ 271,2tr", "man": "no"}
        self.assertTrue(danhgia.score([{"viec": "tra_loi", "chua": ["271"]}], danhgia.plan("tôi còn nợ bao nhiêu")))
        self.assertIn("Nợ còn 271,2tr", h.AI.calls[-1][0])  # đo bằng số liệu mẫu, không phải dữ liệu thật


if __name__ == "__main__":
    unittest.main()
