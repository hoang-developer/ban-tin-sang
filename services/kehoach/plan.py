"""Kế hoạch tài chính: gom số liệu chia lương tháng này, mỗi ngày được tiêu, các việc còn lại, làm hết theo kế hoạch.

Số liệu trả dạng dict theo khóa (xem domain/kehoach/plan.py); kết quả việc làm là kiểu có cấu trúc.
"""
import sys
from datetime import timedelta

import sochitieu as ct  # module cũ ở gốc: sổ chi tiêu, nhóm
from domain.kehoach import plan as rules
from domain.kehoach.plan import DoAllResult, StepResult
from domain.no import debt as debt_rules
from repositories.chitieu import budget as budget_repo
from repositories.dautu import fund as dautu_fund
from repositories.duphong import reserve as reserve_repo
from repositories.luong import salary as salary_repo
from services.dautu import market as dautu_market
from services.dautu import orders as dautu_orders
from services.dautu import reports as dautu_reports
from services.duphong import reserve as reserve_service
from repositories.taisan import assets as assets_repo
from services.no import debt as debt_service
from services.taisan import accounts, flows
from services.taisan import valuation as valuation_service


def spending_estimate(day, group, debt_need):
    """(chi tiêu dự kiến tháng này không tính trả nợ, cách tính) — None nếu chưa có dữ liệu."""
    budget_total = budget_repo.load().get("tong")
    if budget_total:
        return rules.estimate_spend(budget_total, debt_need, [], day, None)
    items = [e for e in ct.between(day - timedelta(days=89), day)
             if e["nhom"] not in (ct.INCOME, group) and not e.get("no")]
    return rules.estimate_spend(None, debt_need, items, day, reserve_repo.load().get("chi"))


def invest_part(day):
    """Phần đầu tư quỹ mở hằng tháng (/dautu) khi chia lương; None nếu chưa bật hoặc lỗi."""
    try:
        return dautu_reports.salary_part(day)
    except Exception as e:
        print(f"[lỗi] phần đầu tư khi chia lương: {e!r}", file=sys.stderr)
        return None


def numbers(day):
    """Số liệu chia lương tháng này (dùng chung cho /kehoach, tin ghi lương, màn hình tổng quan)."""
    ym = debt_rules.month_of(day)
    data = assets_repo.load()
    group = debt_service.debt_group()[0]
    month = ct.load(ym)
    income = sum(e["tien"] for e in month if e["nhom"] == ct.INCOME)
    basis = ""
    if not income:
        salary = salary_repo.load()
        if salary and salary.amount:
            income, basis = salary.amount, "lương dự kiến, chưa ghi"
        else:
            _, average, days = flows.monthly_flows(day)
            if average and days >= 20:
                income, basis = average, "trung bình 3 tháng qua"
    debts = rules.month_debts(debt_service.debts(data), ym)  # (khoản nợ, phải trả kỳ này, đã trả kỳ này)
    debt_need = sum(need for _, need, _ in debts)
    debt_left = sum(debt_rules.month_left(d, ym) for d, _, _ in debts)
    spending = [e for e in month if e["nhom"] not in (ct.INCOME, group) and not e.get("no")]
    spent = sum(e["tien"] for e in spending)
    spent_today = sum(e["tien"] for e in spending if e["ngay"] == day.isoformat())
    spend, spend_basis = spending_estimate(day, group, debt_need)
    fund = reserve_service.status(day)
    added = reserve_repo.deposited_in(ym)
    freed, freed_names = debt_service.freed(data, ym)
    ideal, target = rules.fund_share(fund, added, freed, income, debt_need, spend)
    invest = invest_part(day)
    invest_need = invest["gop"] if invest else 0
    left = rules.leftover(income, debt_need, spend, target, invest_need)
    return {"ym": ym, "income": income, "income_basis": basis, "debts": debts, "debt_need": debt_need,
            "debt_left": debt_left, "spend": spend, "spend_basis": spend_basis, "spent": spent,
            "spent_today": spent_today, "group": group, "fund": fund,
            "fund_target": target, "fund_ideal": ideal, "fund_added": added, "fund_left": max(0, target - added),
            "freed": freed, "freed_names": freed_names, "left": left, "data": data, "invest": invest,
            "invest_left": max(0, invest_need - invest["added"]) if invest else 0}


