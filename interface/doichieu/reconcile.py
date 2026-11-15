"""Đối chiếu tài sản tháng: lệnh /doichieu, nút dc:, tin sáng ngày 15, việc cần làm ở 🏠 Hôm nay."""
import sochitieu as ct  # module cũ ở gốc: ngày hôm nay
from domain.doichieu.reconcile import color  # noqa: F401 (các module khác gọi qua đây)
from interface import common
from presentation.doichieu import reconcile as view
from services.doichieu import reconcile as service

items = service.items  # troly liệt kê ngăn để hỏi số thật
name = view.name
amount_text = view.amount_text


@common.needs_store
def screen(day):
    return view.screen_view(day, service.screen_state(day))


def set_value(item_id, real, now):
    """Ghi số thật của một ngăn. Trả (câu báo, nút)."""
    return view.set_value_view(service.set_value(item_id, real, now))


def morning_part(day):
    """Ngày 15: một phần trong tin sáng (một lần mỗi tháng), hoặc None."""
    count = service.morning_count(day)
    return view.morning_view(day, count) if count else None


def todo(day):
    """Việc cần làm ở 🏠 Hôm nay: từ ngày 15 tới hết tháng, khi còn ngăn chưa đối chiếu."""
    count = service.todo_count(day)
    return view.todo_view(day, count) if count else None


def doichieu(args):
    return screen(ct.today())


def on_button(arg, message, now):
    """Nút "dc:...": xem, ok:<id> (khớp), het (khớp hết), ghi:<id> (ghi khoản lệch là chi/thu chưa ghi)."""
    day = now.date()
    kind, _, value = arg.partition(":")
    if kind == "xem":
        return None, ("edit", lambda: screen(day))
    if kind == "ok":
        ok = service.mark_ok(value, day)
        return ("✅ Khớp" if ok else "Ngăn này chưa đối chiếu được"), ("edit", lambda: screen(day))
    if kind == "het":
        n = service.all_ok(day)
        return f"✅ Đã đánh dấu khớp {n} ngăn", ("edit", lambda: screen(day))
    if kind == "ghi":
        note = view.gap_booked_text(service.book_gap(value, now))
        return common.clip(note), ("edit", lambda: (note, view.screen_rows()))
    return None, None
