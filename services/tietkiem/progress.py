"""Tiết kiệm từ khi dùng bot: tính tiến độ, đánh dấu ngày không tiêu, mừng mốc, chuyển phần đã bớt đi.

Trả kết quả có cấu trúc (domain.tietkiem.progress), không trả chữ.
"""
import sys
from datetime import date, timedelta

from domain.chitieu.kinds import INCOME
from repositories.chitieu import ledger as ledger_repo
from domain.tietkiem import progress as rules
from domain.tietkiem.progress import InvestMove, Milestones, NoSpend, PeriodInfo
from domain.dautu.plan import is_active
from repositories.dautu import fund as dautu_fund
from repositories.duphong import reserve as reserve_repo
from repositories.tietkiem import progress as progress_repo
from services.dautu import market as dautu_market
from services.dautu import orders as dautu_orders
from services.duphong import reserve as reserve_service
from services.no import debt as debt_service


def debt_group():
    try:
        return debt_service.debt_group()[0]
    except Exception as e:
        print(f"[lỗi] nhóm trả nợ: {e!r}", file=sys.stderr)
        return None


def days_data(cfg, today):
    """({ngày: chi lặt vặt}, {ngày có ghi}, các khoản từ ngày bắt đầu) tới hết hôm nay."""
    start = date.fromisoformat(cfg["bat_dau"])
    if today < start:
        return {}, set(), []
    entries = ledger_repo.between(start, today)
    small, logged = rules.collect_days(cfg, today, entries, debt_group(), INCOME)
    return small, logged, entries


def real_saved(cfg, entries):
    """{"duphong", "dautu", "tra_no"}: tiền đã để dành thật từ tháng bắt đầu."""
    ym = cfg["bat_dau"][:7]
    out = {"duphong": 0, "dautu": 0, "tra_no": 0}
    try:
        out["duphong"] = sum(v for k, v in reserve_repo.load().get("nap", {}).items() if k >= ym)
    except Exception as e:
        print(f"[lỗi] quỹ dự phòng trong /tietkiem: {e!r}", file=sys.stderr)
    try:
        out["dautu"] = sum(v for k, v in dautu_fund.load().get("nap", {}).items() if k >= ym)
    except Exception as e:
        print(f"[lỗi] đầu tư trong /tietkiem: {e!r}", file=sys.stderr)
    group = debt_group()
    out["tra_no"] = sum(e["tien"] for e in entries if e["nhom"] != INCOME and rules.is_debt(e, group))
    return out


def summary(today, cfg=None):
    """Progress của ngày today."""
    cfg = cfg or progress_repo.load()
    small, logged, entries = days_data(cfg, today)
    return rules.build_progress(cfg, today, small, logged, real_saved(cfg, entries))


def claim_milestones(p):
    """Các mốc vừa đạt lần đầu (đã đánh dấu để không báo lại)."""
    return Milestones(streak=[n for n in rules.reached_streak_marks(p) if progress_repo.claim_streak_mark(n)],
                      saved=[m for m in rules.reached_saved_marks(p) if progress_repo.claim_saved_mark(m)])


def after_record(entries, day):
    """(Progress, Milestones) để thêm dòng dưới tin "Đã ghi"; None nếu chưa cần (chỉ thu nhập, hoặc trước ngày bắt đầu)."""
    if not any(e["nhom"] != INCOME for e in entries):
        return None
    p = summary(day)
    if day < p.start:
        return None
    return p, claim_milestones(p)


def home(day):
    """Progress cho dòng tổng quan; None trước ngày bắt đầu."""
    p = summary(day)
    return None if day < p.start else p


def mark_no_spend(day_iso, today):
    """Đánh dấu một ngày (hôm nay hoặc hôm qua) không tiêu gì."""
    cfg = progress_repo.load()
    if not cfg["bat_dau"] <= day_iso <= today.isoformat() or (today - date.fromisoformat(day_iso)).days > 1:
        return NoSpend("ngoai_pham_vi")
    when = "hôm nay" if day_iso == today.isoformat() else "hôm qua"
    if any(e["ngay"] == day_iso and e["nhom"] != INCOME for e in ledger_repo.load(day_iso[:7])):
        return NoSpend("da_co_chi", when)
    if day_iso not in cfg["khong_tieu"]:
        cfg["khong_tieu"] = sorted(cfg["khong_tieu"] + [day_iso])[-1000:]
        progress_repo.save(cfg)
    p = summary(today)
    return NoSpend("ok", when, p, claim_milestones(p))


def reminder(day):
    """Progress để nhắc 21h khi hôm nay chưa ghi gì; None nếu không cần nhắc (tắt nhắc, trước ngày bắt đầu, đã ghi)."""
    cfg = progress_repo.load()
    if not cfg.get("nhac", True):
        return None
    p = summary(day, cfg)
    if day < p.start or p.today_logged:
        return None
    return p


def period(kind, day):
    """PeriodInfo cho dòng tổng kết tuần ("tuan") hoặc tháng; None nếu chưa có ngày nào."""
    p = summary(day)
    if not p.days:
        return None
    if kind != "tuan":
        return PeriodInfo(p)
    monday = day - timedelta(days=day.weekday())
    small, logged, _ = days_data(p.cfg, day)
    count, part = rules.week_part(p.base, small, logged, monday, day)
    return PeriodInfo(p, count, part)


# ---- Cài đặt -----------------------------------------------------------------------------

def set_base(amount):
    cfg = progress_repo.load()
    cfg["moc"] = amount
    progress_repo.save(cfg)


def set_start(when):
    cfg = progress_repo.load()
    cfg["bat_dau"] = when.isoformat()
    progress_repo.save(cfg)


def set_reminder(on):
    cfg = progress_repo.load()
    cfg["nhac"] = on
    progress_repo.save(cfg)
    return on


def toggle_reminder():
    """Đảo bật/tắt nhắc 21h; trả trạng thái mới."""
    cfg = progress_repo.load()
    cfg["nhac"] = not cfg.get("nhac", True)
    progress_repo.save(cfg)
    return cfg["nhac"]


def reminder_on():
    return progress_repo.load().get("nhac", True)


# ---- Chuyển phần đã bớt thành tiền để dành thật ------------------------------------------------

def invest_fund():
    """Mã quỹ chờ đầu tư đang bật (để hiện nút chuyển vào quỹ chờ), None nếu không có."""
    try:
        cfg = dautu_fund.load()
        if is_active(cfg):
            return cfg["ma"]
    except Exception as e:
        print(f"[lỗi] nút chuyển đầu tư: {e!r}", file=sys.stderr)
    return None


def _mark_moved(amount):
    cfg = progress_repo.load()
    cfg["da_chuyen"] = cfg.get("da_chuyen", 0) + amount
    progress_repo.save(cfg)


def move_to_invest(amount):
    cfg_dt = dautu_fund.load()
    notes = []
    left = dautu_orders.add_money(cfg_dt, amount, dautu_market.current_period(cfg_dt), notes=notes)
    dautu_fund.save(cfg_dt)
    _mark_moved(amount)
    return InvestMove(cfg_dt["ma"], left, notes)


def move_to_reserve(amount, day):
    change = reserve_service.change(amount, day)
    _mark_moved(amount)
    return change
