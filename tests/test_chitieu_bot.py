"""Định tuyến bot chi tiêu: bảng lệnh, trả lời tin nhắn, lượt bấm nút của sổ chi tiêu."""
import unittest

from tests import harness as h

from infrastructure import ai as ai_client
from interface import common
from interface.chitieu import bot
from repositories.chitieu import groups as groups_repo
from repositories.chitieu import ledger as ledger_repo
from services.chitieu import ledger


class Bang(unittest.TestCase):
    def test_bang_lenh(self):
        for name in ("baocao", "homnay", "tuan", "thang", "lichsu", "xoa", "ngansach", "nhom", "chuaxep", "taisan", "suckhoe", "luong",
                     "duphong", "no", "kehoach", "dautu", "tietkiem", "doichieu", "menu", "huongdan", "help", "hoi"):
            self.assertIn(name, bot.COMMANDS, name)
        self.assertIs(bot.COMMANDS["help"], bot.COMMANDS["huongdan"])
        self.assertEqual([m["command"] for m in bot.MENU], bot.VISIBLE)
        self.assertEqual(bot.period_kind([]), "thang")
        self.assertEqual((bot.period_kind(["10"]), bot.period_kind(["tuan"]), bot.period_kind(["homnay"])), ("10", "tuan", "ngay"))

    def test_nut_cua_tin(self):
        message = {"reply_markup": {"inline_keyboard": [[{"text": "a", "callback_data": "doi:2026-10:3"}, {"text": "b", "callback_data": "m:home"}]]}}
        self.assertEqual(common.keyboard_rows(message), [[("a", "doi:2026-10:3"), ("b", "m:home")]])
        self.assertTrue(common.from_menu(message))
        self.assertFalse(common.from_menu({}))
        self.assertEqual(bot.refs_in(message), ["2026-10:3"])


class Tra(unittest.TestCase):
    def setUp(self):
        h.reset()
        h.at(2026, 10, 20, 10)
        real_ai = ai_client.chat
        self.addCleanup(lambda: setattr(ai_client, "chat", real_ai))
        ai_client.chat = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("bận"))
        self.now = h.CLOCK["now"]

    def test_ghi_khoan_va_lenh(self):
        text, rows = bot.respond("cà phê 35k", self.now)
        self.assertIn("✅ Đã ghi <b>35.000đ</b> · 🍜 Ăn uống — cà phê", text)
        self.assertTrue(any("xoa:" in b[1] for r in rows for b in r))
        self.assertIn("Không thấy số tiền", bot.record_text("hôm nay trời đẹp", self.now))
        self.assertIn("Không có lệnh /zzz", bot.respond("/zzz", self.now))
        self.assertIn("Chi tiêu tháng 10/2026", bot.respond("/baocao", self.now)[0])

    def test_nut_doi_nhom_giu_xoa(self):
        entries = ledger.add("xyz lạ 15k", self.now)
        reference = f"2026-10:{entries[0]['id']}"
        message = {"text": "x"}
        toast, action = bot.on_button(f"doi:{reference}", message, self.now)
        self.assertEqual(toast, "Chọn nhóm đúng cho khoản này")
        toast, action = bot.on_button(f"nhom:{reference}:xe", message, self.now)
        self.assertIn("Đã chuyển sang 🛵 Đi lại", toast)
        self.assertEqual(ledger.find(reference)["nhom"], "xe")
        self.assertIn("Nhóm này không còn", bot.on_button(f"nhom:{reference}:zzz", message, self.now)[0])
        toast, _ = bot.on_button(f"xoa:{reference}", message, self.now)
        self.assertEqual(toast, "Đã xóa")
        self.assertEqual(bot.on_button(f"xoa:{reference}", message, self.now)[0], "Khoản này đã xóa rồi")
        self.assertEqual(bot.on_button("zzz:1", message, self.now), (None, None))

    def test_nut_bao_cao_va_nhom_do_ai_doan(self):
        ledger.add("cà phê 35k", self.now)
        kind, action = bot.on_button("bc:ngay", {"text": ""}, self.now)[1]
        self.assertEqual(kind, "edit")
        text, rows = action()
        self.assertIn("Chi tiêu hôm nay", text)
        guessed = ledger.add("món lạ hoắc 70k", self.now)[0]
        guessed.update(ai=True, nhom="an")
        from repositories.chitieu import ledger as repo
        repo.save(guessed)
        reference = f"2026-10:{guessed['id']}"
        bot.on_button(f"nhom:{reference}:xe", {"text": ""}, self.now)
        self.assertEqual(groups_repo.ai_stats()[1], 1)  # sửa lại nhóm AI đoán: tính là AI đoán sai

    def test_chua_noi_kho(self):
        real = bot.common.ready
        bot.common.ready = lambda: False
        try:
            self.assertEqual(bot.respond("cà phê 35k", self.now), bot.NEED_STORE)
            self.assertEqual(bot.on_button("bc:ngay", {}, self.now), ("Chưa có kho dữ liệu", None))
        finally:
            bot.common.ready = real


def entries_of(ym):
    return [(e["ngay"], e["tien"], e["ghichu"]) for e in ledger_repo.load(ym)]


