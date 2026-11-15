"""Mã tham chiếu một khoản trong nút bấm: "2026-11:12" là khoản 12 của tháng 11/2026."""


def ref(e):
    return f"{e['ngay'][:7]}:{e['id']}"


def button_ref(data):
    """'nhom:2026-11:12:an' -> '2026-11:12' (khoản mà nút đó trỏ tới), None nếu không phải nút của khoản."""
    kind, _, rest = data.partition(":")
    return ":".join(rest.split(":")[:2]) if kind in ("doi", "xoa", "nhom", "giu") else None
