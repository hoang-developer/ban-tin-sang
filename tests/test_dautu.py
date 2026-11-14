"""Đầu tư quỹ mở theo Value Averaging, chạy trên NAV thật của VMEEF và VFF (tháng 9–11/2026)."""
import unittest

from tests import harness as h

from datetime import date

import dautu
import taisan as ts
import thongbao


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

    def test_hoan_doi_hai_buoc_roi_hoi_ngay_cap_nhat_gia(self):
        setup_plan()
        h.at(2026, 9, 14, 20)
        h.say("/dautu taicocau 15,5tr")  # mua VFF 15,5tr, khớp 17/09
        h.at(2026, 9, 17, 17, 30)
        h.run_jobs()
        vff_before, vmeef_before = units("VFF"), units("VMEEF")
        h.at(2026, 9, 22, 10)
        note = dautu.record_switch(100)
        self.assertIn("bán VFF phiên <b>24/09</b>, tiền về mới mua VMEEF", note)
        h.at(2026, 9, 24, 17, 30)
        text, _ = h.run_jobs()[0]
        nav_sell = dict(h.NAV["VFF"])[date(2026, 9, 24)]
        self.assertIn("Đã bán 100 ccq VFF phiên 24/09", text)
        self.assertIn("đang chuyển sang VMEEF", text)
        self.assertEqual((units("VFF"), units("VMEEF")), (round(vff_before - 100, 2), vmeef_before))  # chưa mua VMEEF
        value = ts.valuation(h.CLOCK["now"].date())
        moving = [r for r in value["rows"] if r[2] == "VMEEF đang chuyển"]
        self.assertEqual([r[3] for r in moving], [round(100 * nav_sell)])  # tiền đang chuyển vẫn là tài sản
        h.at(2026, 9, 28, 9, 5)
        self.assertNotIn("Hoán đổi", (thongbao.morning(h.CLOCK["now"].date()) or ("",))[0])  # chưa đủ 1 tuần
        h.at(2026, 9, 29, 9, 5)
        text, buttons = h.parts(thongbao.morning(h.CLOCK["now"].date()))
        self.assertIn("Hoán đổi 100 ccq VFF → VMEEF (đặt 22/09) xong chưa?", text)
        toast, _, _ = h.press(h.button(buttons, "dt:chua:"))
        self.assertIn("2 ngày", toast)
        h.at(2026, 9, 30, 9, 5)
        self.assertIsNone(thongbao.morning(h.CLOCK["now"].date()))  # đã bấm Chưa: chưa hỏi lại
        h.at(2026, 10, 2, 9, 5)
        text, buttons = h.parts(thongbao.morning(h.CLOCK["now"].date()))
        _, ask, _ = h.press(h.button(buttons, "y:them:doi_xong:"))
        self.assertIn("Mua VMEEF khớp ngày nào?", ask)  # ngày bán đã biết (24/09), chỉ hỏi ngày mua
        text, buttons = h.say("1/10")
        self.assertIn("bao nhiêu ccq VMEEF", text)
        _, card, buttons = h.press("y:bo:ccq")
        nav_buy = dict(h.NAV["VMEEF"])[date(2026, 10, 1)]
        got = round(100 * nav_sell / nav_buy, 2)
        self.assertIn("Bán VFF 24/09", card)
        self.assertIn(f"Mua VMEEF 01/10", card)
        _, done, _ = h.press(h.button(buttons, "y:ok:"))
        self.assertIn("Hoán đổi xong", done)
        self.assertEqual(units("VMEEF"), round(vmeef_before + got, 2))
        self.assertEqual(dautu.open_switches(), [])
        self.assertIsNone(thongbao.morning(date(2026, 10, 3)))  # xong rồi: không hỏi nữa
        # báo lại số ccq theo Fmarket: sửa đúng lệnh đó, không cộng hai lần
        order = dautu.config()["lenh"][-1]
        dautu.finish_switch(order["id"], date(2026, 9, 24), date(2026, 10, 1), 210.5)
        self.assertEqual(units("VMEEF"), round(vmeef_before + 210.5, 2))

    def test_nhan_cau_thuong_sua_hoan_doi_cu(self):
        setup_plan()
        h.at(2026, 9, 14, 20)
        h.say("/dautu taicocau 15,5tr")
        h.at(2026, 9, 17, 17, 30)
        h.run_jobs()
        h.at(2026, 9, 22, 10)
        dautu.record_switch(100)
        vmeef_before, vff_before = units("VMEEF"), units("VFF")
        h.at(2026, 10, 2, 10)
        ask = "hoán đổi vff xong rồi, bán 24/9 mua 1/10"
        h.AI.replies[ask] = {"viec": "doi_xong", "ngay_ban": "2026-09-24", "ngay_mua": "2026-10-01"}
        text, _ = h.say(ask)
        self.assertIn("bao nhiêu ccq VMEEF", text)  # hỏi một lần số ccq Fmarket báo (bỏ qua được)
        text, buttons = h.say("212,3")
        self.assertIn("212,3 ccq", text)
        h.press(h.button(buttons, "y:ok:"))
        self.assertEqual(units("VMEEF"), round(vmeef_before + 212.3, 2))
        self.assertEqual(units("VFF"), round(vff_before - 100, 2))  # chưa chạy việc tối bán VFF: trừ lúc báo xong
        self.assertEqual(dautu.open_switches(), [])


if __name__ == "__main__":
    unittest.main()
