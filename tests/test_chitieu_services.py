"""Sổ thu chi: ghi nhiều dòng, nhớ nhóm, xếp lại khoản ở Khác, AI xếp nhóm và tình trạng AI."""
import os
import unittest
from datetime import date

from tests import harness as h

from domain.chitieu import learn as learn_rules
from infrastructure import ai as ai_client
from repositories.chitieu import groups as groups_repo
from repositories.chitieu import ledger as ledger_repo
from services.chitieu import ai_sort, ledger


class Hoc(unittest.TestCase):
    def test_khoa_ghi_nho_bo_so_va_ngay(self):
        self.assertEqual(learn_rules.learn_key("tiền đổ rác tháng 11"), "tiền đổ rác")
        self.assertEqual(learn_rules.learn_key("ăn 12/10"), "ăn")
        self.assertEqual(learn_rules.learn_key("a"), "a")  # quá ngắn: giữ nguyên
        self.assertEqual(learn_rules.learn_key("đóng họ lần 3"), "đóng họ")

    def test_gop_cum_da_hoc(self):
        got = learn_rules.merge_learned({"a": "an", "b": "xe"}, [("a", "cho"), ("c", "nha")])
        self.assertEqual(list(got.items()), [("b", "xe"), ("a", "cho"), ("c", "nha")])  # cặp mới nhất ở cuối
        many = learn_rules.merge_learned({}, [(f"k{i}", "an") for i in range(learn_rules.MAX_LEARNED + 5)])
        self.assertEqual((len(many), "k4" in many, f"k{learn_rules.MAX_LEARNED + 4}" in many), (learn_rules.MAX_LEARNED, False, True))

    def test_khoan_cho_hoi_nhom(self):
        self.assertTrue(learn_rules.pending({"nhom": "khac"}))
        self.assertFalse(learn_rules.pending({"nhom": "khac", "dekhac": True}))
        self.assertFalse(learn_rules.pending({"nhom": "an"}))


class So(unittest.TestCase):
    def setUp(self):
        h.reset()
        h.at(2026, 10, 20, 10)
        self.now = h.CLOCK["now"]
        self.replies = []
        real_ai = ai_client.chat
        self.addCleanup(setattr, ai_client, "chat", real_ai)
        ai_client.chat = self.ask

    def ask(self, system, user, **kw):
        self.replies.append(user)
        return '{"1": "xe", "2": "qua"}', "m-ai"

    def test_ghi_nhieu_dong(self):
        got = ledger.add("cà phê 35k\ngrab 50k #xe\nkhông có tiền\n+lương 25tr", self.now)
        self.assertEqual([(e["ghichu"], e["nhom"], e["id"]) for e in got], [("cà phê", "an", 1), ("grab", "xe", 2), ("lương", "thu", 3)])
        self.assertTrue(all(e["gio"] == "10:00" for e in got))
        self.assertEqual(len(ledger_repo.load("2026-10")), 3)
        self.assertEqual(self.replies, [])  # đều đã có nhóm: không hỏi AI

    def test_chon_nhom_thi_hoc_lan_sau(self):
        ledger.add("đóng họ 1tr #quà", self.now)
        self.assertEqual(groups_repo.learned(), {"đóng họ": "qua"})
        self.assertEqual(ledger.add("đóng họ 2tr", self.now)[0]["nhom"], "qua")

    def test_ai_xep_khoan_la_va_nho_cau_tra_loi(self):
        got = ledger.add("thay má phanh 300k\nsơn móng zzz 100k", self.now)
        self.assertEqual([(e["nhom"], e.get("ai")) for e in got], [("xe", True), ("qua", True)])
        self.assertEqual(len(self.replies), 1)
        self.assertEqual(groups_repo.ai_stats(), (2, 0))
        again = ledger.add("thay má phanh 200k", self.now)
        self.assertEqual((again[0]["nhom"], len(self.replies)), ("xe", 1))  # nhớ: không hỏi lại

    def test_ai_loi_thi_de_o_khac(self):
        ai_client.chat = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("bận"))
        got = ledger.add("món lạ hoắc 70k", self.now)
        self.assertEqual(got[0]["nhom"], "khac")
        ledger.learn("món lạ hoắc", "choi")
        self.assertEqual(ledger.tidy(date(2026, 10, 20)), 1)
        self.assertEqual(ledger_repo.load("2026-10")[0]["nhom"], "choi")
        self.assertEqual(ledger.tidy(date(2026, 10, 20)), 0)

    def test_khong_co_key_thi_khong_hoi_ai(self):
        saved = os.environ.pop("GEMINI_API_KEY")
        self.addCleanup(os.environ.__setitem__, "GEMINI_API_KEY", saved)
        self.assertEqual(ledger.add("món lạ 10k", self.now)[0]["nhom"], "khac")
        self.assertEqual(self.replies, [])
        self.assertIn("tắt", ai_sort.ai_status())
        self.assertEqual(ai_sort.quota_text(), "")

    def test_khoan_gan_day(self):
        ledger.add("cà phê 35k", self.now)
        h.at(2026, 11, 2, 9)
        ledger.add("ăn trưa 50k", h.CLOCK["now"])
        got = ledger.recent(date(2026, 11, 2), 5)
        self.assertEqual([e["ghichu"] for e in got], ["ăn trưa", "cà phê"])  # tháng này và tháng trước, mới nhất trước
        self.assertEqual(len(ledger.recent(date(2026, 11, 2), 1)), 1)

    def test_tinh_trang_ai(self):
        text = ai_sort.ai_status()
        self.assertIn("AI xếp nhóm: bật, thử lần lượt Gemini", text)
        self.assertIn("🛵 Đi lại", ai_sort.ai_status(test=True))
        ai_client.chat = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("hết lượt"))
        self.assertIn("LỖI – ", ai_sort.ai_status(test=True))

    def test_lenh_ai(self):
        prompt = ai_sort.ai_prompt({"cà phê": "an", "x": "zzz"})
        self.assertIn("an: Ăn uống", prompt)
        self.assertIn("cà phê -> an", prompt)
        self.assertNotIn("x -> zzz", prompt)  # nhóm đã học không còn dùng thì bỏ
        self.assertNotIn("thu:", prompt)  # khoản thu không để AI xếp


