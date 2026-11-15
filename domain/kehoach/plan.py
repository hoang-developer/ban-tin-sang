"""Kế hoạch tài chính: lộ trình xây tài sản và chia lương mỗi tháng. Luật thuần: không kho, không chữ hiển thị.

Lộ trình 5 bước, thứ tự thường gặp trong sách tài chính cá nhân:
  1. Ghi chép chi tiêu ít nhất 2 tuần (để biết mỗi tháng tiêu bao nhiêu)
  2. Quỹ dự phòng mốc đầu: 1 tháng chi thiết yếu
  3. Trả hết nợ có lãi (thẻ tín dụng, trả góp, vay tiêu dùng)
  4. Quỹ dự phòng đủ mục tiêu (mặc định 6 tháng chi thiết yếu)
  5. Đầu tư đều mỗi tháng: tiết kiệm, vàng, ETF, cổ phiếu
Nợ không lãi (người thân) trả đều theo hẹn, song song với mọi bước.

Chia lương: thu tháng này → trả nợ tới kỳ → chi tiêu (trung bình 90 ngày qua, không tính trả nợ; có ngân sách tổng thì
theo ngân sách) → quỹ dự phòng (mức mỗi tháng để kịp hạn, cộng tiền trước đây trả các khoản nợ đã xong) → phần còn lại.

Số liệu chia lương (numbers) và mỗi ngày được tiêu (spendable) là dict rộng, nhiều màn hình đọc theo khóa: giữ dạng dict,
kiểu riêng làm khi tách các màn hình đó (plan.md).
"""
from dataclasses import dataclass, field
from datetime import date

from domain.duphong.reserve import MIN_DAYS
from domain.no.debt import is_due, month_left, paid_in

INVEST = (("tietkiem", "tiết kiệm"), ("vang", "vàng"), ("etf", "ETF"), ("quy", "quỹ mở"), ("cp", "cổ phiếu"))
STEP_MIN = 100_000  # việc nạp quỹ/đầu tư nhỏ hơn mức này thì bỏ qua


def estimate_spend(budget_total, debt_need, items, day, manual):
    """(chi tiêu dự kiến tháng này không tính trả nợ, cách tính). items: các khoản chi 90 ngày qua (đã bỏ thu nhập, trả
    nợ); manual: mức chi thiết yếu người dùng tự đặt (hoặc None)."""
    if budget_total:  # ngân sách tổng tính mọi khoản chi, kể cả trả nợ
        return max(0, budget_total - debt_need), "ngân sách tổng"
    if not items:
        return (manual, "tự đặt") if manual else (0, None)
    days = (day - date.fromisoformat(min(e["ngay"] for e in items))).days + 1
    average = sum(e["tien"] for e in items) / days * 30.4
    if days < MIN_DAYS:
        if manual:
            return manual, "tự đặt"
        return average, f"TB {days} ngày"
    return average, f"TB {days} ngày"


def month_debts(debts, ym):
    """[(khoản nợ, phải trả kỳ này, đã trả kỳ này)] của các khoản tới kỳ và còn dư hoặc đã trả trong tháng."""
    out = []
    for d in debts:
        paid = paid_in(d, ym)
        if is_due(d, ym) and (d["tien"] > 0 or paid):
            out.append((d, min(d["thang"], d["tien"] + paid), paid))
    return out


def fund_share(fund, added, freed, income, debt_need, spend):
    """(mức nạp quỹ dự phòng lý tưởng mỗi tháng, mức nên nạp tháng này). fund: ReserveStatus; added: đã nạp trong tháng;
    freed: tiền mỗi tháng được giải phóng nhờ các khoản nợ đã trả xong."""
    target = ideal = 0
    if fund.monthly and fund.missing > 0:
        base = fund.missing + added  # còn thiếu tính từ đầu tháng: nạp đủ mức tháng này thì không bị gợi ý thêm
        ideal = min(max(base / fund.months_left, freed), base)
        ideal = int(round(ideal, -5)) or STEP_MIN
        target = ideal
        if income:  # không gợi ý nạp quá phần thu còn lại sau trả nợ và chi tiêu
            room = int(round(income - debt_need - spend, -5))
            target = max(added, min(ideal, max(0, room)))
    return ideal, target


def leftover(income, debt_need, spend, fund_target, invest_need):
    """Phần còn lại sau khi chia (âm là thiếu); None nếu chưa có thu nhập."""
    return income - debt_need - spend - fund_target - invest_need if income else None


