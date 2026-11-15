"""Đọc lệnh tự chỉnh nhóm: "Ăn uống: bún chả, bánh tráng", tên nhóm có biểu tượng."""
import re
import unicodedata

from domain.common.text import norm


def split_spec(text):
    """'Ăn uống: bún chả, bánh tráng' -> ('Ăn uống', ['bún chả', 'bánh tráng'])."""
    head, sep, tail = text.partition(":")
    words = [norm(w).strip(" .") for w in re.split(r"[,;\n]", tail)] if sep else []
    return head.strip(), list(dict.fromkeys(w for w in words if 0 < len(w) <= 40))


def make_label(text, old=None):
    """'🏦 Trả nợ' giữ nguyên; 'Trả nợ' thì thêm biểu tượng (của tên cũ nếu đổi tên)."""
    text = " ".join(re.sub(r"[<>&\"]", "", unicodedata.normalize("NFC", text)).split())[:40]  # tên an toàn cho HTML
    m = re.match(r"([^\w\s]+)\s*(\w.*)$", text)
    if m:
        return f"{m[1]} {m[2]}"
    emoji = old.split(" ", 1)[0] if old and " " in old else "🏷️"
    return f"{emoji} {text}" if text else None
