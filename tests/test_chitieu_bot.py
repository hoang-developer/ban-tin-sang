"""Định tuyến bot chi tiêu: bảng lệnh, trả lời tin nhắn, lượt bấm nút của sổ chi tiêu."""
import unittest

from tests import harness as h

from infrastructure import ai as ai_client
from interface import common
from interface.chitieu import bot
from repositories.chitieu import groups as groups_repo
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


if __name__ == "__main__":
    unittest.main()
