"""Giai đoạn 2, một dòng tiền thống nhất: tài khoản chính tự cộng thu, trừ chi; chuyển tiền giữa các ngăn trừ nơi
đi, cộng nơi đến (tài sản ròng không đổi); một nút làm hết kế hoạch chia lương; một con số "mỗi ngày được tiêu"."""
import re
import unittest

from tests import harness as h

import duphong
import kehoach
import kho
import menu
import sochitieu as ct
import sono
import taisan as ts


def main_balance():
    return round(ts.main_balance(ts.main_account()))


def net():
    return round(ts.valuation(h.CLOCK["now"].date())["net"])


def item(name):
    return next(it for it in ts.load()["items"] if ts.same_name(it.get("ten") or it.get("ma", ""), name))


def set_main(amount=50_000_000, name="VCB"):
    """Khai báo tài khoản bằng câu thường rồi bấm nút "là tài khoản chính" trên thẻ."""
    sentence = f"tài khoản {name} còn {amount // 1_000_000}tr"
    h.AI.replies[sentence] = {"viec": "tai_khoan", "ten": name, "tien": amount}
    text, buttons = h.say(sentence)
    assert "y:ok:" in " ".join(buttons), text
    _, body, _ = h.press(h.button(buttons, "y:ok:").split(":chinh")[0] + ":chinh")
    return body


def spend_number(text):
    """Số "hôm nay còn được tiêu …" trong một tin."""
    m = re.search(r"Hôm nay còn được tiêu ([\d.]+đ) \(mỗi ngày tối đa ([^)]+)\)", text)
    return m.groups() if m else None


