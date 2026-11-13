"""Đầu tư quỹ mở theo Value Averaging, chạy trên NAV thật của VMEEF và VFF (tháng 9–11/2026)."""
import unittest

from tests import harness as h

import dautu
import taisan as ts


def setup_plan():
    """09/09/2026: bật VA 4tr VMEEF, đã mua 1tr sáng đó, quỹ chờ là VFF, góp thêm 1tr VFF mỗi tháng."""
    h.reset()
    h.at(2026, 9, 9, 15)
    for line in ("/dautu batdau 4tr VMEEF", "/dautu dadat 1tr 9/9", "/dautu quycho VFF", "/dautu vff 1tr"):
        h.say(line)


def units(code):
    return next((it["sl"] for it in ts.load()["items"] if it["loai"] == "quy" and it["ma"] == code), 0)


class DauTu(unittest.TestCase):
    def test_mot_ky_mua_ca_hai_quy(self):
        setup_plan()
        h.at(2026, 9, 10, 17, 30)
        text, buttons = h.run_jobs()[0]
        self.assertIn("Lệnh VMEEF 1.000.000đ đã khớp phiên 10/09: NAV 15.458,06đ → 64,69 ccq", text)
        self.assertIn("y:them:sua_ccq:VMEEF", buttons)  # sửa số ccq bằng nút, không phải gõ lệnh
        h.at(2026, 9, 30, 8, 35)
        text, buttons = h.run_jobs()[0]
        self.assertIn("hôm nay là hạn đặt lệnh tháng 9", text)
        self.assertIn("1. Mua VMEEF 3.020.000đ (tiền góp)", text)
        self.assertIn("2. Mua VFF 980.000đ", text)
        h.press(h.button(buttons, "dt:dat2"))
        h.at(2026, 9, 30, 13, 5)
        self.assertEqual(h.run_jobs(), [])  # đã đặt: không nhắc lại
        h.at(2026, 10, 1, 17, 30)
        h.run_jobs()
        self.assertEqual((units("VMEEF"), units("VFF")), (264.48, 36.34))
        h.at(2026, 10, 1, 20, 5)
        self.assertEqual(h.run_jobs(), [])  # lãi/lỗ quỹ không gửi riêng nữa: nằm trong tin tối 21h
        h.at(2026, 10, 1, 21, 5)
        sent = h.run_jobs()
        self.assertEqual(len(sent), 1)  # một tin tối gộp
        text, buttons = sent[0]
        self.assertIn("🌙 Tối 01/10", text)
        self.assertIn("📊 Quỹ (so với tiền gốc)", text)
        self.assertIn("VMEEF 4tr · 🔴 −22k (−0,6%)", text)
        self.assertIn("Tổng 4,98tr", text)
        self.assertIn("dt:xem", buttons)
        h.at(2026, 10, 3, 21, 5)  # thứ Bảy: không có NAV mới, không gì khác cần báo: không gửi
        self.assertEqual(h.run_jobs(), [])

    def test_sua_so_ccq_bang_nut(self):
        setup_plan()
        h.at(2026, 9, 10, 17, 30)
        _, buttons = h.run_jobs()[0]
        _, ask, _ = h.press(h.button(buttons, "y:them:sua_ccq"))
        self.assertIn("bao nhiêu ccq", ask)
        text, _ = h.say("64,7")
        self.assertIn("Đã sửa lệnh VMEEF phiên 10/09: 64,7 ccq", text)
        self.assertEqual(units("VMEEF"), 64.7)

    def test_khoan_tien_lon_rai_ba_thang(self):
        setup_plan()
        h.at(2026, 9, 14, 20)
        text, _ = h.say("/dautu taicocau 15,5tr")
        self.assertIn("mua VFF 15.500.000đ: đặt 14/09 → khớp NAV phiên 17/09", text)
        self.assertIn("Rải 12,4tr (80%) từ VFF vào VMEEF trong 3 tháng", text)
        self.assertEqual(dautu.config()["ke_hoach_them"],
                         {"2026-09": 4_130_000, "2026-10": 4_130_000, "2026-11": 4_140_000})
        h.at(2026, 9, 17, 17, 30)
        h.run_jobs()
        h.at(2026, 9, 30, 8, 35)
        text, _ = h.run_jobs()[0]
        self.assertIn("1. Mua VMEEF 4.000.000đ (tiền góp)", text)
        self.assertIn("Hoán đổi 116,86 ccq VFF → VMEEF", text)

    def test_cau_noi_thuong_ghi_lenh_quy_sau_khi_xac_nhan(self):
        setup_plan()
        h.at(2026, 9, 21, 10)
        ask = "sáng nay mình đặt 2 triệu vmeef rồi"
        h.AI.replies[ask] = {"viec": "quy", "chieu": "mua", "ma": "VMEEF", "tien": 2000000, "ngay": "2026-09-21"}
        text, buttons = h.say(ask)
        self.assertIn("Mua quỹ VMEEF: 2.000.000đ, đặt ngày 21/09", text)
        self.assertEqual(len(dautu.config()["lenh"]), 1)  # chưa ghi lệnh mới cho tới khi bấm ✅
        _, done, _ = h.press(h.button(buttons, "y:ok"))
        self.assertIn("Đã ghi lệnh mua VMEEF 2.000.000đ: đặt 21/09 → khớp NAV phiên 22/09", done)

    def test_anh_lenh_mua_quy_cho_khoan_lon_goi_y_rai(self):
        setup_plan()
        h.at(2026, 9, 14, 10)
        h.AI.photo = {"loai": "tai_san", "giao_dich": [],
                      "viec": {"viec": "quy", "chieu": "mua", "ma": "VFF", "tien": 15500000}}
        text, buttons = h.send_photo()
        self.assertIn("Đọc từ ảnh", text)
        self.assertIn("Mua quỹ VFF: 15.500.000đ", text)
        _, done, _ = h.press(next(b for b in buttons if b.endswith(":rai")))  # nút "Ghi và rải 80% sang VMEEF"
        self.assertIn("Rải 12,4tr (80%) từ VFF vào VMEEF trong 3 tháng", done)
        self.assertEqual(sum(dautu.config()["ke_hoach_them"].values()), 12_400_000)


if __name__ == "__main__":
    unittest.main()
