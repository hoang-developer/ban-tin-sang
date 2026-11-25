"""Kế hoạch tài chính: lệnh /kehoach (lộ trình, chia lương), nút kh:, gợi ý chia lương sau khi ghi lương.

Các hàm ở đây giữ tên và dạng giá trị trả về mà các màn hình khác (menu, trợ lý, tin tối, dự báo chi tiêu) đang gọi.
"""
import sys

from domain.chitieu.kinds import INCOME
from domain.common.text import plain
from interface.chitieu import context as chitieu_ctx
from interface import common
from presentation.kehoach import plan as pview
from repositories.kehoach import settings as settings_repo
from services.kehoach import plan as service

short, spend_text, room_text, basis_text = pview.short, pview.spend_text, pview.room_text, pview.basis_text
numbers, spendable, spendable_safe = service.numbers, service.spendable, service.spendable_safe


def _invest_fund(n):
    return n["invest"]["ma"] if n["invest"] else None


def steps(n):
    """Các việc còn lại của kế hoạch tháng: [(loại, nhãn, số tiền, mã khoản nợ)]."""
    return [(kind, pview.step_label(kind, d, _invest_fund(n)), amount, ref) for kind, d, amount, ref in service.steps(n)]


def _next_actions(day, n=None):
    """Tối đa 3 việc nên làm ngay, theo thứ tự ưu tiên."""
    return pview.next_action_lines(service.next_actions(day, n))


@common.needs_store
def plan(day):
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
    salary = [e for e in entries if e["nhom"] == INCOME and "luong" in plain(e.get("ghichu") or "")]
    if not salary or not common.ready():
        return None
    n = service.numbers(day)
    if not n["debt_left"] and not n["fund_left"] and not n["invest_left"]:
        return None
    return pview.salary_hint_view(n, service.steps(n))


@common.needs_store
def roadmap(day):
    n = service.numbers(day)
    r = service.roadmap(day, n)
    return pview.roadmap_view(day, n, r, service.next_actions(day, n))


@common.needs_store
def _confirm_all(day):
    n = service.numbers(day)
    todo = service.steps(n)
    main, balance = service.main_account()
    return pview.confirm_view(day, todo, _invest_fund(n), main, balance)


def do_all(now):
    """Làm các việc còn lại của kế hoạch (tính lại lúc bấm, nên bấm hai lần không làm hai lần). Trả các dòng báo."""
    return pview.do_all_lines(service.do_all(now))


@common.needs_store
def kehoach(args):
    word = plain(args[0]) if args else ""
    if word in ("chia", "luong", "chialuong", "thang"):
        return plan(chitieu_ctx.today())
    if word in ("tieudu", "tieuphandu"):  # /kehoach tieudu 30: được tiêu 30% phần dư, còn lại để dành
        try:
            share = float(args[1].rstrip("%").replace(",", ".")) / 100 if len(args) > 1 else None
        except ValueError:
            share = None
        if share is None or not 0 <= share <= 1:
            return ("Phần dư sau chia lương mặc định để dành hết. Cho tiêu một phần: /kehoach tieudu 30 (30% phần dư); "
                    "để dành hết lại: /kehoach tieudu 0")
        settings_repo.save_spend_share(share)
        return (f"✅ Từ giờ được tiêu {share * 100:.0f}% phần dư sau chia lương, còn lại để dành."
                if share else "✅ Phần dư sau chia lương để dành hết (mặc định).") + "\n\n" + plan(chitieu_ctx.today())[0]
    return roadmap(chitieu_ctx.today())


def on_button(arg, message, now):
    """Nút "kh:...": lt (lộ trình), chia (chia lương), het (làm hết theo kế hoạch: hỏi lại, het:ok làm)."""
    day = now.date()
    if arg == "lt":
        return None, ("edit", lambda: roadmap(day))
    if arg == "het":
        if common.title_starts(message, "📋"):
            return None, ("edit", lambda: _confirm_all(day))
        return None, ("send", lambda: _confirm_all(day))
    if arg == "het:ok":
        done = do_all(now)

        def result():
            text, rows = plan(day)
            return "\n".join(done) + "\n\n" + text, rows
        return "Đã làm theo kế hoạch", ("edit", result)
    if arg == "chia":
        if common.title_starts(message, "🎯", "📋", "🏠"):
            return None, ("edit", lambda: plan(day))
        return None, ("send", lambda: plan(day))
    return None, None
