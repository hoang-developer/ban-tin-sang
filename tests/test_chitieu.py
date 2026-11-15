"""Ghi chi tiêu, đọc ảnh, tiết kiệm so với mốc: các luồng có từ trước, giữ cho không hỏng khi sửa."""
import unittest

from tests import harness as h

import kho
import tietkiem


class ChiTieu(unittest.TestCase):
    def setUp(self):
        h.reset()

    def test_ghi_nhieu_khoan_va_khoan_thu(self):
        text, _ = h.say("cơm trưa 45k\nđổ xăng 80000\n+ lương 19tr")
        self.assertIn("45.000đ", text)
        entries = h.month_entries()
        self.assertEqual(sorted(e["tien"] for e in entries), [45_000, 80_000, 19_000_000])
        self.assertEqual(sum(e["nhom"] == "thu" for e in entries), 1)

    def test_chuoi_ngay_ghi_va_so_da_bot(self):
        h.at(2026, 11, 4, 12)
        h.say("cà phê 35k\ncơm trưa 50k")
        h.at(2026, 11, 5, 12)
        text, _ = h.say("cơm trưa 45k")
        self.assertIn("🔥 2 ngày · hôm nay 45k/324k · từ 04/11 đã bớt ~239k", text)
        h.at(2026, 11, 6, 21, 5)
        reply = tietkiem.reminder(h.CLOCK["now"].date())
        self.assertIn("Hôm nay chưa ghi khoản chi nào", reply[0])
        toast, _, _ = h.press(reply[1][0][0][1], reply[0])
        self.assertIn("🔥 3 ngày", toast)

    def test_anh_hoa_don_van_ghi_nhu_truoc(self):
        h.AI.photo = {"loai": "hoa_don", "giao_dich": [{"so_tien": 29000, "chieu": "chi", "ngay": "13/11/2026",
                                                        "noi_dung": "phin sữa đá highlands", "noi_ban": "Highlands",
                                                        "diem": 0, "kieu": "chi_tieu", "nhom": "an"}]}
        text, _ = h.send_photo()
        self.assertIn("Đã ghi 29.000đ", text)
        self.assertEqual([e["tien"] for e in h.month_entries()], [29_000])

    def test_anh_don_mua_vang_khong_thanh_khoan_chi(self):
        h.AI.photo = {"loai": "tai_san", "giao_dich": [],
                      "viec": {"viec": "vang", "loai": "nhan", "chi": 0.2, "tien": 2476800}}
        text, buttons = h.send_photo()
        self.assertIn("Mua 0,2 chỉ vàng nhẫn 24k, trả 2.476.800đ (≈ 123,84 triệu/lượng)", text)
        h.press(h.button(buttons, "y:ok"))
        self.assertEqual(h.month_entries(), [])
        self.assertEqual(kho.get("vivang")[0]["gia"], 123.84)

    def test_vang_gop_theo_loai_gia_theo_chi_tung_lan_mua(self):
        h.say("/taisan vang nhan 0,1 chi 148,02 20/10\n/taisan vang nhan 0,2 chi 123,84 11/11")
        h.say("/taisan cp HAG 100 12")
        h.say("bán 100 HAG giá 12")  # bán hết: không còn dòng 0 cp
        _, body, _ = h.press("ts:xem")
        self.assertIn("Nhẫn 0,3 chỉ · vốn TB 13,19tr/chỉ · hôm nay 13,6tr/chỉ", body)
        self.assertIn("• 20/10 0,1 chỉ giá 14,8tr/chỉ → 🔴 −120k (−8%)", body)
        self.assertIn("• 11/11 0,2 chỉ giá 12,38tr/chỉ → 🟢 +243k (+10%)", body)
        self.assertNotIn("HAG", body)

    def test_mua_vang_qua_the_ghi_ngay_mua(self):
        ask = "mua 0,1 chỉ vàng nhẫn hết 1tr3"
        h.AI.replies[ask] = {"viec": "vang", "loai": "nhan", "chi": 0.1, "tien": 1300000}
        _, buttons = h.say(ask)
        h.press(h.button(buttons, "y:ok"))
        self.assertEqual(kho.get("vivang")[-1]["ngay"], "2026-11-13")


if __name__ == "__main__":
    unittest.main()