class TaiKhoanChinh(unittest.TestCase):
    def setUp(self):
        h.reset()

    def test_chua_chon_tai_khoan_chinh_thi_nhu_cu(self):
        h.say("/taisan tien VCB 20tr")
        reply = duphong.duphong(["nap", "2tr"])
        self.assertNotIn("🏦", reply)
        self.assertEqual(item("VCB")["tien"], 20_000_000)
        self.assertNotIn("chuyen", item("VCB"))
        _, body, buttons = h.press("ts:chinh")
        self.assertIn("Chọn tài khoản chính", body)
        self.assertIn(f"ts:chinh:{item('VCB')['id']}", buttons)  # quỹ dự phòng không được chọn làm tài khoản chính
        self.assertEqual(sum(b.startswith("ts:chinh:") for b in buttons), 1)

    def test_chon_bang_nut_va_tu_cong_thu_tru_chi(self):
        h.say("/taisan tien VCB 20tr")
        _, body, _ = h.press(f"ts:chinh:{item('VCB')['id']}")
        self.assertIn("Tài khoản chính: VCB", body)
        h.say("cà phê 35k")
        self.assertEqual(main_balance(), 19_965_000)
        h.say("+ thưởng 1tr")
        self.assertEqual(main_balance(), 20_965_000)
        h.say("/xoa")  # xóa khoản vừa ghi: số dư tự đúng lại
        self.assertEqual(main_balance(), 19_965_000)
        h.say("12/11 ăn tối 200k")  # khoản của hôm qua: đã nằm trong số dư lúc chốt sáng nay
        self.assertEqual(main_balance(), 19_965_000)
        _, body, _ = h.press("ts:chinh")
        self.assertIn("Số dư ước tính: 19.965.000đ", body)
        self.assertIn("chi: −35k", body)

    def test_khai_bao_lai_so_du_thi_chot_lai(self):
        self.assertIn("Đã đặt làm tài khoản chính", set_main(30_000_000))
        h.say("cơm trưa 50k")
        self.assertEqual(main_balance(), 29_950_000)
        h.AI.replies["tài khoản VCB còn 28tr"] = {"viec": "tai_khoan", "ten": "VCB", "tien": 28_000_000}
        _, buttons = h.say("tài khoản VCB còn 28tr")
        self.assertFalse(any(b.endswith(":chinh") for b in buttons))  # đã là tài khoản chính: không hỏi lại
        h.press(h.button(buttons, "y:ok:"))
        self.assertEqual(main_balance(), 28_000_000)
        h.say("cà phê 30k")
        self.assertEqual(main_balance(), 27_970_000)

    def test_chuyen_giua_cac_ngan_tai_san_rong_khong_doi(self):
        set_main(50_000_000)
        before = net()
        h.AI.replies["nạp 3tr vào quỹ dự phòng"] = {"viec": "du_phong", "tien": 3_000_000, "chieu": "nap"}
        text, buttons = h.say("nạp 3tr vào quỹ dự phòng")
        self.assertIn("Tiền từ VCB: còn ~47tr sau khi chuyển", text)
        _, body, _ = h.press(h.button(buttons, "y:ok:"))
        self.assertIn("Trừ 3tr từ VCB: còn ~47tr", body)
        self.assertEqual((main_balance(), item("Quỹ dự phòng")["tien"], net()), (47_000_000, 3_000_000, before))

        h.AI.replies["rút 1tr quỹ dự phòng"] = {"viec": "du_phong", "tien": 1_000_000, "chieu": "rut"}
        _, buttons = h.say("rút 1tr quỹ dự phòng")
        h.press(h.button(buttons, "y:ok:"))
        self.assertEqual((main_balance(), net()), (48_000_000, before))

        h.AI.replies["cho Hùng vay 1tr"] = {"viec": "cho_vay", "ten": "Hùng", "tien": 1_000_000}
        _, buttons = h.say("cho Hùng vay 1tr")
        h.press(h.button(buttons, "y:ok:"))
        self.assertEqual((main_balance(), net()), (47_000_000, before))

        text, _ = h.say("mua 100 HAG giá 12")
        self.assertIn("Trừ 1,2tr từ VCB", text)
        self.assertEqual((main_balance(), net()), (45_800_000, before))
        h.STOCKS["HAG"] = 13000
        try:
            text, _ = h.say("bán 100 HAG giá 13")
            self.assertIn("Cộng 1,3tr vào VCB", text)
            # tiền bán 1.300.000 − thuế 1.300 về tài khoản; khoản lãi ghi thu nhập không cộng thêm lần nữa
            self.assertEqual(main_balance(), 45_800_000 + 1_298_700)
        finally:
            h.STOCKS["HAG"] = 12000

    def test_tien_co_san_thi_khong_tru(self):
        set_main(50_000_000)
        before = net()
        h.AI.replies["gửi tiết kiệm TCB 10tr lãi 5% 6 tháng"] = {"viec": "tiet_kiem", "ten": "TCB", "tien": 10_000_000,
                                                                 "lai": 5, "ky": 6}
        text, buttons = h.say("gửi tiết kiệm TCB 10tr lãi 5% 6 tháng")
        self.assertIn("Tiền từ VCB: còn ~40tr", text)
        _, card, buttons = h.press(h.button(buttons, "y:nguon:"))
        self.assertIn("Tiền có sẵn, không trừ VCB", card)
        h.press(h.button(buttons, "y:ok:"))
        self.assertEqual((main_balance(), net()), (50_000_000, before + 10_000_000))
        # mua vàng: trừ tài khoản chính theo số tiền đã trả
        h.AI.replies["mua 2 chỉ vàng nhẫn hết 27tr"] = {"viec": "vang", "loai": "nhan", "chi": 2, "tien": 27_000_000}
        _, buttons = h.say("mua 2 chỉ vàng nhẫn hết 27tr")
        _, body, _ = h.press(h.button(buttons, "y:ok:"))
        self.assertIn("Trừ 27tr từ VCB", body)
        self.assertEqual(main_balance(), 23_000_000)

    def test_tai_khoan_chung_khoan_thi_khong_dung_tai_khoan_chinh(self):
        set_main(50_000_000)
        h.say("/taisan tien DNSE 5tr")
        h.say("mua 100 HAG giá 12")
        self.assertEqual((main_balance(), item("DNSE")["tien"]), (50_000_000, 3_800_000))

    def test_quy_cho_dau_tu(self):
        h.at(2026, 11, 13, 15)
        h.say("/dautu batdau 4tr VMEEF")
        set_main(50_000_000)
        text, _ = h.say("/dautu nap 2tr")
        self.assertIn("Trừ 2tr từ VCB", text)
        text, _ = h.say("/dautu rut 500k")
        self.assertIn("Cộng 500k vào VCB", text)
        self.assertEqual(main_balance(), 48_500_000)
        before = net()
        text, _ = h.say("/dautu dadat 3tr")  # quỹ chờ có 1,5tr: phần thiếu 1,5tr đi từ tài khoản chính
        self.assertIn("Trừ 1,5tr từ VCB", text)
        self.assertEqual(main_balance(), 47_000_000)
        self.assertEqual(net(), before)  # lệnh chờ khớp vẫn tính vào tài sản (theo số tiền) tới khi thành ccq
        _, body, _ = h.press("ts:xem")
        self.assertIn("VMEEF chờ khớp: 3tr", body)
        _, body, buttons = h.press("ts:ds")
        self.assertNotIn("chờ khớp", body)  # không xóa lệnh ở danh sách tài sản


