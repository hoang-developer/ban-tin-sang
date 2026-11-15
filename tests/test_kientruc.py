"""Kiến trúc phân lớp (plan.md): lớp chỉ được import lớp ở dưới nó; số file còn ở gốc chỉ giảm; mọi module import được."""
import ast
import importlib
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LAYERS = ("domain", "infrastructure", "repositories", "services", "presentation", "interface")
ALLOWED = {
    "domain": {"domain"},
    "infrastructure": {"infrastructure"},
    "repositories": {"domain", "infrastructure", "repositories"},
    "services": {"domain", "repositories", "infrastructure", "services"},
    "presentation": {"domain", "presentation"},  # kiểu kết quả của service nằm ở domain
    "interface": set(LAYERS),
}
# Module cũ ở gốc mà file trong lớp mới còn tạm import, cho tới khi chức năng đó được chuyển. Phải khớp CHÍNH XÁC với
# thực tế: thêm import cũ mới thì test đỏ, bỏ được import cũ mà không xóa khỏi danh sách cũng đỏ (ratchet: chỉ rút ngắn).
LEGACY_IMPORTS = {}
ROOT_PY_MAX = 1  # file .py còn ở gốc (không tính api/): chỉ được giảm qua từng bước, đích 0


def py_files(folder):
    return [p for p in sorted((ROOT / folder).rglob("*.py")) if "__pycache__" not in p.parts]


def imported_roots(path):
    """Tên gói gốc của mọi import trong file (kể cả import trong hàm)."""
    roots = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            roots |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


class Kientruc(unittest.TestCase):
    def test_lop_chi_import_lop_duoi(self):
        legacy = {p.stem for p in ROOT.glob("*.py")}  # module cũ còn ở gốc
        bad = []
        for layer in LAYERS:
            for path in py_files(layer):
                rel = str(path.relative_to(ROOT))
                roots = imported_roots(path)
                for name in roots:
                    if name in LAYERS and name not in ALLOWED[layer]:
                        bad.append(f"{rel} import {name}: sai chiều giữa các lớp")
                used = roots & legacy
                allowed = LEGACY_IMPORTS.get(rel, set())
                if used - allowed:
                    bad.append(f"{rel} import module cũ {sorted(used - allowed)}: chưa có trong LEGACY_IMPORTS")
                if allowed - used:
                    bad.append(f"{rel}: LEGACY_IMPORTS còn {sorted(allowed - used)} không dùng nữa, hãy bỏ khỏi danh sách")
        stale = [f for f in LEGACY_IMPORTS if not (ROOT / f).exists()]
        self.assertEqual(bad + [f"{f}: không còn file" for f in stale], [])

    def test_so_file_o_goc_chi_giam(self):
        root_files = sorted(p.name for p in ROOT.glob("*.py"))
        self.assertLessEqual(len(root_files), ROOT_PY_MAX,
                             f"{len(root_files)} file ở gốc, tối đa {ROOT_PY_MAX}: không thêm file mới ở gốc")

    def test_ro_giam_ratchet_khong_bo_sot(self):
        """Giảm số file ở gốc thì hạ ROOT_PY_MAX theo, để mức mới giữ được."""
        self.assertEqual(len(list(ROOT.glob("*.py"))), ROOT_PY_MAX, "đã giảm file ở gốc: hạ ROOT_PY_MAX trong test này")

    def test_moi_module_import_duoc(self):
        """Import thử mọi module (cả api/*.py): bắt import sót sau khi chuyển file."""
        failed = []
        for path in [p for p in sorted(ROOT.rglob("*.py"))
                     if not {"tests", ".git", "__pycache__"} & set(p.relative_to(ROOT).parts)]:
            rel = path.relative_to(ROOT)
            try:
                if rel.parts[0] == "api":
                    spec = importlib.util.spec_from_file_location(f"_api_{rel.stem}", path)
                    spec.loader.exec_module(importlib.util.module_from_spec(spec))
                else:
                    parts = list(rel.with_suffix("").parts)
                    if parts[-1] == "__init__":
                        parts.pop()
                    importlib.import_module(".".join(parts))
            except Exception as e:  # noqa: BLE001
                failed.append(f"{rel}: {e!r}")
        self.assertEqual(failed, [])


if __name__ == "__main__":
    unittest.main()
