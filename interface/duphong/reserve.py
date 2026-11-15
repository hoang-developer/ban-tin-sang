"""Quỹ dự phòng: lệnh /duphong và nút dp: của bot chi tiêu. Đọc lệnh, gọi service, nhờ presentation dựng tin."""
from domain.common.money import parse_amount
from domain.common.text import plain
from interface.chitieu import context as chitieu_ctx
from interface import common
from interface.kehoach import plan as kehoach
from presentation.duphong import reserve as view
from services.duphong import reserve as service


@common.needs_store
def text(day):
    return view.status_view(service.status(day))


def change(amount, day, from_main=True):
    """Nạp (amount > 0) hoặc rút (amount < 0) quỹ; trả câu báo."""
    return view.change_note(service.change(amount, day, from_main))


def _where(day):
    return view.where_text(service.savings_books())


@common.needs_store
def duphong(args):
    day = chitieu_ctx.today()
    word = plain(args[0]) if args else ""
    rest = " ".join(args[1:])
    usage = ("🛟 /duphong: xem quỹ · /duphong nap 2tr · /duphong rut 1tr · /duphong muctieu 6 (tháng chi) · "
             "/duphong han 12 (đạt trong bao nhiêu tháng) · /duphong chi 10tr (tự đặt chi thiết yếu; /duphong chi tu dong "
             "để bot tự tính) · /duphong tinh <tên sổ/quỹ trong /taisan>")
    if not word:
        return text(day)
    if word in ("nap", "them", "de", "rut"):
        found = parse_amount(rest)
        if not found:
            return usage
        return change(found[0] if word != "rut" else -found[0], day)
    if word in ("muctieu", "thang"):
        n = rest.split()[0] if rest.split() else ""
        if not n.isdigit() or not 1 <= int(n) <= 24:
            return usage
        service.set_months(int(n))
        return text(day)
    if word == "han":
        n = rest.split()[0] if rest.split() else ""
        if not n.isdigit() or not 1 <= int(n) <= 60:
            return usage
        service.set_deadline(int(n), day)
        return text(day)
    if word == "chi":
        if plain(rest).replace(" ", "") in ("tudong", "auto"):
            service.clear_monthly()
            return text(day)
        found = parse_amount(rest)
        if not found:
            return usage
        service.set_monthly(found[0])
        return text(day)
    if word == "tinh":
        return view.toggle_text(service.toggle(rest)) if rest.strip() else usage
    if word in ("noi", "odau"):
        return _where(day)
    return usage


def on_button(arg, message, now):
    """Nút "dp:...": (thông báo nhỏ, việc tiếp theo)."""
    kind, _, value = arg.partition(":")
    day = now.date()
    if kind == "xem":
        return None, ("edit", lambda: text(day))
    if kind == "nap" and value.isdigit():
        lines = change(int(value), day).split("\n")
        toast = lines[0][2:] + "".join(f" · {x[2:]}" for x in lines[1:] if x.startswith("🎉"))
        if common.title_starts(message, "🛟 Quỹ dự phòng"):  # nút trên tin quỹ: vẽ lại tin
            return toast, ("edit", lambda: text(day))
        if common.title_starts(message, "📋"):  # nút trên tin chia lương: vẽ lại tin đó
            return toast, ("edit", lambda: kehoach.plan(day))
        rows = common.without_buttons(message, "dp:nap")
        return toast, ("buttons", lambda: rows)  # nút dưới tin "Đã ghi lương": bỏ nút đó
    if kind == "thang" and value.isdigit():
        service.set_months(int(value))
        return None, ("edit", lambda: text(day))
    if kind == "han" and value.isdigit():
        service.set_deadline(int(value), day)
        return None, ("edit", lambda: text(day))
    if kind == "noi":
        return None, ("send", lambda: _where(day))
    return None, None
