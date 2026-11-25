"""Dòng tiền trung bình theo sổ thu chi."""
from datetime import date, timedelta

from domain.chitieu import flow
from repositories.chitieu import groups as groups_repo
from repositories.chitieu import ledger as ledger_repo


def monthly_flows(day):
    """(chi trung bình/tháng, thu trung bình/tháng, số ngày có dữ liệu) trong tối đa 90 ngày qua."""
    items = ledger_repo.between(day - timedelta(days=89), day)
    if not items:
        return 0, 0, 0
    days = (day - date.fromisoformat(min(e["ngay"] for e in items))).days + 1
    spend = flow.spent(items, flow.debt_group_of(groups_repo.config()))  # trả gốc nợ không phải chi
    income = flow.income(items)
    return spend / days * 30.4, income / days * 30.4, days
