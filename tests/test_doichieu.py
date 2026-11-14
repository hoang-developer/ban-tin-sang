"""Đối chiếu tài sản tháng: ngày 15 nhắc, so từng ngăn, ghi số thật, lưu khoản lệch."""
import unittest

from tests import harness as h
from tests.test_dongtien import item, main_balance, set_main

import doichieu
import sono
import taisan as ts
import thongbao


def setup():
    """VCB là tài khoản chính 30tr, MoMo 2tr, sổ TCB 50tr, nợ bác Vân 10tr."""
    h.reset()
    h.at(2026, 11, 10, 10)
    set_main(30_000_000)
    h.say("/taisan tien MoMo 2tr")
    h.say("/taisan tietkiem TCB 50tr 5% 6 thang 01/11/2026")
    sono.declare_info({"ten": "bác Vân", "con": 10_000_000, "thang": 2_000_000, "lai": 0}, h.CLOCK["now"].date())


class DoiChieu(unittest.TestCase):
    def setUp(self):
        setup()

    def test_ngay_15_nhac_trong_tin_sang_va_hom_nay(self):
        h.at(2026, 11, 14, 9, 5)
        self.assertIsNone(thongbao.morning(h.CLOCK["now"].date()))
        h.at(2026, 11, 15, 9, 5)
        text, buttons = h.parts(thongbao.morning(h.CLOCK["now"].date()))
        self.assertIn("Hôm nay đối chiếu tài sản tháng 11: 4 ngăn", text)
        self.assertIn("dc:xem", buttons)
        self.assertIsNone(thongbao.morning(h.CLOCK["now"].date()))  # mỗi tháng nhắc một lần
        _, home, buttons = h.press("m:home")
        self.assertIn("Đối chiếu tài sản tháng 11: còn 4 ngăn", home)

    def test_doi_chieu_tung_ngan_va_khoan_lech(self):
        h.at(2026, 11, 15, 10)
        h.say("cà phê 35k")  # tài khoản chính bot tính 29.965.000đ
        _, body, buttons = h.press("dc:xem")
        self.assertIn("⬜ VCB (chính): bot tính 29,96tr", body)
        self.assertIn("⬜ bác Vân 💳: bot tính 10tr", body)
        # VCB thật 29,5tr: lệch −465k, hỏi có ghi là chi chưa ghi không
        _, ask, _ = h.press(h.button(buttons, f"y:them:doi_chieu:{item('VCB')['id']}"))
        self.assertIn("VCB (chính) thật là bao nhiêu? (bot đang tính 29,96tr)", ask)
        text, buttons = h.say("29tr5")
        self.assertIn("🔴 VCB (chính): bot 29,96tr → thật 29,5tr · lệch −465k", text)
        self.assertEqual(main_balance(), 29_500_000)
        _, done, _ = h.press(h.button(buttons, "dc:ghi:"))
        self.assertIn("Đã ghi 465k là khoản chi chưa ghi", done)
        self.assertEqual(main_balance(), 29_500_000)  # không trừ số dư lần nữa
        gap = [e for e in h.month_entries() if "chưa ghi" in (e["ghichu"] or "")]
        self.assertEqual([e["tien"] for e in gap], [465_000])
        toast, _, _ = h.press("dc:ghi:" + str(item("VCB")["id"]))
        self.assertIn("đã xử lý", toast)  # bấm lại: không ghi hai lần
        # MoMo khớp, sổ TCB lệch +200k, phần còn lại khớp hết
        h.press(f"dc:ok:{item('MoMo')['id']}")
        h.press(f"y:them:doi_chieu:{item('TCB')['id']}")
        h.say("50tr2")
        self.assertEqual(item("TCB")["tien"], 50_200_000)
        _, body, _ = h.press("dc:het")
        self.assertIn("✅ bác Vân 💳: 10tr", body)
        self.assertEqual(doichieu.color(500_000, debt=True), "🔴")  # nợ thật nhiều hơn bot tính: xấu
        self.assertIn("🟢 +200k TCB: 50,2tr", body)
        self.assertIn("Σ lệch tiền: 🔴 −265k · 🎉 xong", body)
        _, home, _ = h.press("m:home")
        self.assertNotIn("Đối chiếu tài sản", home)  # xong rồi: không còn trong việc cần làm

    def test_quy_con_lenh_cho_khop_thi_chua_doi_chieu(self):
        h.at(2026, 9, 9, 15)
        h.say("/dautu batdau 4tr VMEEF")
        h.say("/dautu dadat 1tr 9/9")
        h.at(2026, 9, 10, 17, 30)
        h.run_jobs()  # khớp 64,69 ccq
        h.say("/dautu dadat 2tr")  # lệnh mới chờ khớp
        _, body, buttons = h.press("dc:xem")
        self.assertIn("⏳ VMEEF: 64,69 ccq · còn lệnh chờ khớp", body)
        hold = next(it for it in ts.load()["items"] if it["loai"] == "quy")
        self.assertNotIn(f"dc:ok:{hold['id']}", buttons)
        h.at(2026, 9, 14, 17, 30)  # đặt sau 14:40 thứ Năm 10/09: khớp phiên thứ Hai 14/09
        h.run_jobs()  # lệnh khớp: giờ đối chiếu được
        _, body, buttons = h.press("dc:xem")
        _, ask, _ = h.press(h.button(buttons, f"y:them:doi_chieu_sl:{hold['id']}"))
        self.assertIn("VMEEF thật là bao nhiêu?", ask)
        text, _ = h.say("193,5")
        self.assertIn("VMEEF: bot", text)
        self.assertEqual(next(it for it in ts.load()["items"] if it["loai"] == "quy")["sl"], 193.5)

    def test_khai_bao_lai_so_tiet_kiem_khong_tao_trung(self):
        h.say("/taisan tietkiem TCB 52tr 5,2% 6 thang 01/11/2026")
        books = [it for it in ts.load()["items"] if it["loai"] == "tietkiem"]
        self.assertEqual([(b["ten"], b["tien"], b["lai"]) for b in books], [("TCB", 52_000_000, 5.2)])


if __name__ == "__main__":
    unittest.main()
