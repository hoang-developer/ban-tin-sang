"""Chữ tiếng Việt: chuẩn hóa và bỏ dấu để so sánh."""
import unicodedata


def norm(text):
    return " ".join(unicodedata.normalize("NFC", text).lower().split())


def plain(text):
    """Bỏ dấu: 'Cà phê đá' -> 'ca phe da'."""
    text = unicodedata.normalize("NFD", norm(text).replace("đ", "d"))
    return "".join(c for c in text if not unicodedata.combining(c))
