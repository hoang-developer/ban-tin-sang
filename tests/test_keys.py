"""Khóa Redis: chuỗi phải y như bản cũ (đổi là mất dữ liệu đang chạy), và code không viết khóa trực tiếp."""
import ast
import re
import unittest
from pathlib import Path

from repositories import keys

ROOT = Path(__file__).resolve().parent.parent


def source_files(outside=()):
    """Mọi file .py của app (không tính tests, .git), bỏ các thư mục trong outside."""
    return [p for p in sorted(ROOT.rglob("*.py"))
            if not {"tests", ".git", "__pycache__"} & set(p.relative_to(ROOT).parts)
            and not any(part in outside for part in p.relative_to(ROOT).parts)]
GOLDEN = {  # chép từ main trước khi refactor
    keys.COUNTER: "chitieu:dem", keys.LEARN: "chitieu:hoc", keys.BUDGET: "chitieu:ngansach",
    keys.GROUPS: "chitieu:nhomrieng", keys.AI_CACHE: "chitieu:ai", keys.AI_STATS: "chitieu:ai:thongke",
    keys.PLAIN_NOTES: "chitieu:hieu:chi", keys.DAILY_GROUPS: "chitieu:dubao:nhom",
    keys.ASSETS: "chitieu:taisan", keys.ASSET_HISTORY: "chitieu:taisan:lichsu", keys.GOLD: "vivang",
    keys.SALARY: "chitieu:luong", keys.FUND: "chitieu:dautu", keys.RESERVE: "chitieu:duphong",
    keys.SAVINGS: "chitieu:tietkiem", keys.RECONCILE: "chitieu:doichieu", keys.OWNERS: "chitieu:chutk",
    keys.KEYBOARD_FLAG: "chitieu:banphim:2", keys.CARD_COUNTER: "chitieu:the:dem",
    keys.WATCHLIST: "theodoi", keys.REMINDERS: "nhac", keys.KEYWORDS: "tukhoa", keys.GOLD_HISTORY: "vang_lichsu",
    keys.GUESS_STATS: "doan_thongke", keys.ALERT_STATE: "canhbao", keys.BOARD: "bangdien",
    keys.DIVIDENDS_SEEN: "cotuc_daxem", keys.TICK_LAST: "tick_cuoi", keys.TICK_LOCK: "khoa:tick",
    keys.ANALYSIS_OFF: "nhandinh:tat", keys.CACHE_SECTORS: "nhandinh:nganh", keys.CACHE_HOSE: "nhandinh:hose",
    keys.ledger_month("2026-11"): "chitieu:2026-11",
    keys.price_cache("hose"): "chitieu:gia:hose",
    keys.fund_nav("VMEEF"): "chitieu:dautu:nav:VMEEF",
    keys.fund_info("VMEEF"): "chitieu:dautu:thongtin:VMEEF",
    keys.savings_streak_milestone(7): "chitieu:tietkiem:moc:chuoi:7",
    keys.savings_saved_milestone(1000000): "chitieu:tietkiem:moc:bot:1000000",
    keys.reconcile_reminder("2026-11"): "chitieu:doichieu:nhac:2026-11",
    keys.alert_rise("SSI"): "chitieu:canhbao:tang:SSI",
    keys.alert_budget("an", "2026-11"): "chitieu:canhbao:ngansach:an:2026-11",
    keys.debt_reminder(3, "2026-11", "truoc"): "chitieu:nhac:no:3:2026-11:truoc",
    keys.saving_maturity_reminder(5, "2026-12-01"): "chitieu:nhac:daohan:5:2026-12-01",
    keys.conversation(42): "chitieu:cho:42", keys.conversation(None): "chitieu:cho:0",
    keys.card(9): "chitieu:the:9",
    keys.ai_usage("2026-11-15"): "chitieu:hieu:thu:2026-11-15",
    keys.benchmark_usage("2026-11-15"): "chitieu:danhgia:2026-11-15",
    keys.image_seen("abc"): "chitieu:anh:abc", keys.image_pending("abc"): "chitieu:anhcho:abc",
    keys.done_transaction("2026-11-15", 35000, "chi"): "chitieu:gd:2026-11-15|35000|chi",
    keys.guess("2026-11-15"): "doan:2026-11-15", keys.guess_result("2026-11-15"): "doan_kq:2026-11-15",
    keys.job_done("sang", "2026-11-15"): "xong:sang:2026-11-15",
    keys.cache_foreign(5, "2026-11-10"): "nhandinh:kn:5:2026-11-10",
}
KHO_KEY_ARG = {"get": 0, "put": 0, "put_new": 0, "delete": 0, "command": 1}  # command("INCR", khóa, ...)


def is_literal(node):
    return isinstance(node, (ast.Constant, ast.JoinedStr)) and not (
        isinstance(node, ast.Constant) and not isinstance(node.value, str))


class Khoa(unittest.TestCase):
    def test_chuoi_khoa_giu_nguyen(self):
        for got, want in GOLDEN.items():
            self.assertEqual(got, want)

    def test_khong_khoa_nao_trung_nhau(self):
        self.assertEqual(len(set(GOLDEN.values())), len(GOLDEN.values()))

    def test_code_khong_viet_khoa_truc_tiep(self):
        """kho.get/put/put_new/delete/command và remembered() phải nhận khóa từ repositories.keys, không phải chuỗi."""
        bad = []
        for path in source_files():
            if path.name in ("kho.py", "questions.py"):
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id == "kho" \
                        and func.attr in KHO_KEY_ARG:
                    index = KHO_KEY_ARG[func.attr]
                elif isinstance(func, ast.Name) and func.id == "remembered":
                    index = 0
                else:
                    continue
                if len(node.args) > index and is_literal(node.args[index]):
                    bad.append(f"{path.name}:{node.lineno}")
        self.assertEqual(bad, [], "khóa viết trực tiếp, hãy thêm vào repositories/keys.py")

    def test_khong_con_chuoi_khoa_chitieu_ngoai_keys(self):
        """Hằng như K_X = "chitieu:..." hay f"chitieu:..." chỉ được nằm trong repositories/keys.py."""
        bad = []
        for path in source_files():
            if path.name == "questions.py" or path == ROOT / "repositories" / "keys.py":
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.startswith("chitieu:"):
                    bad.append(f"{path.name}:{node.lineno}")
        self.assertEqual(bad, [], "khóa chitieu: viết ngoài repositories/keys.py")

    def test_khoa_da_co_repo_chi_repo_duoc_dung(self):
        """Dữ liệu đã có repository (ví vàng, tài sản, lịch sử tài sản, giá, lương, quỹ, sổ thu chi) chỉ đi qua repo."""
        pattern = re.compile(r"keys\.(GOLD|ASSETS|ASSET_HISTORY|SALARY|FUND|price_cache|COUNTER|ledger_month|fund_nav|fund_info)\b")
        bad = [f"{path.name}: {m.group(0)}" for path in source_files(outside=("repositories",))
               for m in pattern.finditer(path.read_text(encoding="utf-8"))]
        self.assertEqual(bad, [], "dùng repositories.<tên> thay vì gọi kho với khóa này")

if __name__ == "__main__":
    unittest.main()
