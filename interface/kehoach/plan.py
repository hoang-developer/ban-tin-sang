"""Kế hoạch tài chính: lệnh /kehoach (lộ trình, chia lương), nút kh:, gợi ý chia lương sau khi ghi lương.

Các hàm ở đây giữ tên và dạng giá trị trả về mà các màn hình khác (menu, trợ lý, tin tối, dự báo chi tiêu) đang gọi.
"""
import sys

import sochitieu as ct  # module cũ ở gốc: đọc lệnh, ngày hôm nay
from infrastructure import kho
from presentation.kehoach import plan as pview
from services.kehoach import plan as service

short, spend_text, room_text, basis_text = pview.short, pview.spend_text, pview.room_text, pview.basis_text
numbers, spendable, spendable_safe = service.numbers, service.spendable, service.spendable_safe


def _invest_fund(n):
    return n["invest"]["ma"] if n["invest"] else None


def steps(n):
    """Các việc còn lại của kế hoạch tháng: [(loại, nhãn, số tiền, mã khoản nợ)]."""
    return [(kind, pview.step_label(kind, d, _invest_fund(n)), amount, ref) for kind, d, amount, ref in service.steps(n)]


def next_actions(day, n=None):
    """Tối đa 3 việc nên làm ngay, theo thứ tự ưu tiên."""
    return pview.next_action_lines(service.next_actions(day, n))


def plan(day):
    if not kho.ready():
        return ct.NEED_STORE
    n = service.numbers(day)
    try:
        step = pview.step_line(service.roadmap(day, n), n["fund"], n["invest"])
    except Exception as e:
        print(f"[lỗi] bước lộ trình: {e!r}", file=sys.stderr)
        step = None
    s = service.spendable_safe(day, n)
    main, balance = service.main_account_of(n["data"], day)
    return pview.plan_view(day, n, s, step, main, balance, service.steps(n))


def salary_hint(entries, day):
    """Vừa ghi lương: (dòng gợi ý chia lương, hàng nút); None nếu không có lương hoặc chưa có gì để chia."""
    salary = [e for e in entries if e["nhom"] == ct.INCOME and "luong" in ct.plain(e.get("ghichu") or "")]
    if not salary or not kho.ready():
        return None
    n = service.numbers(day)
    if not n["debt_left"] and not n["fund_left"] and not n["invest_left"]:
        return None
    return pview.salary_hint_view(n, service.steps(n))


def roadmap(day):
    if not kho.ready():
        return ct.NEED_STORE
    n = service.numbers(day)
    r = service.roadmap(day, n)
    return pview.roadmap_view(day, n, r, service.next_actions(day, n))


def confirm_all(day):
    if not kho.ready():
        return ct.NEED_STORE
    n = service.numbers(day)
    todo = service.steps(n)
    main, balance = service.main_account()
    return pview.confirm_view(day, todo, _invest_fund(n), main, balance)


def do_all(now):
    """Làm các việc còn lại của kế hoạch (tính lại lúc bấm, nên bấm hai lần không làm hai lần). Trả các dòng báo."""
    return pview.do_all_lines(service.do_all(now))


def kehoach(args):
    if not kho.ready():
        return ct.NEED_STORE
    word = ct.plain(args[0]) if args else ""
    if word in ("chia", "luong", "chialuong", "thang"):
        return plan(ct.today())
    return roadmap(ct.today())


def on_button(arg, message, now):
    """Nút "kh:...": lt (lộ trình), chia (chia lương), het (làm hết theo kế hoạch: hỏi lại, het:ok làm)."""
    day = now.date()
    if arg == "lt":
        return None, ("edit", lambda: roadmap(day))
    if arg == "het":
        if (message.get("text") or "").startswith("📋"):
            return None, ("edit", lambda: confirm_all(day))
        return None, ("send", lambda: confirm_all(day))
    if arg == "het:ok":
        done = do_all(now)

        def result():
            text, rows = plan(day)
            return "\n".join(done) + "\n\n" + text, rows
        return "Đã làm theo kế hoạch", ("edit", result)
    if arg == "chia":
        if (message.get("text") or "").startswith(("🎯", "📋", "🏠")):
            return None, ("edit", lambda: plan(day))
        return None, ("send", lambda: plan(day))
    return None, None
