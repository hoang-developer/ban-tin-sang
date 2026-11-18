"""Nhóm đang dùng và xếp nhóm cho ghi chú. cfg là cấu hình nhóm tự chỉnh của người dùng:
{"moi": [mã nhóm tự tạo], "ten": {mã: tên}, "tu": {mã: [từ khóa]}, "an": [mã nhóm đã ẩn], "dem": số nhóm đã tạo}.
Nhóm ẩn vẫn giữ tên để khoản cũ hiện đúng."""
import re

from domain.chitieu.categories import CATEGORIES, KEYWORDS, plain_pattern, word_pattern
from domain.chitieu.kinds import INCOME, OTHER
from domain.common.text import norm, plain


# Ghi chú là tiền trả nợ, đóng thẻ tín dụng, trả góp, ví trả sau: không phải chi tiêu thiết yếu và không thuộc nhóm
# nhà cửa, ăn uống... dù AI hay từ khóa lạc sang đó (so sau khi bỏ dấu)
DEBT_PAYMENT = re.compile(r"(?<!\w)(?:the tin dung|dong the|thanh toan the|sao ke the|no vay|tra no|tra gop|"
                          r"tra tien vay|vay tieu dung|spaylater|shopeepay)(?!\w)")


def is_debt_payment(note):
    """Ghi chú nói về trả nợ, đóng/thanh toán thẻ tín dụng, trả góp, SPayLater/ShopeePay."""
    return bool(DEBT_PAYMENT.search(plain(note or "")))


def name(code, cfg):
    """Tên nhóm kèm biểu tượng ('🍜 Ăn uống'), kể cả nhóm đã ẩn; mã lạ thì là Khác."""
    return cfg.get("ten", {}).get(code) or CATEGORIES.get(code, CATEGORIES[OTHER])[0]

def bare(label):
    """'🍜 Ăn uống' -> 'Ăn uống'."""
    return label.split(" ", 1)[-1]

def groups(cfg):
    """Các nhóm đang dùng, theo thứ tự hiện trên nút: mã -> (tên, từ khóa tự thêm, từ khóa có sẵn)."""
    hidden = set(cfg.get("an", []))
    order = [c for c in CATEGORIES if c not in (OTHER, INCOME)] + list(cfg.get("moi", [])) + [OTHER, INCOME]
    return {c: (name(c, cfg), cfg.get("tu", {}).get(c, []), CATEGORIES.get(c, ("", []))[1])
            for c in order if c not in hidden}

def rules(learned, cfg):
    """Bảng so khớp (mẫu có dấu, mẫu không dấu, điểm, mã): cụm từ đã học > từ khóa tự thêm > có sẵn."""
    active = groups(cfg)
    learned_rules = [(word_pattern(k), word_pattern(plain(k)), 100 + len(k), code)
                     for k, code in (learned or {}).items() if code in active]
    own = [(word_pattern(norm(k)), plain_pattern(k), len(norm(k)) + 0.5, code)  # +0.5: thắng từ có sẵn trùng
           for code, (_, words, _) in active.items() for k in words]
    return learned_rules + own + [r for r in KEYWORDS if r[3] in active]

def pick(note, table):
    """Câu có dấu chỉ so với từ khóa có dấu ("cho Lan" không phải "chợ", "trả" không phải "trà");
    câu gõ không dấu so với từ khóa đã bỏ dấu ("cho be" là "cho bé", thắng "be" gọi xe).
    Nhiều cụm cùng khớp thì lấy cụm điểm cao nhất (dài nhất)."""
    text = norm(note)
    typed_plain = text == plain(text)
    found = [(score, code) for exact, bare_word, score, code in table
             if (bare_word if typed_plain else exact) and (bare_word if typed_plain else exact).search(text)]
    return max(found, key=lambda x: x[0])[1] if found else OTHER

def classify(note, learned, cfg):
    """Mã nhóm của ghi chú. Cụm từ đã học (người dùng sửa nhóm) thắng từ khóa."""
    return pick(note, rules(learned, cfg))

def find_group(text, cfg, include_hidden=False):
    """Tên nhóm người dùng gõ ('ăn uống', 'di lai', 'ăn', 'trả nợ') -> mã, None nếu không có nhóm nào."""
    key = plain(re.sub(r"[^\w\s]", " ", text))
    key = " ".join(key.split())
    if not key:
        return None
    codes = list(groups(cfg)) + ([c for c in CATEGORIES if c in cfg.get("an", [])]
                                 + [c for c in cfg.get("moi", []) if c in cfg.get("an", [])] if include_hidden else [])
    best = None
    for code in codes:
        label = " ".join(plain(re.sub(r"[^\w\s]", " ", bare(name(code, cfg)))).split())
        score = 3 if label == key else 2 if label.startswith(key) else 1 if re.search(
            rf"(?<!\w){re.escape(key)}", label) else 0
        if score and (best is None or score > best[0]):
            best = (score, code)
    return best[1] if best else None


def find_category(text, cfg):
    """Tên nhóm người dùng gõ ('ăn uống', 'di lai', 'tổng') -> mã, None nếu không rõ."""
    if plain(text).strip() in ("tong", "tat ca", "tong chi"):
        return "tong"
    if plain(text).strip() in ("hang ngay", "hangngay", "sinh hoat", "thuong ngay", "chi hang ngay"):
        return "hangngay"
    code = find_group(text, cfg) or classify(text, None, cfg)
    return None if code == OTHER else code
