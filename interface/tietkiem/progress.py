"""Tiết kiệm từ khi dùng bot: lệnh /tietkiem, nút tk:, tin nhắc 21h. Đọc lệnh, gọi service, nhờ presentation dựng tin."""
from datetime import timedelta

from domain.common.money import parse_amount
from domain.common.text import plain
from interface.chitieu import context as chitieu_ctx
from interface import common
from presentation.duphong import reserve as reserve_view
from presentation.tietkiem import progress as pview
from services.tietkiem import progress as service


@common.needs_store
def view(day):
    p = service.summary(day)
    return pview.view_text(p, day, service.invest_fund() if p.movable else None)


def after_record(entries, day, brief=False):
    """Dòng thêm dưới tin "Đã ghi" (chuỗi ngày, hôm nay so với mốc, đã bớt, chúc mừng mốc); [] nếu chưa cần."""
    result = service.after_record(entries, day)
    return pview.after_record_lines(result[0], result[1], brief) if result else []


def home_line(day):
    p = service.home(day)
    return pview.home_line(p) if p else None


def reminder(day):
    """Tin nhắc 21h: (chữ, nút), hoặc None nếu không cần nhắc."""
    p = service.reminder(day)
    return pview.reminder_view(p, day) if p else None


def period_line(kind, day):
    info = service.period(kind, day)
    return pview.period_text(info) if info else None


def mark_no_spend(day_iso, today):
    return pview.no_spend_text(service.mark_no_spend(day_iso, today))


@common.needs_store
def tietkiem(args):
    day = chitieu_ctx.today()
    word = plain(args[0]) if args else ""
    rest = " ".join(args[1:])
    if not word:
        return view(day)
    if word in ("huongdan", "help", "?"):
        return pview.USAGE
    if word in ("khongtieu", "khong"):
        target = day - timedelta(days=1) if "qua" in plain(rest) else day
        return mark_no_spend(target.isoformat(), day)
    if word == "moc":
        found = parse_amount(rest)
        if not found or not 10_000 <= found[0] <= 10_000_000:
            return "Mốc chi lặt vặt mỗi ngày, ví dụ: /tietkiem moc 300k"
        service.set_base(found[0])
        return view(day)
    if word == "batdau":
        when, _ = chitieu_ctx.parse_date(rest, day)
        if when > day:
            return "Ngày bắt đầu phải là hôm nay hoặc trước đó, ví dụ: /tietkiem batdau 04/11"
        service.set_start(when)
        return view(day)
    if word == "nhac":
        on = service.set_reminder(plain(rest) not in ("tat", "off", "khong"))
        return "✅ Bật nhắc 21h khi hôm đó chưa ghi gì" if on else "Đã tắt nhắc 21h"
    return pview.USAGE


def on_button(arg, message, now):
    """Nút "tk:...": (thông báo nhỏ, việc tiếp theo)."""
    kind, _, value = arg.partition(":")
    day = now.date()
    if kind == "xem":
        return None, ("edit", lambda: view(day))
    if kind == "khong":
        note = mark_no_spend(value, day)
        if common.title_starts(message, "💚"):
            return common.clip(note), ("edit", lambda: view(day))
        rows = common.without_buttons(message, "tk:khong")
        return common.clip(note), ("buttons", lambda: rows)
    if kind == "chuyen":
        where, _, amount = value.partition(":")
        if not amount.isdigit():
            return None, None
        amount = int(amount)
        if where == "dt":
            note = pview.invest_move_note(service.move_to_invest(amount), amount)
        else:
            note = reserve_view.change_note(service.move_to_reserve(amount, day)).split("\n")[0][2:]
        return common.clip(note), ("edit", lambda: view(day))
    return None, None
