"""Nhóm chi tự chỉnh ở tầng service: tạo nhóm, dùng lại nhóm ẩn, thêm từ khóa, xếp lại khoản ở Khác."""
import unittest

from tests import harness as h

from services.chitieu import groups


class NhomChi(unittest.TestCase):
    def setUp(self):
        h.reset()

    def test_tao_nhom_moi_va_tim_lai(self):
        self.assertIsNone(groups.find_group("trả nợ"))
        text = groups.nhom_them("Trả nợ")
        self.assertIn("Đã tạo nhóm", text)
        groups.reset()
        code = groups.find_group("trả nợ")
        self.assertTrue(code)
        self.assertEqual(groups.bare(groups.name(code)), "Trả nợ")
        self.assertIn("đã có", groups.nhom_them("Trả nợ"))

    def test_them_tu_khoa_va_gioi_han(self):
        self.assertEqual(groups.nhom_them(""), groups.NHOM_USAGE)
        text = groups.nhom_them("Thú cưng: cát mèo, hạt cho chó")
        self.assertIn("từ khóa: cát mèo, hạt cho chó", text)
        for i in range(groups.MAX_GROUPS):
            groups.nhom_them(f"Nhóm số {i}")
        self.assertIn(f"Đã có {groups.MAX_GROUPS} nhóm tự tạo", groups.nhom_them("Một nhóm nữa"))


if __name__ == "__main__":
    unittest.main()
