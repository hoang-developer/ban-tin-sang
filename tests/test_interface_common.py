"""Phần dùng chung của lớp interface: chặn khi chưa nối kho, nhận biết tin có nút, bỏ nút đã bấm."""
import unittest

from tests import harness as h

from presentation.chitieu import view as cview
from infrastructure import kho
from interface import common


def message(text, rows):
    return {"text": text, "reply_markup": {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in row] for row in rows]}}


class Chung(unittest.TestCase):
    def setUp(self):
        h.reset()

    def test_chua_noi_kho_thi_tra_cau_huong_dan(self):
        calls = []

        @common.needs_store
        def work(x, y=1):
            """tài liệu"""
            calls.append((x, y))
            return x + y

        self.assertEqual(work(2, y=3), 5)
        real = kho.ready
        kho.ready = lambda: False
        try:
            self.assertEqual(work(2), cview.NEED_STORE)
            self.assertFalse(common.ready())
        finally:
            kho.ready = real
        self.assertEqual(calls, [(2, 3)])  # chưa nối kho: hàm không chạy
        self.assertEqual(work.__name__, "work")
        self.assertEqual(work.__doc__, "tài liệu")

    def test_tin_nam_tren_nut_nao(self):
        self.assertTrue(common.title_starts({"text": "📋 Chia lương"}, "🎯", "📋"))
        self.assertFalse(common.title_starts({"text": "🏠 Hôm nay"}, "🎯", "📋"))
        self.assertFalse(common.title_starts({}, "📋"))
        self.assertFalse(common.title_starts({"text": None}, "📋"))

    def test_bo_nut_da_bam(self):
        rows = [[("A", "dp:nap:1"), ("B", "dp:xem")], [("C", "dp:nap:2")], [("D", "no:xem")]]
        msg = message("x", rows)
        self.assertEqual(common.without_buttons(msg, "dp:nap"), [[("B", "dp:xem")], [("D", "no:xem")]])
        self.assertEqual(common.without_rows(msg, ("dp:nap:1",)), [[("C", "dp:nap:2")], [("D", "no:xem")]])
        self.assertEqual(common.without_rows(msg, ("dp:", "no:")), [])

    def test_cat_thong_bao(self):
        self.assertEqual(common.strip_tags("✅ <b>Trả</b> 5tr <i>xong</i>"), "✅ Trả 5tr xong")
        self.assertEqual(len(common.clip("x" * 500)), common.TOAST_MAX)
        self.assertEqual(common.clip("ngắn"), "ngắn")


if __name__ == "__main__":
    unittest.main()
