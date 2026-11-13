"""Trợ lý hiểu câu nói thường: khoản chi thường vẫn ghi ngay; việc khác hỏi lại khi thiếu và chỉ ghi sau khi bấm ✅."""
import os
import unittest

from tests import harness as h

import duphong
import kho
import sono
import taisan as ts
import tietkiem
import troly


class TroLy(unittest.TestCase):
    def setUp(self):
        h.reset()

    def test_khoan_chi_thuong_ghi_ngay_khong_hoi_ai(self):
        text, _ = h.say("cà phê 35k")
        self.assertIn("Đã ghi 35.000đ", text)
        self.assertEqual(h.AI.calls, [])

    def test_nap_quy_du_phong_can_bam_xac_nhan(self):
        h.AI.replies["nạp 1tr vào quỹ dự phòng"] = {"viec": "du_phong", "tien": 1000000, "chieu": "nap"}
        text, buttons = h.say("nạp 1tr vào quỹ dự phòng")
        self.assertIn("Mình hiểu là", text)
        self.assertIn("1.000.000đ", text)
        self.assertEqual(h.month_entries(), [])  # chưa ghi gì, không thành khoản chi
        self.assertEqual(duphong.status(h.CLOCK["now"].date())["balance"], 0)
        _, done, _ = h.press(h.button(buttons, "y:ok"))
        self.assertIn("Đã thêm 1tr vào quỹ dự phòng", done)
        self.assertEqual(duphong.status(h.CLOCK["now"].date())["balance"], 1_000_000)
        self.assertEqual(h.month_entries(), [])
        self.assertEqual(h.press(h.button(buttons, "y:ok"))[0], "Thẻ này đã xử lý hoặc hết hạn")  # bấm lại không ghi trùng

    def test_gui_tiet_kiem_hoi_tung_truong_con_thieu(self):
        h.AI.replies["gửi tiết kiệm VCB 50tr"] = {"viec": "tiet_kiem", "ten": "VCB", "tien": 50000000}
        text, buttons = h.say("gửi tiết kiệm VCB 50tr")
        self.assertIn("Lãi suất bao nhiêu", text)
        calls = len(h.AI.calls)
        text, buttons = h.say("4,7%")  # câu trả lời ngắn: code tự đọc, không hỏi AI
        self.assertEqual(len(h.AI.calls), calls)
        self.assertIn("Kỳ hạn mấy tháng", text)
        _, text, buttons = h.press(h.button(buttons, "y:tl:ky:3"))  # nút "6 tháng"
        self.assertIn("lãi 4,7%/năm, kỳ hạn 6 tháng", text)
        _, done, _ = h.press(h.button(buttons, "y:ok"))
        self.assertIn("Đã thêm sổ tiết kiệm VCB 50.000.000đ", done)
        saving = [it for it in ts.load()["items"] if it["loai"] == "tietkiem"]
        self.assertEqual([(it["ten"], it["tien"], it["lai"], it["ky"]) for it in saving], [("VCB", 50_000_000, 4.7, 6)])

    def test_mua_vang_so_tien_doi_chieu_voi_cau(self):
        ask = "mua 2 vỉ vàng nhẫn 0,1 chỉ hết 2tr476"
        h.AI.replies[ask] = {"viec": "vang", "loai": "nhan", "chi": 0.2, "tien": 2476}  # AI đọc sai số tiền
        text, buttons = h.say(ask)
        self.assertIn("0,2 chỉ", text)
        self.assertIn("2.476.000đ", text)  # code sửa lại theo số đọc được trong câu
        self.assertIn("123,80 triệu/lượng", text)
        h.press(h.button(buttons, "y:ok"))
        gold = kho.get("vivang")
        self.assertEqual((gold[0]["loai"], round(gold[0]["luong"], 3), gold[0]["gia"]), ("nhan", 0.02, 123.8))
        self.assertEqual(h.month_entries(), [])  # mua vàng không phải khoản chi

    def test_vay_no_bo_qua_va_chon_bang_nut(self):
        h.AI.replies["vay anh Nam 10tr"] = {"viec": "no_moi", "ten": "anh Nam", "tien": 10000000}
        text, buttons = h.say("vay anh Nam 10tr")
        self.assertIn("Mỗi tháng trả bao nhiêu", text)
        _, text, buttons = h.press(h.button(buttons, "y:bo:moi_thang"))
        self.assertIn("Lãi suất", text)
        _, text, buttons = h.press(h.button(buttons, "y:tl:lai:0"))  # nút "Không lãi"
        self.assertIn("còn nợ 10.000.000đ, không lãi", text)
        h.press(h.button(buttons, "y:ok"))
        debt = sono.active()[0]
        self.assertEqual((debt["ten"], debt["tien"], debt["lai"]), ("anh Nam", 10_000_000, 0))

    def test_sua_the_bang_cau_noi(self):
        h.AI.replies["cho Dương vay 3tr"] = {"viec": "cho_vay", "ten": "Dương", "tien": 3000000}
        _, buttons = h.say("cho Dương vay 3tr")
        _, ask, _ = h.press(h.button(buttons, "y:sua"))
        self.assertIn("Sửa chỗ nào", ask)
        h.AI.replies["2 triệu thôi"] = {"viec": "cho_vay", "tien": 2000000}  # AI chỉ trả phần đổi
        text, buttons2 = h.say("2 triệu thôi")
        self.assertIn("Cho Dương vay 2.000.000đ", text)
        self.assertEqual(h.press(h.button(buttons, "y:ok"))[0], "Thẻ này đã xử lý hoặc hết hạn")  # thẻ cũ đã bị thay
        h.press(h.button(buttons2, "y:ok"))
        asset = [it for it in ts.load()["items"] if it["loai"] == "khac"]
        self.assertEqual([(it["ten"], it["tien"]) for it in asset], [("Cho Dương vay", 2_000_000)])

    def test_hoi_ve_no_mo_so_no_cau_hoi_chi_tieu_van_nhu_cu(self):
        sono.declare("bác Vân 20tr, trả 5tr/tháng, không lãi", h.CLOCK["now"].date())
        h.AI.replies["tôi còn nợ bao nhiêu"] = {"viec": "xem", "man": "no"}
        text, _ = h.say("tôi còn nợ bao nhiêu")
        self.assertIn("Sổ nợ: còn 20tr", text)
        h.say("cà phê 35k")
        text, _ = h.say("tháng này cà phê hết bao nhiêu?")  # AI bận: bot tự hiểu câu hỏi chi tiêu như trước
        self.assertIn("35.000đ", text)

    def test_ai_ban_thi_hoi_lai_bang_nut_khong_tu_doan(self):
        text, buttons = h.say("chuyển 5tr vào tiết kiệm")
        self.assertIn("AI đang bận", text)
        self.assertEqual(h.month_entries(), [])
        _, done, _ = h.press(h.button(buttons, "y:chi"))
        self.assertIn("Đã ghi 5.000.000đ", done)

    def test_khoan_chi_co_chu_de_nham_chi_hoi_ai_lan_dau(self):
        h.AI.replies["nạp game 50k"] = {"viec": "chi"}
        text, _ = h.say("nạp game 50k")
        self.assertIn("Đã ghi 50.000đ", text)
        calls = len(h.AI.calls)
        h.AI.replies.clear()  # lần sau AI có bận cũng không sao: bot đã nhớ đây là khoản chi
        text, _ = h.say("nạp game 100k")
        self.assertIn("Đã ghi 100.000đ", text)
        self.assertEqual(len(h.AI.calls), calls)

    def test_dang_hoi_do_ma_nhan_khoan_chi_thi_ghi_khoan_chi(self):
        h.AI.replies["gửi tiết kiệm VCB 50tr"] = {"viec": "tiet_kiem", "ten": "VCB", "tien": 50000000}
        h.say("gửi tiết kiệm VCB 50tr")
        h.AI.replies["cà phê 35k"] = {"viec": "chi"}
        text, _ = h.say("cà phê 35k")
        self.assertIn("Đã ghi 35.000đ", text)
        self.assertIsNone(troly.state(h.CHAT))
        self.assertEqual([it for it in ts.load()["items"] if it["loai"] == "tietkiem"], [])

    def test_them_bang_nut_hoi_tung_buoc(self):
        _, text, buttons = h.press("y:them")
        self.assertIn("Thêm gì", text)
        _, text, _ = h.press(h.button(buttons, "y:them:tai_khoan"))
        self.assertIn("Tài khoản hay ví nào", text)
        text, _ = h.say("Techcombank")
        self.assertIn("Số dư hiện tại", text)
        text, buttons = h.say("14tr")
        self.assertIn("Số dư Techcombank hiện là 14.000.000đ", text)
        h.press(h.button(buttons, "y:ok"))
        self.assertEqual([(it["ten"], it["tien"]) for it in ts.load()["items"] if it["loai"] == "tien"],
                         [("Techcombank", 14_000_000)])

    def test_anh_ban_co_phieu_thieu_ma_thi_hoi_roi_tinh_lo(self):
        text, _ = h.parts(troly.from_photo({"viec": "co_phieu", "chieu": "ban", "sl": 1300, "gia": 12.0,
                                            "gia_von": 22.816}, h.CHAT, h.CLOCK["now"]))
        self.assertIn("Mã cổ phiếu nào", text)
        text, buttons = h.say("hag")
        self.assertIn("Đọc từ ảnh", text)
        self.assertIn("Bán 1.300 HAG giá 12.000đ, giá vốn 22.816đ", text)
        _, done, _ = h.press(h.button(buttons, "y:ok"))
        self.assertIn("Đã bán 1.300 HAG", done)
        data = ts.load()
        self.assertEqual([it for it in data["items"] if it["loai"] == "cp"], [])
        self.assertEqual(data["lailo"][-1]["lai"], round(1300 * 12000 * 0.999 - 1300 * 22816))  # lỗ, đã trừ thuế 0,1%

    def test_khong_tieu_va_lenh_xoa_viec_dang_do(self):
        text, _ = h.say("hôm nay không tiêu gì")  # hiểu bằng luật, không cần AI
        self.assertIn("không tiêu gì", text)
        self.assertEqual(h.AI.calls, [])
        self.assertIn(h.CLOCK["now"].date().isoformat(), tietkiem.config()["khong_tieu"])
        h.press("y:them:cho_vay")
        self.assertIsNotNone(troly.state(h.CHAT))
        h.say("/menu")
        self.assertIsNone(troly.state(h.CHAT))

    def test_nhan_luong_khong_co_dau_cong_van_la_khoan_thu(self):
        h.AI.replies["nhận lương tháng 11 19tr"] = {"viec": "thu", "tien": 19000000, "ghi_chu": "lương tháng 11"}
        text, _ = h.say("nhận lương tháng 11 19tr")
        self.assertIn("Đã ghi 19.000.000đ", text)
        self.assertEqual([(e["tien"], e["nhom"], e["ghichu"]) for e in h.month_entries()],
                         [(19_000_000, "thu", "lương tháng 11")])

    def test_cau_hoi_ngoai_so_chi_tieu_ma_ai_ban_thi_tra_loi_nhu_truoc(self):
        text, _ = h.say("tháng này tiết kiệm được bao nhiêu?")
        self.assertIn("bot hiểu câu hỏi theo cách đơn giản", text)  # trả lời như trước, không báo lỗi

    def test_trang_thu_cau_khong_ghi_gi(self):
        ask = "mua 2 chỉ vàng nhẫn hết 27tr"
        h.AI.replies[ask] = {"viec": "vang", "loai": "nhan", "chi": 2, "tien": 27000000}
        out = troly.try_text(ask, h.CLOCK["now"].date())
        self.assertIn("Thẻ xác nhận: 🥇 Mua 2 chỉ vàng nhẫn 24k, trả 27.000.000đ", out)
        self.assertIsNone(kho.get("vivang"))
        self.assertIn("ghi ngay như trước", troly.try_text("cà phê 35k", h.CLOCK["now"].date()))

    def test_chua_bat_ai_thi_chay_nhu_truoc(self):
        os.environ.pop("GEMINI_API_KEY")
        text, _ = h.say("nạp 1tr vào quỹ dự phòng")
        self.assertIn("Đã ghi 1.000.000đ", text)
        self.assertEqual(h.AI.calls, [])


if __name__ == "__main__":
    unittest.main()
