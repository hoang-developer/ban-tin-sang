"""Số liệu báo cáo chi tiêu một kỳ: các khoản, kỳ trước để so sánh, tiến độ ngân sách (chỉ báo cáo tháng này)."""
from domain.chitieu import period as periods
from domain.chitieu import flow
from repositories.chitieu import groups as groups_repo
from repositories.chitieu import ledger as ledger_repo
from services.chitieu import budget


def report_data(kind, day):
    """{"kind", "period": (từ, tới, tên, từ trước, tới trước, tên trước), "items", "prev_total", "budget"}."""
    period = periods.period(kind, day)
    start, end, _, prev_start, prev_end, _ = period
    items = ledger_repo.between(start, end)
    debt = flow.debt_group_of(groups_repo.config())
    prev_total = flow.spent(ledger_repo.between(prev_start, prev_end), debt) if items else 0
    return {"kind": kind, "period": period, "items": items, "prev_total": prev_total,
            "budget": budget.all_progress(day) if kind == "thang" and items else []}
