"""Dòng tiền trung bình theo sổ thu chi."""
from datetime import date, timedelta

from domain.chitieu.kinds import INCOME
from repositories.chitieu import ledger as ledger_repo


def monthly_flows(day):
    """(chi trung bình/tháng, thu trung bình/tháng, số ngày có dữ liệu) trong tối đa 90 ngày qua."""
    items = ledger_repo.between(day - timedelta(days=89), day)
    if not items:
        return 0, 0, 0
    days = (day - date.fromisoformat(min(e["ngay"] for e in items))).days + 1
    spend = sum(e["tien"] for e in items if e["nhom"] != INCOME)
    income = sum(e["tien"] for e in items if e["nhom"] == INCOME)
    return spend / days * 30.4, income / days * 30.4, days
