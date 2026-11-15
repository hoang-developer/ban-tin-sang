"""Lệnh /baocao /thang /lichsu /xoa /ngansach /nhom /chuaxep /xuat gọi thẳng module lệnh; đọc lệnh tự chỉnh nhóm (thuần)."""
import unittest
from datetime import date

from tests import harness as h

import sochitieu as ct
from domain.chitieu import classify, labels
from infrastructure import ai as ai_client
from interface.chitieu import commands
from repositories.chitieu import budget as budget_repo
from services.chitieu import ledger

DAY = date(2026, 10, 20)


class DocLenh(unittest.TestCase):
    def test_tach_ten_va_tu_khoa(self):
        self.assertEqual(labels.split_spec("Ăn uống: bún chả, bánh tráng"), ("Ăn uống", ["bún chả", "bánh tráng"]))
        self.assertEqual(labels.split_spec("Học"), ("Học", []))
        self.assertEqual(labels.split_spec("A: x;y\nz")[1], ["x", "y", "z"])
        self.assertEqual(labels.split_spec("A: " + "x" * 50)[1], [])  # từ khóa quá dài bỏ

    def test_ten_nhom_co_bieu_tuong(self):
        self.assertEqual(labels.make_label("🏦 Trả nợ"), "🏦 Trả nợ")
        self.assertEqual(labels.make_label("Trả nợ"), "🏷️ Trả nợ")
        self.assertEqual(labels.make_label("Mới", "🚗 Cũ"), "🚗 Mới")
        self.assertIsNone(labels.make_label(""))
        self.assertNotIn("<", labels.make_label("<b>x</b>"))
        self.assertLessEqual(len(labels.make_label("A" * 60)), 45)

    def test_tim_nhom_cho_ngan_sach(self):
        for text, code in (("ăn uống", "an"), ("tổng", "tong"), ("tat ca", "tong"), ("hàng ngày", "hangngay"), ("di lai", "xe")):
            self.assertEqual(classify.find_category(text, {}), code, text)
        self.assertIsNone(classify.find_category("zzz", {}))


class Lenh(unittest.TestCase):
    def setUp(self):
        h.reset()
        h.at(2026, 10, 20, 10)
        self.now = h.CLOCK["now"]
        real_ct, real_ai = ct.ai_chat, ai_client.chat
        self.addCleanup(lambda: (setattr(ct, "ai_chat", real_ct), setattr(ai_client, "chat", real_ai)))
        ai_client.chat = ct.ai_chat = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("bận"))
        ledger.add("cà phê 35k\ngrab 80k\nxyz lạ 15k\nlương 20tr", self.now)

    def test_bao_cao(self):
        text, buttons = commands.baocao([])
        self.assertIn("Chi tiêu tháng 10/2026", text)
        self.assertIs(buttons, commands.REPORT_BUTTONS)
        self.assertIn("hôm nay", commands.baocao(["homnay"])[0])
        self.assertIn("tuần này", commands.baocao(["tuan"])[0])
        self.assertIn("tháng 9/2026", commands.thang(["9"])[0])
        self.assertIn("tháng 10/2026", commands.thang(["abc"])[0])

    def test_lich_su_va_xoa(self):
        text, rows = commands.lichsu([])
        self.assertIn("🧾 <b>10 khoản gần nhất</b>", text)
        self.assertEqual(rows[0][0][1].split(":")[0], "xls")
        last = ledger.recent(DAY, 1)[0]
        self.assertEqual(commands.delete(f"2026-10:{last['id']}")["id"], last["id"])
        self.assertIsNone(commands.delete(f"2026-10:{last['id']}"))  # xóa lại: đã xóa từ trước
        self.assertIn("🗑 Đã xóa:", commands.xoa_cuoi([]))
        h.reset()
        h.at(2026, 10, 20, 10)
        self.assertIn("Chưa có khoản nào", commands.lichsu([]))
        self.assertIn("Chưa có khoản nào", commands.xoa_cuoi([]))

    def test_ngan_sach(self):
        self.assertIn("Đặt ngân sách tháng", commands.ngansach([]))
        self.assertIn("🎯 Ngân sách 🍜 Ăn uống: 3.000.000đ/tháng", commands.ngansach(["ăn", "uống", "3tr"]))
        self.assertEqual(budget_repo.load()["an"], 3_000_000)
        self.assertIn("🎯 <b>Ngân sách tháng này</b>", commands.ngansach([]))
        self.assertIn("Đã bỏ ngân sách", commands.ngansach(["ăn", "uống", "0"]))
        self.assertNotIn("an", budget_repo.load())
        self.assertIn("Đặt ngân sách tháng", commands.ngansach(["zzz", "1tr"]))
        self.assertIn("Đặt ngân sách tháng", commands.ngansach(["thu", "nhập", "1tr"]))  # nhóm thu nhập không có ngân sách

    def test_nhom_tu_chinh(self):
        self.assertIn("✅ Đã tạo nhóm 🏦 Trả nợ", commands.nhom_cmd(["them", "🏦", "Trả", "nợ:", "trả", "nợ,", "trả", "góp"]))
        self.assertIn("🏦 Trả nợ (nhóm bạn tạo)", commands.nhom_cmd([]))
        self.assertIn("đã có", commands.nhom_cmd(["them", "Ăn", "uống"]))
        self.assertIn("thêm từ khóa", commands.nhom_cmd(["tukhoa", "Ăn", "uống:", "bún", "chả"]))
        self.assertIn("Nhóm Khác dành cho", commands.nhom_cmd(["tukhoa", "Khác:", "abc"]))
        self.assertIn("Đã đổi", commands.nhom_cmd(["doiten", "Đi", "lại:", "🚗", "Xe", "cộ"]))
        self.assertIn("Đã ẩn nhóm", commands.nhom_cmd(["xoa", "Học", "tập"]))
        self.assertIn("Không ẩn được", commands.nhom_cmd(["xoa", "Khác"]))
        self.assertIn("Bot đã học", commands.nhom_cmd([]))
        for i in range(21):
            commands.nhom_them(f"Nhóm số {i}: tu{i}")
        self.assertIn("Đã có 20 nhóm tự tạo", commands.nhom_them("Thêm nữa: x"))

    def test_chua_xep_va_xuat(self):
        text, rows = commands.chuaxep([])
        self.assertIn("chưa rõ nhóm", text)
        ai_client.chat = lambda system, user, **kw: ('{"1": "xe"}', "m")
        text, _ = commands.chuaxep([])
        self.assertIn("Đã xếp xong", text)
        out = commands.xuat([])
        self.assertTrue(out["file"].startswith("﻿".encode()))
        self.assertEqual(out["name"], "chitieu-2026-10.csv")
        self.assertIn("Chi tiêu tháng 10/2026: 4 khoản", out["caption"])
        self.assertEqual(commands.xuat(["7"]), "Tháng 7/2026 chưa có khoản nào")


if __name__ == "__main__":
    unittest.main()