def spendable(day, n=None):
    """Mỗi ngày được tiêu bao nhiêu, dùng chung cho tin sau khi ghi, /dubao, tổng quan và chia lương. Có ngân sách tổng
    thì theo ngân sách (tính mọi khoản chi), không thì theo kế hoạch chia lương. None nếu chưa tính được (chưa có thu nhập)."""
    from services.phantich import analysis as phantich_service  # nạp muộn: phantich cũng dùng kehoach
    f = phantich_service.forecast(day)
    budgets = budget_repo.load()
    if budgets.get("tong"):
        per_day, today_left = phantich_service.allowance(f)
        return {"per_day": per_day, "today_left": today_left, "limit": budgets["tong"], "spent": f["spent"],
                "basis": "tong", "parts": None}
    n = n or numbers(day)
    if not n["income"]:
        return None
    invest = n["invest"]["gop"] if n["invest"] else 0
    upcoming = sum(e["tien"] for e in f["upcoming"] if e["nhom"] != n["group"] and not e.get("no"))
    return rules.plan_spendable(n["income"], n["debt_need"], n["fund_target"], invest, n["spent"], n["spent_today"],
                                upcoming, f["left"])


def spendable_safe(day, n=None):
    try:
        return spendable(day, n)
    except Exception as e:
        print(f"[lỗi] mỗi ngày được tiêu: {e!r}", file=sys.stderr)
        return None


def steps(n):
    """Các việc còn lại của kế hoạch tháng: [(loại, khoản nợ hoặc None, số tiền, mã khoản nợ hoặc None)]."""
    return rules.pending_steps(n)


def next_actions(day, n=None):
    """Các việc nên làm ngay (chưa cắt còn 3): xem domain.kehoach.plan.urgent_items."""
    n = n or numbers(day)
    month_has_income = any(e["nhom"] == ct.INCOME for e in ct.load(n["ym"]))
    pending = sum(ct.pending(e) for e in ct.load(n["ym"]))
    return rules.urgent_items(n, month_has_income, pending)


def invest_held(day):
    """{loại tài sản: giá trị} tiền đã đầu tư (không tính phần gắn vào quỹ dự phòng)."""
    fund_ids = {str(it["id"]) for it in assets_repo.load()["items"] if it.get("duphong")}
    sums = {}
    for kind, rid, _, value, _, _ in valuation_service.valuation(day)["rows"]:
        if rid not in fund_ids:
            sums[kind] = sums.get(kind, 0) + value
    return sums


def roadmap(day, n):
    """Roadmap của tháng chứa day (n: số liệu chia lương)."""
    _, _, days = flows.monthly_flows(day)
    return rules.roadmap_state(n["fund"], days, debt_service.active(n["data"]), lambda d: debt_rules.schedule(d, day),
                               invest_held(day))


def main_account(day=None):
    """(tài khoản chính hoặc None, số dư của nó); số dư 0 nếu không có."""
    main = accounts.main_account()
    return (main, accounts.main_balance(main, day) if day else accounts.main_balance(main)) if main else (None, 0)


def main_account_of(data, day):
    main = accounts.main_account(data)
    return (main, accounts.main_balance(main, day)) if main else (None, 0)


def do_all(now):
    """Làm các việc còn lại của kế hoạch (tính lại lúc bấm, nên bấm hai lần không làm hai lần). None nếu không còn việc."""
    day = now.date()
    n = numbers(day)
    todo = steps(n)
    if not todo:
        return None
    result = DoAllResult(invest_fund=n["invest"]["ma"] if n["invest"] else None)
    for kind, d, amount, ref in todo:
        try:
            if kind == "no":
                e = debt_service.pay(ref, amount, now).entry
                ok = e is not None
            elif kind == "dp":
                reserve_service.change(amount, day)
                ok = True
            else:
                cfg = dautu_fund.load()
                dautu_orders.add_money(cfg, amount, dautu_market.current_period(cfg))
                dautu_fund.save(cfg)
                ok = True
        except Exception as e:
            print(f"[lỗi] làm theo kế hoạch ({kind}): {e!r}", file=sys.stderr)
            ok = False
        result.results.append(StepResult(kind, d, amount, ok))
    result.main, result.main_balance = main_account()
    return result
