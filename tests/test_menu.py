"""Giai đoạn 3: 4 mục chính (Hôm nay · Tiền của tôi · Kế hoạch · Hỏi) và thông báo gộp mỗi buổi một tin."""
import unittest

from tests import harness as h
from tests.test_dongtien import setup_month

import kho
import lich
import menu
import sono
import thongbao
import tietkiem


def screen(name):
    _, body, buttons = h.press(f"m:{name}")
    return body, buttons


class BonMuc(unittest.TestCase):
    def setUp(self):
        h.reset()

    def test_hang_nut_duoi_o_chat_bon_muc(self):
        reply = menu.start([])
        keyboard = reply["messages"][0][1]["keyboard"]
        self.assertEqual([b["text"] for row in keyboard for b in row],
                         ["🏠 Hôm nay", "💰 Tiền của tôi", "🎯 Kế hoạch", "💬 Hỏi"])
        for label, title in (("🏠 Hôm nay", "Hôm nay, thứ sáu 13/11"), ("💰 Tiền của tôi", "Tiền của tôi"),
                             ("🎯 Kế hoạch", "Chia lương 11/2026"), ("💬 Hỏi", "Hỏi")):
            text, _ = h.say(label)
            self.assertIn(title, text)

    def test_nut_cu_van_chay_va_gui_hang_nut_moi_mot_lan(self):
        kho.put("chitieu:banphim", True)  # người dùng cũ: đã có hàng nút bản trước
        with kho.memo():
            reply = h.ct.answer("📊 Chi tiêu", h.CLOCK["now"], h.CHAT)
        greeting, keyboard = reply["messages"][0]  # lần đầu: kèm lời chào và hàng nút mới
        self.assertIn("Bốn nút dưới ô chat", greeting)
        self.assertEqual(keyboard["keyboard"][0][0]["text"], "🏠 Hôm nay")
        self.assertIn("Chi tiêu tháng 11/2026", h.parts(reply)[0])
        text, _ = h.say("💼 Tài sản")
        self.assertIn("Tiền của tôi", text)  # lần sau: chỉ màn hình

    def test_hom_nay_viec_can_lam_co_nut(self):
        setup_month()
        h.say("cơm trưa 50k")
        text, buttons = screen("home")
        self.assertIn("Đã chi 50k: cơm trưa 50k", text)
        self.assertIn("🟢 Hôm nay còn", text)
        self.assertIn("VCB còn ~", text)
        self.assertIn("Lương đã về: trả bác Vân 2tr · nạp quỹ dự phòng", text)
        self.assertEqual(buttons[0], "kh:het")
        h.press("kh:het:ok")
        text, buttons = screen("home")
        self.assertIn("Không có việc gấp", text)
        self.assertNotIn("kh:het", buttons)

    def test_hom_nay_chua_luong_thi_nhac_tung_khoan_no(self):
        h.at(2026, 10, 20, 15)
        sono.declare_info({"ten": "bác Vân", "con": 10_000_000, "thang": 2_000_000, "lai": 0, "ngay_tra": 10},
                          h.CLOCK["now"].date())
        h.at(2026, 11, 13, 19)
        text, buttons = screen("home")
        self.assertIn("Trả bác Vân 2tr (hạn ngày 10)", text)
        self.assertIn("no:tra:", " ".join(buttons))
        self.assertIn("Chưa ghi khoản chi nào", text)
        self.assertIn("tk:khong:2026-11-13", buttons)  # sau 18h chưa ghi gì: nút không tiêu

    def test_tien_cua_toi_moi_ngan_mot_dong(self):
        setup_month()
        h.say("/taisan tien MoMo 1tr")
        h.say("/taisan tietkiem TCB 50tr 5% 6 thang 01/11/2026")
        text, buttons = screen("tien")
        self.assertIn("🏦 VCB (chính) ~49tr", text)
        self.assertIn("👛 MoMo 1tr", text)
        self.assertIn("🛟 Quỹ dự phòng 12tr / 60tr (20%)", text)
        self.assertIn("🐷 Tiết kiệm 50", text)
        self.assertIn("💳 Nợ còn 10tr", text)
        self.assertNotIn("📈 Quỹ mở", text)  # quỹ chờ đang 0đ, chưa có ccq: không hiện dòng trống
        for b in ("ts:chinh", "y:them:chuyen_tk", "dp:xem", "no:xem", "dt:xem"):
            self.assertIn(b, buttons)

    def test_ke_hoach_cho_biet_buoc_lo_trinh(self):
        setup_month()
        text, buttons = screen("kh")
        self.assertIn("🎯 Bước 1/5", text)
        self.assertIn("kh:het", buttons)
        self.assertIn("kh:lt", buttons)

    def test_hoi_bam_cau_co_san(self):
        setup_month()
        _, buttons = screen("hoi")
        self.assertIn("m:q:tieu", buttons)
        _, body, _ = h.press("m:q:tieu")
        self.assertIn("🟢 Hôm nay còn", body)
        _, body, _ = h.press("m:q:no")
        self.assertIn("bác Vân", body)

    def test_cai_dat_tat_nhac_ghi_chep(self):
        _, buttons = screen("cd")
        self.assertIn("m:tb:nhac", buttons)
        toast, body, buttons = h.press("m:tb:nhac")
        self.assertEqual(toast, "Đã tắt nhắc ghi chép 21h")
        self.assertFalse(tietkiem.config()["nhac"])
        h.at(2026, 11, 13, 21, 5)
        self.assertIsNone(thongbao.evening(h.CLOCK["now"]))

    def test_hang_nut_moi_tu_gui_khi_chay_theo_gio(self):
        h.SENT.clear()
        lich.ban_phim_moi(h.CLOCK["now"], str(h.CHAT))
        self.assertEqual(len(h.SENT), 1)
        text, markup = h.SENT[0]
        self.assertIn("Bốn nút dưới ô chat", text)
        self.assertEqual(markup["keyboard"][1][1]["text"], "💬 Hỏi")
        h.SENT.clear()
        lich.ban_phim_moi(h.CLOCK["now"], str(h.CHAT))
        self.assertEqual(h.SENT, [])  # chỉ một lần
        text, _ = h.say("cà phê 35k")  # đã gửi rồi: tin trả lời bình thường
        self.assertIn("Đã ghi", text)

    def test_tin_dau_tien_sau_cap_nhat_kem_hang_nut_moi(self):
        with kho.memo():
            reply = h.ct.answer("cà phê 35k", h.CLOCK["now"], h.CHAT)
        self.assertIn("Bốn nút dưới ô chat", reply["messages"][0][0])
        self.assertIn("Đã ghi", h.parts(reply)[0])
        text, _ = h.say("🎯 Kế hoạch")  # lần sau không gửi lại
        self.assertIn("Chia lương", text)