if __name__ == "__main__":
    unittest.main()


class TraNoDongThe(unittest.TestCase):
    """Tiền trả nợ, đóng thẻ tín dụng không được AI xếp nhầm vào nhà cửa và không tính là chi thiết yếu."""

    def setUp(self):
        h.reset()
        h.at(2026, 11, 18, 9)
        self.real = ai_client.chat
        self.addCleanup(lambda: setattr(ai_client, "chat", self.real))

    def test_nhan_ra_ghi_chu_tra_no(self):
        from domain.chitieu import classify
        for note in ("thanh toán nợ vay", "đóng thẻ tín dụng lpbank", "Thanh toán thẻ VPBank", "trả góp tủ lạnh",
                     "thanh toán shopeepay", "dong the tin dung", "trả nợ bác Vân"):
            self.assertTrue(classify.is_debt_payment(note), note)
        for note in ("tiền nhà tháng 11", "tiền điện", "phở bò", "mua thẻ cào", "trả tiền điện"):
            self.assertFalse(classify.is_debt_payment(note), note)

    def test_ai_khong_xep_tra_no_vao_nha_cua(self):
        ai_client.chat = lambda *a, **k: ('{"1": "nha", "2": "nha"}', "m")
        entries = ledger.add("đóng thẻ tín dụng lpbank 440k\nthanh toán nợ vay 4tr39", h.CLOCK["now"])
        self.assertEqual([e["nhom"] for e in entries], ["khac", "khac"])
        self.assertFalse(any(e.get("ai") for e in entries))

    def test_tidy_dua_khoan_ai_xep_nham_ve_khac(self):
        e = {"id": ledger_repo.next_id(), "ngay": "2026-11-05", "tien": 4_390_000, "ghichu": "thanh toán nợ vay", "nhom": "nha",
             "ai": True}
        ledger_repo.save(e)
        mine = {"id": ledger_repo.next_id(), "ngay": "2026-11-06", "tien": 440_000, "ghichu": "đóng thẻ", "nhom": "nha"}  # người dùng tự chọn
        ledger_repo.save(mine)
        ledger.tidy(h.CLOCK["now"].date())
        saved = {x["id"]: x for x in ledger_repo.load("2026-11")}
        self.assertEqual(saved[e["id"]]["nhom"], "khac")
        self.assertNotIn("ai", saved[e["id"]])
        self.assertEqual(saved[mine["id"]]["nhom"], "nha")  # khoản người dùng tự chọn thì giữ nguyên
