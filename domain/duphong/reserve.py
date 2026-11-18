"""Quỹ dự phòng: mục tiêu đủ 3–12 tháng chi thiết yếu, mốc khởi đầu 1 tháng, đạt trong N tháng. Quy tắc thuần."""
from dataclasses import dataclass, field
from datetime import date

from domain.common.dates import add_months

FUND_NAME = "Quỹ dự phòng"
ESSENTIAL = ["an", "cho", "xe", "nha", "khoe", "hoc", "giadinh"]  # không tính nhóm Trả nợ: nợ đã có kế hoạch trả riêng
MONTHLY_BILLS = ["nha", "hoc"]  # chi theo kỳ (tiền nhà, hóa đơn, học phí): mỗi tháng trả một lần, không nhân theo ngày
MONTHS_CHOICES, DEADLINE_CHOICES = (3, 6, 9, 12), (6, 12, 18, 24)
MIN_DAYS = 14  # ít nhất 2 tuần ghi chép mới tự tính chi thiết yếu (ít hơn thì một khoản lớn làm sai lệch cả tháng)


@dataclass
class ReserveStatus:
    months: int  # mục tiêu: đủ bao nhiêu tháng chi
    deadline_months: int  # đạt mục tiêu trong bao nhiêu tháng
    deadline: date
    monthly: float  # chi thiết yếu mỗi tháng (tự đặt hoặc tự tính); 0 nếu chưa đủ dữ liệu
    auto: float  # chi thiết yếu bot tự tính
    manual: bool  # chi thiết yếu do người dùng tự đặt
    by_group: dict  # {mã nhóm: chi/tháng}
    group_labels: dict  # {mã nhóm: tên hiển thị}
    days: int  # số ngày có dữ liệu chi
    rows: list  # [(tên, giá trị)] các tài sản tính vào quỹ
    has_other_funds: bool  # có tài sản khác tài khoản "Quỹ dự phòng" tính vào quỹ
    balance: float
    target: float
    missing: float
    covered: float  # số dư đủ cho bao nhiêu tháng chi
    months_left: int
    per_month: float  # mỗi tháng cần để bao nhiêu để kịp hạn
    surplus: float | None  # thu − chi trung bình mỗi tháng; None nếu chưa đủ dữ liệu
    overdue: bool


def monthly_amounts(totals, bills, days):
    """Chi thiết yếu mỗi tháng từ tổng chi trong `days` ngày có dữ liệu. Chi hằng ngày (ăn, chợ, đi lại...) quy theo số
    ngày; chi theo kỳ (nhà, hóa đơn, học: nhóm trong `bills`) chia theo số tháng đã qua, tối thiểu một
    tháng, vì tháng nào cũng chỉ trả một lần (15 ngày dữ liệu có một lần trả nhà thì vẫn là một tháng, không nhân đôi)."""
    months = max(1, round(days / 30.4))
    return {c: v / months if c in bills else v * 30.4 / days for c, v in totals.items()}


def build_status(cfg, day, essential, rows, flows, group_labels=None, has_other_funds=False):
    """cfg: cấu hình quỹ. essential: (chi thiết yếu tự tính, {nhóm: chi/tháng}, số ngày dữ liệu).
    rows: [(tên, giá trị)]. flows: (chi, thu, số ngày) bình quân của sổ."""
    months = cfg.get("thang", 6)
    deadline_months = cfg.get("han", 12)
    start = date.fromisoformat(cfg["bat_dau"]) if cfg.get("bat_dau") else day
    auto, by_group, days = essential
    monthly = cfg.get("chi") or (auto if days >= MIN_DAYS else 0)
    balance = sum(v for _, v in rows)
    target = monthly * months
    missing = max(0, target - balance)
    deadline = add_months(start, deadline_months)
    months_left = (deadline.year - day.year) * 12 + deadline.month - day.month - (deadline.day < day.day)
    months_left = max(1, months_left)
    spend, income, flow_days = flows
    surplus = income - spend if income and flow_days >= 20 else None
    return ReserveStatus(
        months=months, deadline_months=deadline_months, deadline=deadline, monthly=monthly, auto=auto,
        manual=bool(cfg.get("chi")), by_group=by_group, group_labels=group_labels or {}, days=days, rows=rows,
        has_other_funds=has_other_funds, balance=balance, target=target, missing=missing,
        covered=balance / monthly if monthly else 0, months_left=months_left,
        per_month=missing / months_left if missing else 0, surplus=surplus, overdue=deadline <= day and missing > 0)


def milestone(before, after):
    """Mốc vừa vượt khi số dư tăng (đủ 1 tháng, 3 tháng, đạt mục tiêu): câu mô tả, hoặc None."""
    for mark, label in ((1, "đủ 1 tháng chi"), (3, "đủ 3 tháng chi"), (after.months, "ĐẠT MỤC TIÊU")):
        if after.monthly and before.covered < mark <= after.covered:
            return label
    return None


def record_deposit(cfg, day, amount):
    """Cấu hình sau khi nạp/rút: có ngày bắt đầu; nạp (amount > 0) thì cộng vào số đã nạp của tháng (12 tháng gần nhất)."""
    cfg = dict(cfg)
    if not cfg.get("bat_dau"):
        cfg["bat_dau"] = day.isoformat()
    if amount > 0:
        ym = day.strftime("%Y-%m")
        added = dict(cfg.get("nap", {}))
        added[ym] = added.get(ym, 0) + amount
        cfg["nap"] = dict(sorted(added.items())[-12:])
    return cfg


@dataclass
class Change:
    """Kết quả một lần nạp (amount > 0) hoặc rút (amount < 0) quỹ."""
    amount: int
    before: ReserveStatus
    after: ReserveStatus
    moved: str | None  # câu báo tiền đi/về tài khoản chính (taisan.move_main), hoặc None
    milestone: str | None = None


@dataclass
class Toggle:
    """Kết quả /duphong tinh <tên>: tính (hoặc bỏ) một tài sản vào quỹ."""
    name: str  # tên người dùng gõ
    found: bool
    label: str | None = None
    enabled: bool = False
    available: list = field(default_factory=list)  # tên các tài sản chọn được, khi không thấy