class NgayChuaRo(unittest.TestCase):
    """"27/11" nhắn ngày 20/11: hỏi khoản sắp tới hay của năm trước, không im lặng lùi về năm trước như cũ."""

    def setUp(self):
        h.reset()
        h.at(2026, 11, 20, 10)

    def choice(self, buttons, option):
        return next(b for b in buttons if b.endswith(f":{option}"))

    def test_hoi_truoc_khi_ghi(self):
        text, buttons = h.say("27/11 đóng học 3tr")
        self.assertIn("27/11 chưa tới (hôm nay 20/11/2026). Đây là khoản sắp tới hay của năm trước?", text)
        self.assertEqual(sorted(b.rsplit(":", 1)[1] for b in buttons if b.startswith("y:chi:")), ["nay", "toi", "trc"])
        self.assertTrue(any(b.startswith("y:huy:") for b in buttons))
        self.assertEqual((entries_of("2026-11"), entries_of("2025-11")), ([], []))  # chưa ghi gì

    def test_chon_sap_toi_ghi_dung_thang(self):
        _, buttons = h.say("27/11 đóng học 3tr")
        _, done, _ = h.press(self.choice(buttons, "toi"))
        self.assertIn("Đã ghi 3.000.000đ", done)
        self.assertEqual((entries_of("2026-11"), entries_of("2025-11")), ([("2026-11-27", 3_000_000, "đóng học")], []))

    def test_chon_nam_truoc(self):
        _, buttons = h.say("27/11 đóng học 3tr")
        _, done, _ = h.press(self.choice(buttons, "trc"))
        self.assertIn("27/11/2025", done)  # khác năm nay thì tin báo ghi rõ năm
        self.assertEqual((entries_of("2026-11"), entries_of("2025-11")), ([], [("2025-11-27", 3_000_000, "đóng học")]))

    def test_chon_hom_nay_va_khong_ghi(self):
        _, buttons = h.say("27/11 đóng học 3tr")
        h.press(self.choice(buttons, "nay"))
        self.assertEqual(entries_of("2026-11"), [("2026-11-20", 3_000_000, "đóng học")])
        _, buttons = h.say("28/11 mua sách 200k")
        h.press(h.button(buttons, "y:huy:"))
        self.assertEqual(len(entries_of("2026-11")), 1)

    def test_ngay_xa_hoac_ro_van_ghi_ngay(self):
        text, _ = h.record("27/12 đóng học 3tr")  # 37 ngày nữa: xa, năm trước, ghi rõ năm
        self.assertIn("27/12/2025", text)
        self.assertEqual(entries_of("2025-12"), [("2025-12-27", 3_000_000, "đóng học")])
        h.record("27/11/2026 mua sách 200k")  # đã ghi năm: không hỏi năm, nhưng ngày chưa tới nên xác nhận (risk)
        h.say("hôm qua phở 50k")
        h.say("tối qua ăn lẩu 300k")  # buổi của hôm qua
        self.assertEqual(sorted(entries_of("2026-11")), [("2026-11-19", 50_000, "phở"), ("2026-11-19", 300_000, "ăn lẩu"),
                                                         ("2026-11-27", 200_000, "mua sách")])

    def test_the_cu_het_han_va_nhieu_dong(self):
        text, buttons = h.say("cà phê 35k\n27/11 đóng học 3tr")
        self.assertEqual(entries_of("2026-11"), [])  # cả tin chờ chọn ngày
        h.press(self.choice(buttons, "toi"))
        self.assertEqual(sorted(entries_of("2026-11")), [("2026-11-20", 35_000, "cà phê"), ("2026-11-27", 3_000_000, "đóng học")])
        self.assertEqual(h.press(self.choice(buttons, "toi"))[0], "Thẻ này đã xử lý hoặc hết hạn")


class HocNhom(unittest.TestCase):
    """Cụm bot học từ lần sửa nhóm: cụm 1 chữ chỉ khớp cả ghi chú; xem và xóa bằng /nhom hoc."""

    def setUp(self):
        h.reset()
        h.at(2026, 11, 20, 10)

    def teach(self, note, code):
        entry = ledger.add(f"{note} 150k", h.CLOCK["now"])[0]
        h.press(f"nhom:2026-11:{entry['id']}:{code}")

    def test_hoc_bo_khong_keo_theo_pho_bo(self):
        self.teach("bò", "cho")
        self.assertIn("Đi chợ", h.say("bò 20k")[0])
        for note in ("phở bò", "bún bò", "bò bía"):
            text, _ = h.say(f"{note} 40k")
            self.assertNotIn("Đi chợ", text, note)

    def test_xem_va_xoa_cum_da_hoc(self):
        self.assertIn("chưa học cụm nào", h.say("/nhom hoc")[0])
        self.teach("bò", "cho")
        self.teach("đóng họ", "qua")
        text, _ = h.say("/nhom hoc")
        self.assertIn("Cụm bot đã học", text)
        self.assertIn("(2)", text)
        self.assertIn("🛒 Đi chợ, siêu thị: bò", text)
        self.assertIn("🎁 Hiếu hỷ, quà tặng: đóng họ", text)
        self.assertIn("Đã bỏ cụm bò", h.say("/nhom hoc xoa bò")[0])
        self.assertNotIn("Đi chợ", h.say("bò 20k")[0])  # không còn nhóm đã học
        self.assertIn("Không thấy cụm «bò»", h.say("/nhom hoc xoa bò")[0])
        self.assertIn("Bỏ cụm học nhầm", h.say("/nhom hoc xoa")[0])
        self.assertIn("Đã bỏ cụm đóng họ", h.say("/nhom hoc bo Đóng Họ")[0])  # gõ khác hoa thường vẫn xóa được
        self.assertIn("chưa học cụm nào", h.say("/nhom hoc")[0])


if __name__ == "__main__":
    unittest.main()
