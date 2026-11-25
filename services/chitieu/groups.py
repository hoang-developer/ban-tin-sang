"""Nhóm chi tự chỉnh: tạo nhóm, thêm từ khóa, dùng lại nhóm đã ẩn, rồi xếp lại các khoản đang ở Khác theo nhóm mới."""
import html
import json

from domain.chitieu import classify as classify_rules
from domain.chitieu import labels
from domain.chitieu.learn import learn_key
from domain.common.text import plain
from infrastructure import clock
from repositories.chitieu import groups as groups_repo
from services.chitieu import ledger

MAX_GROUPS, MAX_WORDS = 20, 60  # số nhóm tự tạo, số từ khóa tự thêm cho mỗi nhóm


def config():
    return groups_repo.config()


def reset():
    groups_repo.reset()


def groups(cfg=None):
    """Các nhóm đang dùng, theo thứ tự hiện trên nút: mã -> (tên, từ khóa tự thêm, từ khóa có sẵn)."""
    return classify_rules.groups(config() if cfg is None else cfg)


def name(code, cfg=None):
    return classify_rules.name(code, config() if cfg is None else cfg)


def bare(label):
    return classify_rules.bare(label)


def find_group(text, include_hidden=False, cfg=None):
    return classify_rules.find_group(text, config() if cfg is None else cfg, include_hidden)


def today():
    return clock.now_vn().date()


NHOM_USAGE = ("<b>Tự chỉnh nhóm</b>\n"
              "• Tạo nhóm: /nhom them 🏦 Trả nợ: trả nợ, trả góp, vay\n"
              "• Thêm từ khóa: /nhom tukhoa Ăn uống: bún chả, bánh tráng\n"
              "• Đổi tên: /nhom doiten Đi lại: 🚗 Xe cộ\n"
              "• Ẩn nhóm không dùng: /nhom xoa Học tập\n"
              "• Xem cụm bot đã học, xóa cụm học nhầm: /nhom hoc, /nhom hoc xoa bò\n"
              "• Chọn nhóm ngay khi ghi: đóng họ 1tr #trả nợ\n"
              "• Xếp các khoản đang ở Khác: /chuaxep")


def forget_learned(phrase):
    """Bỏ một cụm bot đã học từ lần người dùng sửa nhóm (gõ có dấu hay không đều được); trả các cụm đã bỏ."""
    want = plain(learn_key(phrase))
    if not want:
        return []
    learned = groups_repo.learned()
    gone = [k for k in learned if plain(k) == want]
    if gone:
        groups_repo.save_learned({k: c for k, c in learned.items() if k not in gone})
    return gone


def add_words(cfg, code, words):
    """Thêm từ khóa cho một nhóm; từ khóa đó có ở nhóm tự chỉnh khác thì chuyển sang nhóm này,
    cụm từ đã học trùng hẳn từ khóa đó (học từ lần sửa cũ) thì bỏ để từ khóa mới có tác dụng."""
    if words:
        learned = groups_repo.learned()
        kept = {k: c for k, c in learned.items() if k not in words or c == code}
        if len(kept) != len(learned):
            groups_repo.save_learned(kept)
    cfg.setdefault("tu", {})
    for other, own in cfg["tu"].items():
        if other != code:
            own[:] = [w for w in own if w not in words]
    cfg["tu"][code] = list(dict.fromkeys(cfg["tu"].get(code, []) + words))[-MAX_WORDS:]
    cfg["tu"] = {c: w for c, w in cfg["tu"].items() if w}


def after_change(cfg, text):
    groups_repo.save(cfg)
    moved = ledger.tidy(today())
    return text + (f"\n↪️ Đã xếp lại {moved} khoản đang ở Khác theo nhóm mới" if moved else "")


def nhom_them(rest):
    head, words = labels.split_spec(rest)
    cfg = json.loads(json.dumps(config()))  # bản sao để sửa
    label = labels.make_label(head) if head else None
    code = find_group(head, include_hidden=True, cfg=cfg) if label else None
    if code and plain(bare(name(code, cfg))) != plain(bare(label)):
        code = None  # chỉ khớp một phần tên ("Ăn" với "Ăn uống"): tạo nhóm mới
    if code:
        was_hidden = code in cfg.get("an", [])
        cfg["an"] = [c for c in cfg.get("an", []) if c != code]
        add_words(cfg, code, words)
        text = (f"✅ Đã dùng lại nhóm {name(code, cfg)}" if was_hidden else f"Nhóm {name(code, cfg)} đã có")
        return after_change(cfg, text + (f", thêm từ khóa: {html.escape(', '.join(words))}" if words else ""))
    if not label:
        return NHOM_USAGE
    if len(cfg.get("moi", [])) >= MAX_GROUPS:
        return f"Đã có {MAX_GROUPS} nhóm tự tạo, ẩn bớt nhóm không dùng (/nhom xoa tên nhóm) rồi tạo tiếp"
    cfg["dem"] = cfg.get("dem", 0) + 1
    code = f"r{cfg['dem']}"
    cfg.setdefault("moi", []).append(code)
    cfg.setdefault("ten", {})[code] = label
    add_words(cfg, code, words)
    text = f"✅ Đã tạo nhóm {html.escape(label)}" + (
        f", từ khóa: {html.escape(', '.join(words))}" if words else
        f"\nThêm từ khóa để bot tự xếp: /nhom tukhoa {html.escape(bare(label))}: từ khóa 1, từ khóa 2")
    return after_change(cfg, text)