def setup_month():
    """20/10: chi thiết yếu 10tr/tháng, quỹ dự phòng có sẵn 12tr, nợ bác Vân 10tr trả 2tr/tháng từ tháng 11, bật đầu tư
    VMEEF 4tr/tháng, tài khoản chính VCB 30tr. 05/11 lương về 19tr."""
    h.at(2026, 10, 20, 15)
    h.say("/duphong chi 10tr")
    h.say("/duphong nap 12tr")
    sono.declare_info({"ten": "bác Vân", "con": 10_000_000, "thang": 2_000_000, "lai": 0}, h.CLOCK["now"].date())
    h.say("/dautu batdau 4tr VMEEF")
    set_main(30_000_000)
    h.at(2026, 11, 5, 10)
    return h.say("+ lương 19tr")


class ChiaLuong(unittest.TestCase):
    def setUp(self):
        h.reset()

    def test_mot_nut_lam_het_ke_hoach(self):
        text, buttons = setup_month()
        self.assertIn("Lương về!", text)
        self.assertIn("kh:het", buttons)
        self.assertEqual(main_balance(), 49_000_000)
        n = kehoach.numbers(h.CLOCK["now"].date())
        fund, invest = n["fund_left"], n["invest_left"]
        self.assertEqual((n["debt_left"], invest), (2_000_000, 4_000_000))
        self.assertGreater(fund, 0)
        _, body, buttons = h.press("kh:het", text)
        self.assertIn("Trả bác Vân: 2tr", body)
        self.assertIn("Nạp quỹ dự phòng", body)
        self.assertIn("Để vào quỹ chờ VMEEF: 4tr", body)
        total = 2_000_000 + fund + invest
        self.assertIn(f"Tiền đi từ VCB: 49tr → còn ~{ts.short(49_000_000 - total)}", body)
        before = net()
        toast, body, _ = h.press("kh:het:ok", body)
        self.assertEqual(toast, "Đã làm theo kế hoạch")
        self.assertIn("✅ Trả bác Vân 2tr", body)
        self.assertIn("Chia lương tháng 11/2026", body)
        self.assertEqual(main_balance(), 49_000_000 - total)
        self.assertEqual(net(), before)  # trả nợ: tài sản và nợ cùng giảm; nạp quỹ, góp đầu tư: chuyển ngăn
        self.assertEqual(sono.by_id(ts.load(), item("bác Vân")["id"])["tien"], 8_000_000)
        self.assertEqual(item("Quỹ dự phòng")["tien"], 12_000_000 + fund)
        self.assertEqual(item("Quỹ chờ VMEEF")["tien"], invest)
        debt_entries = [e for e in h.month_entries() if e.get("no")]
        self.assertEqual([e["tien"] for e in debt_entries], [2_000_000])
        self.assertEqual(kehoach.steps(kehoach.numbers(h.CLOCK["now"].date())), [])
        _, body, _ = h.press("kh:het:ok", body)  # bấm lại: không làm hai lần
        self.assertIn("đã làm hết rồi", body)
        self.assertEqual(main_balance(), 49_000_000 - total)

    def test_ke_hoach_goi_y_chon_tai_khoan_chinh(self):
        h.at(2026, 11, 5, 10)
        h.say("+ lương 19tr")
        text, buttons = kehoach.plan(h.CLOCK["now"].date())
        self.assertIn("Chọn tài khoản chính", text)
        self.assertIn("ts:chon", [d for row in buttons for _, d in row])