class ThongBaoGop(unittest.TestCase):
    def setUp(self):
        h.reset()

    def run_lich(self, job):
        h.SENT.clear()
        job(h.CLOCK["now"], str(h.CHAT))
        return [h.parts(x) for x in h.SENT]

    def test_toi_chua_ghi_thi_mot_tin_nhac(self):
        h.at(2026, 11, 13, 21, 5)
        sent = self.run_lich(lich.tong_ket_toi)
        self.assertEqual(len(sent), 1)
        text, buttons = sent[0]
        self.assertIn("🌙 Tối 13/11", text)
        self.assertIn("Hôm nay chưa ghi khoản chi nào", text)
        self.assertIn("tk:khong:2026-11-13", buttons)
        self.assertEqual(self.run_lich(lich.tong_ket_toi), [])  # mỗi tối một lần

    def test_toi_da_ghi_va_khong_co_gi_thi_khong_gui(self):
        h.say("cà phê 35k")
        h.at(2026, 11, 13, 21, 5)
        self.assertEqual(self.run_lich(lich.tong_ket_toi), [])

    def test_sang_gop_luong_va_no_vao_mot_tin(self):
        h.at(2026, 10, 20, 15)
        h.say("/luong 5 19tr")
        sono.declare_info({"ten": "bác Vân", "con": 10_000_000, "thang": 2_000_000, "lai": 0}, h.CLOCK["now"].date())
        h.at(2026, 11, 7, 9, 5)
        sent = self.run_lich(lich.tai_chinh_sang)
        self.assertEqual(len(sent), 1)
        text, buttons = sent[0]
        self.assertIn("☀️ Sáng 07/11", text)
        self.assertIn("đã nhận chưa?", text)
        self.assertIn("Nhắc trả nợ tháng 11", text)
        self.assertIn("ts:luong:19000000", buttons)
        self.assertIn("no:tra:", " ".join(buttons))

    def test_tong_ket_thang_kem_dong_no_va_quy(self):
        setup_month()
        lines = lich.month_lines(h.CLOCK["now"].date())
        self.assertTrue(any(x.startswith("💳 Nợ còn") for x in lines))
        self.assertTrue(any(x.startswith("🛟 Quỹ dự phòng 12tr/60tr") for x in lines))


if __name__ == "__main__":
    unittest.main()