def plan_spendable(income, debt_need, fund_target, invest, spent, spent_today, upcoming, days_left):
    """Mỗi ngày được tiêu theo kế hoạch chia lương: thu − trả nợ − quỹ dự phòng − đầu tư là phần chi tiêu cả tháng
    (không tính trả nợ); trừ phần đã chi trước hôm nay và khoản lớn sắp tới, chia đều cho hôm nay và các ngày còn lại."""
    limit = income - debt_need - fund_target - invest
    room = limit - (spent - spent_today) - upcoming
    per_day = room / (days_left + 1)
    parts = [("thu", income), ("trả nợ", debt_need), ("quỹ dự phòng", fund_target), ("đầu tư", invest)]
    return {"per_day": per_day, "today_left": per_day - spent_today, "limit": limit, "spent": spent,
            "basis": "plan", "parts": parts}


def pending_steps(n):
    """Các việc còn lại của kế hoạch tháng: [(loại, khoản nợ hoặc None, số tiền, mã khoản nợ hoặc None)]; loại: no, dp, dt."""
    out = [("no", d, month_left(d, n["ym"]), d["id"]) for d, _, _ in n["debts"] if month_left(d, n["ym"])]
    if n["fund_left"] >= STEP_MIN:
        out.append(("dp", None, n["fund_left"], None))
    if n["invest_left"] >= STEP_MIN:
        out.append(("dt", None, n["invest_left"], None))
    return out


def urgent_items(n, month_has_income, pending_count):
    """Các việc nên làm ngay theo thứ tự ưu tiên: [("no", khoản nợ, còn phải trả) | ("dp", số tiền) | ("ghi_chep", số ngày)
    | ("chuaxep", số khoản)]. Người gọi lấy tối đa 3."""
    out = []
    for d, _, _ in n["debts"]:
        left = month_left(d, n["ym"])
        if left:
            out.append(("no", d, left))
    topped = n["fund_added"] and n["fund_left"] < 0.3 * n["fund_target"]  # đã nạp gần đủ: số lệch nhỏ do trung bình chi đổi
    if n["fund_left"] >= STEP_MIN and month_has_income and not topped:
        out.append(("dp", n["fund_left"]))
    if not n["fund"].monthly:
        out.append(("ghi_chep", n["fund"].days))
    if pending_count:
        out.append(("chuaxep", pending_count))
    return out


@dataclass
class Roadmap:
    """Trạng thái 5 bước lộ trình."""
    done: list  # 5 cờ: đã xong từng bước
    current: int  # bước đang làm (bước đầu tiên chưa xong)
    days: int  # số ngày đã ghi chép
    debts: list  # các khoản nợ còn dư
    bearing: list  # nợ có lãi
    zero: list  # nợ không lãi
    bearing_last: str | None  # tháng trả xong khoản nợ có lãi xong muộn nhất, nếu đủ thông tin
    held: dict = field(default_factory=dict)  # {loại tài sản: giá trị} tiền đã đầu tư (không tính phần gắn vào quỹ dự phòng)


def roadmap_state(fund, days, active_debts, schedule_of, held):
    """fund: ReserveStatus; days: số ngày có dữ liệu chi; schedule_of(d): (số kỳ, tháng xong) hoặc None."""
    bearing = [d for d in active_debts if d.get("lai") != 0]  # chưa rõ lãi: tính như có lãi cho chắc
    zero = [d for d in active_debts if d.get("lai") == 0]
    last = None
    if bearing:
        ends = [schedule_of(d) for d in bearing]
        last = max(s[1] for s in ends) if all(ends) else None
    done = [days >= MIN_DAYS, bool(fund.monthly and fund.covered >= 1), not bearing,
            bool(fund.monthly and not fund.missing), False]
    current = next((i for i, flag in enumerate(done) if not flag), len(done) - 1)
    return Roadmap(done, current, days, active_debts, bearing, zero, last, held)


@dataclass
class StepResult:
    kind: str
    debt: dict | None
    amount: float
    ok: bool


@dataclass
class DoAllResult:
    """Kết quả làm hết theo kế hoạch."""
    results: list = field(default_factory=list)
    invest_fund: str | None = None
    main: dict | None = None  # tài khoản chính sau khi làm (hoặc None)
    main_balance: float = 0