class MoiNgayDuocTieu(unittest.TestCase):
    def setUp(self):
        h.reset()

    def test_mot_con_so_o_moi_noi(self):
        setup_month()
        day = h.CLOCK["now"].date()
        text, _ = h.say("cơm trưa 50k")
        after = spend_number(text)
        self.assertIsNotNone(after, text)
        self.assertNotIn("/324k", text)  # một con số mỗi ngày: không hiện thêm mốc tiết kiệm
        self.assertIn("🔥 1 ngày", text)
        s = kehoach.spendable(day)
        n = kehoach.numbers(day)
        self.assertEqual(s["limit"], 19_000_000 - 2_000_000 - n["fund_target"] - 4_000_000)
        # 26 ngày (05/11 tới 30/11), hôm nay đã tiêu 50k
        self.assertEqual(round(s["per_day"]), round(s["limit"] / 26))
        self.assertEqual(round(s["today_left"]), round(s["limit"] / 26 - 50_000))
        dubao = h.parts(ct.answer("/dubao", h.CLOCK["now"], h.CHAT))[0]
        self.assertEqual(spend_number(dubao), after)
        self.assertIn("theo kế hoạch chia lương: thu 19tr − trả nợ 2tr", dubao)
        tatca = h.parts(ct.answer("/dubao tatca", h.CLOCK["now"], h.CHAT))[0]
        self.assertEqual(spend_number(tatca), after)
        home = h.parts(menu.home(day))[0]
        self.assertEqual(spend_number(home), after)
        self.assertIn("VCB còn ~", home)
        plan = h.parts(kehoach.plan(day))[0]
        self.assertEqual(spend_number(plan), after)
        # trả nợ không làm giảm phần được tiêu (đã để riêng trong kế hoạch)
        h.say("trả nợ bác Vân 2tr")
        self.assertEqual(spend_number(h.parts(menu.home(day))[0]), after)

    def test_ngan_sach_tong_uu_tien_hon_ke_hoach(self):
        setup_month()
        h.say("/ngansach tổng 15tr")
        text, _ = h.say("cơm trưa 50k")
        s = kehoach.spendable(h.CLOCK["now"].date())
        self.assertEqual((s["basis"], s["limit"]), ("tong", 15_000_000))
        self.assertEqual(spend_number(text)[0], kehoach.approx(s["today_left"]))
        dubao = h.parts(ct.answer("/dubao", h.CLOCK["now"], h.CHAT))[0]
        self.assertIn("theo ngân sách tổng 15tr/tháng", dubao)

    def test_ngan_sach_hang_ngay_van_rieng(self):
        setup_month()
        h.say("/ngansach hằng ngày 6tr")
        text, _ = h.say("cơm trưa 50k")
        self.assertIn("Chi hằng ngày: hôm nay còn được tiêu", text)

    def test_chua_co_thu_nhap_thi_chi_goi_y(self):
        text, _ = h.say("cơm trưa 50k")
        self.assertNotIn("được tiêu", text)
        dubao = h.parts(ct.answer("/dubao", h.CLOCK["now"], h.CHAT))[0]
        self.assertIn("Ghi lương tháng này", dubao)

    def test_hoi_bang_cau_thuong(self):
        setup_month()
        h.say("cơm trưa 50k")
        h.AI.replies["hôm nay còn được tiêu bao nhiêu"] = {"viec": "xem", "man": "du_bao"}
        text, _ = h.say("hôm nay còn được tiêu bao nhiêu")
        self.assertIsNotNone(spend_number(text), text)


