"""Xếp nhóm và đọc dòng chi tiêu (domain thuần, cấu hình nhóm truyền vào) và kho cấu hình nhóm."""
import unittest
from datetime import date

from tests import harness as h

from domain.chitieu import classify, parse
from domain.chitieu.categories import CATEGORIES, KEYWORDS
from domain.chitieu.kinds import INCOME, OTHER
from repositories.chitieu import groups as groups_repo

CFG = {"moi": ["tuthien"], "ten": {"tuthien": "💝 Từ thiện"}, "tu": {"tuthien": ["quyên góp"], "xe": ["thay má phanh"]},
       "an": ["choi"], "dem": 1}
DAY = date(2026, 10, 20)


class Nhom(unittest.TestCase):
    def test_bang_nhom(self):
        self.assertEqual(CATEGORIES["an"][0], "🍜 Ăn uống")
        self.assertTrue(KEYWORDS)
        active = classify.groups({})
        self.assertEqual(list(active)[-2:], [OTHER, INCOME])
        mine = classify.groups(CFG)
        self.assertNotIn("choi", mine)  # nhóm ẩn
        self.assertIn("tuthien", mine)
        self.assertEqual(mine["tuthien"][:2], ("💝 Từ thiện", ["quyên góp"]))

    def test_cum_da_hoc_mot_chu_chi_khop_ca_ghi_chu(self):
        """Lỗi cũ: học "bò" thành Đi chợ thì "phở bò", "bún bò" cũng thành Đi chợ."""
        learned = {"bò": "cho", "mua": "giadinh", "bún bò": "cho"}
        self.assertEqual(classify.classify("bò", learned, {}), "cho")
        self.assertEqual(classify.classify("bò 2", learned, {}), "cho")  # số, dấu câu quanh cụm vẫn tính là cụm đó
        self.assertEqual(classify.classify("bo", learned, {}), "cho")  # gõ không dấu
        self.assertNotEqual(classify.classify("phở bò", learned, {}), "cho")
        self.assertNotEqual(classify.classify("bò bía", learned, {}), "cho")
        self.assertNotEqual(classify.classify("mua áo", learned, {}), "giadinh")
        self.assertEqual(classify.classify("mua", learned, {}), "giadinh")
        self.assertEqual(classify.classify("bún bò huế", learned, {}), "cho")  # cụm 2 chữ khớp trong câu dài
        self.assertEqual(classify.classify("ăn bún bò", learned, {}), "cho")

    def test_ten_nhom(self):
        self.assertEqual(classify.name("an", {}), "🍜 Ăn uống")
        self.assertEqual(classify.name("tuthien", CFG), "💝 Từ thiện")
        self.assertEqual(classify.name("choi", CFG), "🎬 Giải trí, du lịch")  # nhóm ẩn vẫn giữ tên
        self.assertEqual(classify.name("zzz", {}), "📦 Khác")
        self.assertEqual(classify.bare("🍜 Ăn uống"), "Ăn uống")

    def test_xep_nhom(self):
        cases = {"cà phê": "an", "ca phe": "an", "chợ 300k": "cho", "cho Lan 200k": "khac", "cho be": "giadinh", "grab": "xe",
                 "tiền nước": "nha", "lương": "thu", "thay má phanh": "khac"}
        for note, code in cases.items():
            self.assertEqual(classify.classify(note, None, {}), code, note)
        self.assertEqual(classify.classify("thay má phanh", None, CFG), "xe")  # từ khóa tự thêm
        self.assertEqual(classify.classify("quyên góp 100k", None, CFG), "tuthien")
        self.assertEqual(classify.classify("cà phê", {"cà phê": "cho"}, {}), "cho")  # cụm đã học thắng từ khóa
        self.assertEqual(classify.classify("cà phê", {"cà phê": "ko"}, {}), "an")  # học nhóm không còn: bỏ qua

    def test_tim_nhom_theo_ten(self):
        for text, code in (("ăn uống", "an"), ("di lai", "xe"), ("ăn", "an"), ("từ thiện", "tuthien")):
            self.assertEqual(classify.find_group(text, CFG), code, text)
        self.assertIsNone(classify.find_group("", CFG))
        self.assertIsNone(classify.find_group("!!!", CFG))
        self.assertIsNone(classify.find_group("giải trí", CFG))  # nhóm ẩn
        self.assertEqual(classify.find_group("giải trí", CFG, include_hidden=True), "choi")


