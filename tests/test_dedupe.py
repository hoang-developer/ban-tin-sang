"""Chống xử lý trùng: Telegram gửi lại một tin (cùng update_id), bấm đúp một nút; kho lỗi không được chặn nhầm tin thật."""
import io
import json
import unittest

from tests import harness as h

from api import chitieu as api_chitieu
from infrastructure import telegram as tg
from interface.chitieu import context as chitieu_ctx
from interface.chitieu import dedupe
from repositories import store
from repositories.chitieu import updates


class Kho(unittest.TestCase):
    def setUp(self):
        h.reset()

    def test_tin_chi_lam_mot_lan(self):
        self.assertTrue(updates.claim_update(100))
        self.assertFalse(updates.claim_update(100))  # Telegram gửi lại khi tin đang xử lý
        updates.finish_update(100)
        self.assertFalse(updates.claim_update(100))  # gửi lại muộn sau khi xong cũng bị chặn
        self.assertTrue(updates.claim_update(101))  # tin khác không bị ảnh hưởng

    def test_bam_dup_cung_nut_cung_tin(self):
        self.assertTrue(updates.claim_press(1, 55, "dc:ghi:1"))
        self.assertFalse(updates.claim_press(1, 55, "dc:ghi:1"))  # bấm lần hai ngay sau đó
        self.assertTrue(updates.claim_press(1, 55, "dc:xem"))  # nút khác trên cùng tin
        self.assertTrue(updates.claim_press(1, 56, "dc:ghi:1"))  # cùng nút trên tin khác
        self.assertTrue(updates.claim_press(2, 55, "dc:ghi:1"))  # chat khác

    def test_kho_loi_khong_chan_tin_that(self):
        real = store.put_new
        self.addCleanup(setattr, store, "put_new", real)
        store.put_new = lambda *args: (_ for _ in ()).throw(RuntimeError("kho lỗi"))
        self.assertTrue(updates.claim_update(7))
        self.assertTrue(updates.claim_update(7))  # không dấu được thì vẫn xử lý, kể cả lần gửi lại
        self.assertTrue(updates.claim_press(1, 2, "x"))

    def test_cua_vao(self):
        self.assertTrue(dedupe.start({"message": {}}))  # không có update_id: không chặn
        self.assertTrue(dedupe.start({"update_id": 5}))
        self.assertFalse(dedupe.start({"update_id": 5}))
        dedupe.finish({"update_id": 5})
        dedupe.finish({})  # không có update_id: không làm gì
        query = {"id": "q", "data": "bc:ngay", "message": {"message_id": 9, "chat": {"id": 1}}}
        self.assertFalse(dedupe.repeated_press(query))
        self.assertTrue(dedupe.repeated_press(query))
        self.assertFalse(dedupe.repeated_press({"id": "q", "message": {"message_id": 9}}))  # thiếu dữ liệu nút
        self.assertFalse(dedupe.repeated_press({"id": "q", "data": "x", "message": {}}))  # thiếu mã tin


class DauVao(unittest.TestCase):
    """Qua hàm WSGI thật của api/chitieu.py."""

    def setUp(self):
        h.reset()
        h.at(2026, 11, 20, 10)
        self.pressed = []
        for name, fake in (("call", lambda *a, **k: {}),
                           ("handle_button", lambda query, on_button, now, tok=None: self.pressed.append(query["data"]))):
            self.addCleanup(setattr, tg, name, getattr(tg, name))
            setattr(tg, name, fake)

    def post(self, update):
        body = json.dumps(update).encode()
        environ = {"REQUEST_METHOD": "POST", "CONTENT_LENGTH": str(len(body)), "wsgi.input": io.BytesIO(body),
                   "HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN": tg.derived_secret("webhook", chitieu_ctx.token())}
        status = []
        api_chitieu.app(environ, lambda s, headers: status.append(s))
        return status[0]

    def text(self, update_id, text):
        return {"update_id": update_id, "message": {"message_id": update_id, "chat": {"id": h.CHAT}, "text": text}}

    def test_telegram_gui_lai_tin_thi_khong_ghi_lan_hai(self):
        """Lỗi cũ: hàm chậm hơn thời gian chờ của Telegram thì tin được gửi lại và khoản bị ghi hai lần."""
        self.assertEqual(self.post(self.text(500, "cà phê 35k")), "200 OK")
        self.assertEqual(self.post(self.text(500, "cà phê 35k")), "200 OK")  # gửi lại cùng update_id
        self.assertEqual([(e["tien"], e["ghichu"]) for e in h.month_entries()], [(35_000, "cà phê")])
        self.assertEqual(len(h.SENT), 1)  # bot trả lời một lần

    def test_hai_tin_khac_nhau_cung_noi_dung_van_ghi_hai_khoan(self):
        self.post(self.text(501, "cà phê 35k"))
        self.post(self.text(502, "cà phê 35k"))  # người dùng thật sự nhắn hai lần
        self.assertEqual(len(h.month_entries()), 2)

    def test_bam_dup_va_nut_gui_lai(self):
        def press(update_id, data="bc:ngay", message_id=77):
            return {"update_id": update_id, "callback_query": {
                "id": f"cb{update_id}", "data": data,
                "message": {"message_id": message_id, "chat": {"id": h.CHAT}, "text": ""}}}
        self.post(press(600))
        self.post(press(601))  # bấm đúp: update khác nhưng cùng nút, cùng tin
        self.post(press(600))  # Telegram gửi lại lượt bấm đầu
        self.assertEqual(self.pressed, ["bc:ngay"])  # chỉ xử lý một lần
        self.post(press(602, data="bc:tuan"))  # nút khác vẫn chạy
        self.post(press(603, message_id=78))  # cùng nút trên tin khác vẫn chạy
        self.assertEqual(self.pressed, ["bc:ngay", "bc:tuan", "bc:ngay"])

    def test_sai_secret_van_bi_chan(self):
        body = b"{}"
        status = []
        api_chitieu.app({"REQUEST_METHOD": "POST", "CONTENT_LENGTH": "2", "wsgi.input": io.BytesIO(body),
                         "HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN": "sai"}, lambda s, headers: status.append(s))
        self.assertEqual(status, ["403 Forbidden"])


if __name__ == "__main__":
    unittest.main()