class ChuyenTien(unittest.TestCase):
    def setUp(self):
        h.reset()

    def test_chuyen_giua_hai_tai_khoan(self):
        set_main(20_000_000)
        before = net()
        h.AI.replies["rút 2tr tiền mặt"] = {"viec": "chuyen_tk", "den": "tiền mặt", "tien": 2_000_000}
        text, buttons = h.say("rút 2tr tiền mặt")
        self.assertIn("Chuyển 2.000.000đ từ VCB sang tiền mặt", text)
        _, body, _ = h.press(h.button(buttons, "y:ok:"))
        self.assertIn("(tài khoản mới)", body)
        self.assertEqual((main_balance(), item("tiền mặt")["tien"], net()), (18_000_000, 2_000_000, before))
        h.AI.replies["chuyển 500k từ tiền mặt sang VCB"] = {"viec": "chuyen_tk", "tu": "tiền mặt", "den": "VCB",
                                                           "tien": 500_000}
        _, buttons = h.say("chuyển 500k từ tiền mặt sang VCB")
        h.press(h.button(buttons, "y:ok:"))
        self.assertEqual((main_balance(), item("tiền mặt")["tien"], net()), (18_500_000, 1_500_000, before))

    def test_chua_co_tai_khoan_chinh_thi_hoi_tien_tu_dau(self):
        h.say("/taisan tien MoMo 3tr")
        h.say("/taisan tien VCB 10tr")
        h.AI.replies["chuyển 1tr sang MoMo"] = {"viec": "chuyen_tk", "den": "MoMo", "tien": 1_000_000}
        text, _ = h.say("chuyển 1tr sang MoMo")
        self.assertIn("từ tài khoản, ví nào", text)
        text, buttons = h.say("VCB")
        self.assertIn("từ VCB sang MoMo", text)
        h.press(h.button(buttons, "y:ok:"))
        self.assertEqual((item("VCB")["tien"], item("MoMo")["tien"]), (9_000_000, 4_000_000))

    def test_chuyen_vao_quy_cho_dau_tu(self):
        h.at(2026, 11, 13, 15)
        h.say("/dautu batdau 4tr VMEEF")
        set_main(20_000_000)
        before = net()
        h.AI.replies["để 4tr vào quỹ chờ"] = {"viec": "quy_cho", "tien": 4_000_000, "chieu": "nap"}
        text, buttons = h.say("để 4tr vào quỹ chờ")
        self.assertIn("Tiền từ VCB: còn ~16tr", text)
        _, body, _ = h.press(h.button(buttons, "y:ok:"))
        self.assertIn("Đã để 4.000.000đ vào quỹ chờ VMEEF", body)
        self.assertEqual((main_balance(), item("Quỹ chờ VMEEF")["tien"], net()), (16_000_000, 4_000_000, before))
        h.say("/duphong nap 1tr")
        h.say("/taisan tien MoMo 2tr")
        # chuyển từ ví khác vào quỹ dự phòng: trừ ví đó, không trừ tài khoản chính
        h.AI.replies["chuyển 1tr từ MoMo vào quỹ dự phòng"] = {"viec": "chuyen_tk", "tu": "MoMo", "den": "quỹ dự phòng",
                                                               "tien": 1_000_000}
        _, buttons = h.say("chuyển 1tr từ MoMo vào quỹ dự phòng")
        _, body, _ = h.press(h.button(buttons, "y:ok:"))
        self.assertIn("MoMo còn 1.000.000đ", body)
        self.assertEqual((main_balance(), item("Quỹ dự phòng")["tien"], item("MoMo")["tien"]),
                         (15_000_000, 2_000_000, 1_000_000))
        self.assertEqual(duphong.month_added("2026-11"), 2_000_000)


if __name__ == "__main__":
    unittest.main()
