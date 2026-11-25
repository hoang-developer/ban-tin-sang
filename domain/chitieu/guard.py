"""Tin có số tiền nhưng không phải khoản chi đã xảy ra: dự định ("mai tôi định mua laptop 20tr"), câu hỏi giả định ("nếu mua
xe 30tr thì sao"), câu hỏi, hoặc tin bot gửi bị dán lại. Những tin này không bao giờ được ghi thẳng vào sổ: bot hỏi lại.
Thuần: so trên chữ đã bỏ dấu, nhầm thì chỉ tốn một lần bấm nút (không mất dữ liệu)."""
import re

from domain.common.text import plain
from domain.phantich.query import is_question

# Động từ đi sau chữ báo dự định: "định mua", "sẽ đóng"... ("định kỳ", "cố định", "sắp xếp" không phải dự định)
VERBS = "mua|dong|tra|nop|di|doi|sam|dat|thue|chi|cho|gui|rut|chuyen|sua|bien|dau tu|tieu"
FUTURE = re.compile(
    rf"(?<!\w)(?:(?:dinh|du dinh|se|sap|chuan bi|muon|tinh|ke hoach|du kien)\s+(?:{VERBS})(?!\w)"
    r"|ngay mai|ngay kia|tuan sau|thang sau|nam sau|lat nua|ti nua)"
    r"|^\s*mai(?!\w)")  # "mai mua laptop 20tr": chữ "mai" đứng đầu tin (không nhầm tên người: "trả Mai 500k")
HYPOTHETICAL = re.compile(r"^\s*(?:neu|gia su|gia du|lieu)(?!\w)|(?<!\w)(?:thi sao|ra sao|lieu co)(?!\w)")

# Tin bot gửi bắt đầu bằng biểu tượng riêng của bot; người dùng không mở đầu một khoản chi bằng các biểu tượng này
BOT_START = tuple("🔎📊🏠💸✅🧾📅🗂💼💳🎯🔮🩺🛟🐷📈🌙☀🔥📋🤔🟢🔴⚠📷🔄")
BOT_PHRASES = re.compile(r"(?<!\w)(?:da ghi|minh hieu la|tong:|tong chi|da xu ly|con duoc tieu|tai san rong|bot tinh)(?!\w)")


def is_bot_text(text):
    """Tin giống tin bot đã gửi (người dùng dán lại): mở đầu bằng biểu tượng của bot, hoặc nhiều dòng/có dấu « · » kèm
    cụm chữ chỉ bot mới dùng ("Đã ghi", "Tổng:", "Mình hiểu là"...)."""
    t = text.strip()
    if t.startswith(BOT_START):
        return True
    return bool(BOT_PHRASES.search(plain(t)) and ("\n" in t or " · " in t))


def line_reason(line):
    """Lý do một dòng không phải khoản chi đã xảy ra: "tuong_lai" | "gia_su" | "hoi", hoặc None."""
    bare = plain(line)
    if FUTURE.search(bare):
        return "tuong_lai"
    if HYPOTHETICAL.search(bare):
        return "gia_su"
    if is_question(line):
        return "hoi"
    return None


def skip_reason(text):
    """Lý do tin này không được ghi thẳng: "dan_lai" (tin bot bị dán lại) | "tuong_lai" | "gia_su" | "hoi"; None nếu là
    khoản chi thường. Nhiều dòng: dòng nào có lý do thì cả tin chờ hỏi."""
    t = text.strip()
    if not t:
        return None
    if is_bot_text(t):
        return "dan_lai"
    return next(filter(None, (line_reason(line) for line in t.splitlines())), None)