class DocTin(unittest.TestCase):
    def test_ngay(self):
        self.assertEqual(parse.parse_date("hôm qua cà phê 35k", DAY)[0], date(2026, 10, 19))
        self.assertEqual(parse.parse_date("hom qua cafe", DAY)[0], date(2026, 10, 19))
        self.assertEqual(parse.parse_date("02/11 ăn", DAY)[0], date(2025, 11, 2))  # tương lai thì là năm trước
        self.assertEqual(parse.parse_date("01/05/24", DAY)[0], date(2024, 5, 1))
        self.assertEqual(parse.parse_date("31/2 x", DAY)[0], DAY)  # ngày sai: dùng hôm nay
        self.assertEqual(parse.parse_date("cà phê", DAY)[0], DAY)

    def test_buoi_cua_hom_qua(self):
        """"tối qua", "đêm qua"... là buổi của hôm qua (lỗi cũ: ghi vào hôm nay, nhất là lúc sau nửa đêm)."""
        for text in ("tối qua ăn lẩu 300k", "đêm qua taxi về 120k", "sáng qua phở 40k", "chiều qua trà sữa 45k",
                     "trưa qua cơm 50k", "toi qua an lau 300k", "dem qua taxi 120k"):
            self.assertEqual(parse.parse_date(text, DAY)[0], date(2026, 10, 19), text)
        e = parse.parse_line("tối qua ăn lẩu 300k", DAY, None, {})
        self.assertEqual((e["ngay"], e["ghichu"], e["tien"]), ("2026-10-19", "ăn lẩu", 300_000))

    def test_ngay_chua_ro(self):
        """"dd/mm" sau hôm nay trong 31 ngày tới: chưa rõ khoản sắp tới hay của năm trước (lỗi cũ: im lặng lùi năm trước)."""
        self.assertEqual(parse.vague_date("27/10 đóng học 3tr", DAY), (date(2026, 10, 27), date(2025, 10, 27), "27/10"))
        self.assertEqual(parse.vague_date("02/11 ăn 50k", DAY)[:2], (date(2026, 11, 2), date(2025, 11, 2)))
        self.assertIsNone(parse.vague_date("27/12 đóng học 3tr", DAY))  # 68 ngày nữa: xa, vẫn là năm trước
        self.assertIsNone(parse.vague_date("19/10 ăn 50k", DAY))  # đã qua
        self.assertIsNone(parse.vague_date("20/10 ăn 50k", DAY))  # hôm nay
        self.assertIsNone(parse.vague_date("27/10/2026 đóng học 3tr", DAY))  # đã ghi năm
        self.assertIsNone(parse.vague_date("hôm qua 27/10 đóng học 3tr", DAY))  # chữ "hôm qua" thắng
        self.assertIsNone(parse.vague_date("31/2 x", DAY))  # ngày sai
        self.assertIsNone(parse.vague_date("cà phê 35k", DAY))
        self.assertEqual(parse.first_vague_date("cà phê 35k\n27/10 đóng học 3tr", DAY)[2], "27/10")
        self.assertIsNone(parse.first_vague_date("cà phê 35k\năn 50k", DAY))

    def test_chon_ngay_chua_ro(self):
        text = "27/10 đóng học 3tr"
        self.assertEqual(parse.resolve_vague(text, "toi", DAY), "27/10/2026 đóng học 3tr")
        self.assertEqual(parse.resolve_vague(text, "trc", DAY), "27/10/2025 đóng học 3tr")
        self.assertEqual(parse.resolve_vague(text, "nay", DAY), "hôm nay đóng học 3tr")
        self.assertEqual(parse.resolve_vague("cà phê 35k\n" + text, "toi", DAY), "cà phê 35k\n27/10/2026 đóng học 3tr")
        self.assertEqual(parse.parse_date(parse.resolve_vague(text, "toi", DAY), DAY)[0], date(2026, 10, 27))
        self.assertEqual(parse.parse_date(parse.resolve_vague(text, "trc", DAY), DAY)[0], date(2025, 10, 27))
        self.assertEqual(parse.parse_date(parse.resolve_vague(text, "nay", DAY), DAY)[0], DAY)

    def test_the_nhom(self):
        self.assertEqual(parse.read_tag("cà phê 35k", {}), (None, None, "cà phê 35k"))
        self.assertEqual(parse.read_tag("đóng họ 1tr #tiết kiệm", {})[0:2], (None, "tiết kiệm"))
        self.assertEqual(parse.read_tag("grab 50k #xe", {})[0], "xe")
        self.assertEqual(parse.read_tag("10k #từ thiện quà", CFG)[0], "tuthien")
        self.assertEqual(parse.read_tag("20k #cafe", {})[0], "an")  # cuối dòng, là từ khóa của một nhóm
        self.assertEqual(parse.read_tag("#cafe 20k", {})[0:2], (None, "cafe"))  # giữa câu thì phải trùng tên nhóm

    def test_dong_chi_tieu(self):
        e = parse.parse_line("cà phê 35k", DAY, None, {})
        self.assertEqual((e["tien"], e["ghichu"], e["nhom"], e["ngay"]), (35_000, "cà phê", "an", "2026-10-20"))
        self.assertEqual(parse.parse_line("+lương 25tr", DAY, None, {})["nhom"], INCOME)
        self.assertIsNone(parse.parse_line("không số tiền", DAY, None, {}))
        chosen = parse.parse_line("grab 50k #xe", DAY, None, {})
        self.assertEqual((chosen["nhom"], chosen["_chon"]), ("xe", True))
        other = parse.parse_line("đồ lạ 5k #khác", DAY, None, {})
        self.assertEqual((other["nhom"], other.get("dekhac")), ("khac", True))
        self.assertEqual(parse.parse_line("x 10k #nhómlạ", DAY, None, {})["_tag"], "nhómlạ")  # nhắc tạo nhóm
        self.assertEqual(parse.parse_line("đóng họ 1tr", DAY, {"đóng họ": "qua"}, {})["nhom"], "qua")
        self.assertEqual(parse.parse_line("cà phê hôm qua 35k", DAY, None, {})["ngay"], "2026-10-19")


class KhoCauHinh(unittest.TestCase):
    def setUp(self):
        h.reset()

    def test_luu_va_xoa_cau_ai(self):
        self.assertEqual(groups_repo.load(), {})
        groups_repo.save_ai_cache({"cà phê": "an"})
        self.assertEqual(groups_repo.ai_cache(), {"cà phê": "an"})
        groups_repo.save(CFG)
        self.assertEqual(groups_repo.load(), CFG)
        self.assertEqual(groups_repo.ai_cache(), {})  # nhóm đã khác: câu AI cũ không còn đúng

    def test_dem_khoan_ai_xep(self):
        self.assertEqual(groups_repo.ai_stats(), (0, 0))
        groups_repo.add_ai_guessed(3)
        groups_repo.add_ai_guessed(2)
        self.assertEqual(groups_repo.ai_stats(), (5, 0))


if __name__ == "__main__":
    unittest.main()
