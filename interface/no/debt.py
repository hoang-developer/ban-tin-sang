"""Sổ nợ: lệnh /no, nút no:, nhắc trả nợ, dòng tổng quan, chấm sức khỏe nợ.

Các hàm ở đây giữ tên và dạng giá trị trả về mà các màn hình khác (kế hoạch chia lương, menu, khám sức khỏe, tin sáng,
ghi chi tiêu) đang gọi: kết quả của service được presentation dựng thành chữ.
"""
import sochitieu as ct  # module cũ ở gốc: đọc số tiền, ngày hôm nay, tìm khoản chi, hàng nút
from domain.no import debt as rules
from interface import common
from interface.kehoach import plan as kehoach
from presentation.no import debt as pview
from services.no import debt as service

# Truy vấn và phép tính mà các module khác dùng trực tiếp
month_of, paid_in, is_due, month_left = rules.month_of, rules.paid_in, rules.is_due, rules.month_left
schedule, has_interest, ym_text = rules.schedule, rules.has_interest, rules.ym_text
short, short_name, interest_text = pview.short, pview.short_name, pview.interest_text
debts, active, by_id, freed, debt_group = service.debts, service.active, service.by_id, service.freed, service.debt_group
due_now, monthly_total, undo = service.due_now, service.monthly_total, service.undo


def view(day):
    return pview.view_view(service.view_state(day), day)


def _edit_list():
    return pview.edit_list_view(service.debts())


def home_line(day):
    """Một dòng cho màn hình tổng quan; None nếu không có nợ."""
    summary = service.home_summary(day)
    return pview.home_line(*summary, day) if summary else None


def reminders(day):
    """Tin nhắc trả nợ (tin, nút) cho các khoản tới hạn mà tháng này chưa trả đủ; None nếu không có gì cần nhắc."""
    due = service.reminders(day)
    return pview.reminders_view(due, day) if due else None


def health_check(day, v, income):
    """(điểm 0–20, dấu, dòng) cho khám sức khỏe tài chính."""
    return pview.health_line(service.health(day, v, income))


def declare(text, day):
    result = service.declare(text, day)
    return pview.USAGE if result is None else pview.declare_text(result, day)


def declare_info(info, day):
    return pview.declare_text(service.declare_info(info, day), day)


def pay(debt_id, amount, now):
    """Bấm ✅ Trả: ghi khoản chi nhóm Trả nợ và trừ dư nợ. Trả (khoản đã ghi hoặc None, các dòng báo)."""
    result = service.pay(debt_id, amount, now)
    return result.entry, pview.pay_lines(result)


def after_record(entries, day):
    """Vừa ghi các khoản: khoản nào là trả nợ thì trừ dư nợ. Trả (dòng thêm, hàng nút)."""
    return pview.after_record_view(service.after_record(entries, day))


@common.needs_store
def no_cmd(args):
    day = ct.today()
    word = ct.plain(args[0]) if args else ""
    if not args:
        return view(day)
    if word in ("xoa", "sua", "ds"):
        return _edit_list()
    if word in ("huongdan", "help", "?"):
        return pview.USAGE
    if word == "tra" and len(args) > 1:  # /no tra chú Tư 5tr
        rest = " ".join(args[1:])
        found = ct.parse_amount(rest)
        d = service.find_for_command(rest)
        if not found or not d:
            return "Trả nợ: /no tra <tên khoản nợ> <số tiền>, ví dụ /no tra chú Tư 5tr"
        _, lines = pay(d["id"], found[0], service.now())
        return "\n".join(lines)
    return declare(" ".join(args), day)


def on_button(arg, message, now):
    """Nút "no:...": (thông báo nhỏ, việc tiếp theo)."""
    kind, _, rest = arg.partition(":")
    day = now.date()
    if kind == "xem":
        return None, ("edit", lambda: view(day))
    if kind == "hd":
        return None, ("send", lambda: pview.USAGE)
    if kind == "ds":
        return None, ("edit", _edit_list)
    if kind == "x":
        if service.remove(rest):
            return "Đã xóa khoản nợ", ("edit", _edit_list)
        return "Khoản này đã xóa rồi", ("edit", _edit_list)
    if kind == "tra":
        debt_id, _, amount = rest.partition(":")
        if not amount.isdigit():
            return None, None
        e, lines = pay(debt_id, int(amount), now)
        toast = common.clip(common.strip_tags(lines[0]))
        if not e:
            return toast, None
        if common.title_starts(message, "📋"):
            return toast, ("edit", lambda: kehoach.plan(day))
        if common.title_starts(message, "🏠"):
            import menu  # nạp muộn để né vòng với menu (hết khi menu được tách)
            return toast, ("edit", lambda: menu.home(day))
        if common.title_starts(message, "💳"):
            return toast, ("edit", lambda: view(day))
        rows = [row for row in ct.keyboard_rows(message) if not any(d == f"no:{arg}" for _, d in row)]
        return toast, ("buttons", lambda: rows)
    reference = rest.rpartition(":")[0] if kind == "gan" else rest
    e = ct.find(reference) if kind in ("gan", "kg", "bo") else None
    if kind in ("gan", "kg", "bo") and e is None:
        return "Khoản chi này đã xóa rồi", None
    keep = common.without_rows(message, (f"no:gan:{reference}:", f"no:kg:{reference}", f"no:bo:{reference}"))
    if kind == "gan":
        payment = service.assign(e, rest.rpartition(":")[2], day)
        if payment is None:
            return "Khoản này đã trừ nợ rồi hoặc khoản nợ không còn", ("buttons", lambda: keep)
        return common.clip(common.strip_tags(pview.payment_lines(payment)[0])), ("buttons", lambda: keep)
    if kind == "kg":
        return "Không trừ vào khoản nợ nào", ("buttons", lambda: keep)
    if kind == "bo":
        if not e.get("no"):
            return "Khoản này không trừ nợ", ("buttons", lambda: keep)
        d = service.unassign(e)
        return common.clip(f"Đã bỏ trừ nợ, {d['ten']} còn {pview.short(d['tien'])}" if d else "Đã bỏ trừ nợ"), ("buttons", lambda: keep)
    return None, None
