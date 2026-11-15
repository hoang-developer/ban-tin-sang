"""Tiến độ ngân sách tháng: số đã chi so với hạn mức từng nhóm, ngân sách tổng và ngân sách chi hằng ngày."""
from domain.chitieu.kinds import INCOME
from repositories.chitieu import budget as budget_repo
from repositories.chitieu import ledger as ledger_repo


def progress(codes, day):
    """Tiến độ ngân sách tháng của các nhóm vừa ghi (và ngân sách tổng): [(mã, đã chi, hạn mức)]."""
    budgets = budget_repo.load()
    if not budgets:
        return []
    import phantich  # module cũ ở gốc: chi tiêu hằng ngày bỏ khoản đột biến
    items = [e for e in ledger_repo.load(day.strftime("%Y-%m")) if e["nhom"] != INCOME]
    out = []
    daily = phantich.daily_groups() if "hangngay" in budgets else []
    extra = (["hangngay"] if daily and set(codes) & set(daily + ["hangngay"]) else []) + (["tong"] if "tong" in budgets else [])
    for code in list(dict.fromkeys([c for c in codes if c in budgets and c not in ("tong", "hangngay")] + extra)):
        if code == "hangngay":  # chi tiêu hằng ngày, không tính khoản đột biến
            spent = phantich.daily_spent(day)
        else:
            spent = sum(e["tien"] for e in items if code == "tong" or e["nhom"] == code)
        out.append((code, spent, budgets[code]))
    return out


def all_progress(day):
    """Tiến độ mọi ngân sách đã đặt trong tháng này: từng nhóm, rồi ngân sách tổng nếu có."""
    return progress([c for c in budget_repo.load() if c != "tong"], day)
