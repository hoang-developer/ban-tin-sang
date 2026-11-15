"""Tiết kiệm từ khi dùng bot: chi lặt vặt mỗi ngày so với mốc trước khi dùng bot, chuỗi ngày ghi chép, mốc thành tích.

- Mốc: chi lặt vặt (mỗi khoản dưới 1 triệu, không tính thu nhập, trả nợ) trung bình mỗi ngày trước khi dùng bot.
  Mặc định 323.700đ/ngày, tính từ sao kê thẻ tín dụng và tài khoản thanh toán 11/09–20/10/2026 (đã bỏ trả thẻ, chuyển
  giữa tài khoản của mình, trả nợ, khoản mua hộ; trừ tiền bạn bè trả lại). Đổi: /tietkiem moc 300k.
- Ngày có ghi: có ít nhất một khoản chi, hoặc bấm "Hôm nay không tiêu". Chỉ ngày có ghi mới được tính: bớt được = mốc −
  chi lặt vặt của ngày đó. Ngày không ghi gì thì bỏ qua (không ghi không phải là tiết kiệm). Hôm nay chưa hết ngày nên
  chưa cộng vào số đã bớt.
- Chuỗi ngày ghi chép: ghi bù ngày hôm qua thì chuỗi vẫn giữ. Nghiên cứu (Silverman & Barasch 2023) cho thấy chuỗi bị đứt
  làm giảm động lực, cho sửa lại thì đỡ; nên bot không nhấn vào chuyện đứt chuỗi, chỉ hiện chuỗi hiện tại và kỷ lục.
- Đã để dành thật: tiền nạp quỹ dự phòng, góp đầu tư, trả nợ từ ngày bắt đầu. "Chi ít hơn mốc" chỉ thành tiền để dành
  khi chuyển đi nên có nút chuyển phần đã bớt vào quỹ chờ đầu tư hoặc quỹ dự phòng.
Luật thuần: không kho, không chữ hiển thị.
"""
from dataclasses import dataclass, field
from datetime import date, timedelta

DEFAULT_BASE = 323_700
DEFAULT_START = "2026-11-04"
SMALL = 1_000_000  # khoản lặt vặt: dưới 1 triệu (khoản lớn, thất thường không tính, giống cách tính mốc)
STREAK_MARKS = (7, 30, 100, 365)
SAVED_MARKS = (1_000_000, 5_000_000, 10_000_000, 20_000_000, 50_000_000, 100_000_000)


def with_defaults(stored):
    """Cấu hình đầy đủ: {"moc", "bat_dau", "khong_tieu", "nhac", "da_chuyen"} cộng các giá trị đã lưu."""
    return {"moc": DEFAULT_BASE, "bat_dau": DEFAULT_START, "khong_tieu": [], "nhac": True, "da_chuyen": 0,
            **(stored or {})}


def is_debt(entry, debt_group):
    """Khoản trả nợ (đánh dấu nợ, hoặc thuộc nhóm trả nợ): không tính vào chi lặt vặt."""
    return bool(entry.get("no")) or (debt_group is not None and entry["nhom"] == debt_group)


def collect_days(cfg, today, entries, debt_group, income_code):
    """({ngày: chi lặt vặt}, {ngày có ghi}) từ các khoản đã ghi và các ngày bấm "không tiêu"."""
    small, logged = {}, set()
    for e in entries:
        if e["nhom"] == income_code:
            continue
        d = date.fromisoformat(e["ngay"])
        logged.add(d)
        if e["tien"] < SMALL and not is_debt(e, debt_group):
            small[d] = small.get(d, 0) + e["tien"]
    logged |= {date.fromisoformat(x) for x in cfg["khong_tieu"] if cfg["bat_dau"] <= x <= today.isoformat()}
    return small, logged


def streaks(logged, today):
    """(chuỗi hiện tại, kỷ lục). Hôm nay chưa ghi thì chuỗi tính tới hôm qua (vẫn còn, chưa đứt)."""
    d = today if today in logged else today - timedelta(days=1)
    current = 0
    while d in logged:
        current += 1
        d -= timedelta(days=1)
    best = run = 0
    prev = None
    for d in sorted(logged):
        run = run + 1 if prev and (d - prev).days == 1 else 1
        best = max(best, run)
        prev = d
    return current, best


@dataclass
class Progress:
    base: int  # mốc chi lặt vặt mỗi ngày
    start: date
    saved: float  # đã bớt so với mốc từ ngày bắt đầu (âm: chi hơn mốc)
    days: int  # số ngày có ghi đã qua
    elapsed: int  # số ngày đã qua từ ngày bắt đầu (không tính hôm nay)
    month_saved: float
    month_days: int
    avg: float | None  # chi lặt vặt trung bình mỗi ngày đã qua; None nếu chưa có ngày nào
    spent_today: float
    today_logged: bool
    yesterday_logged: bool
    streak: int
    best: int
    real: dict  # {"duphong", "dautu", "tra_no"}: tiền đã để dành thật
    weeks: list  # [(thứ Hai, chi TB/ngày, số ngày)] 4 tuần gần nhất
    movable: int  # phần đã bớt chưa chuyển đi, làm tròn 100k
    cfg: dict = field(repr=False, default_factory=dict)

    @property
    def real_total(self):
        return sum(self.real.values())


def build_progress(cfg, today, small, logged, real):
    base = cfg["moc"]
    past = sorted(d for d in logged if d < today)  # hôm nay chưa hết ngày: chưa cộng
    saved = sum(base - small.get(d, 0) for d in past)
    month = [d for d in past if d.month == today.month and d.year == today.year]
    start = date.fromisoformat(cfg["bat_dau"])
    elapsed = max(0, (today - start).days)  # số ngày đã qua (không tính hôm nay)
    current, best = streaks(logged, today)
    spent_past = sum(small.get(d, 0) for d in past)
    weeks = []
    for i in range(4):  # 4 tuần gần nhất (thứ Hai–Chủ nhật), chỉ ngày đã qua và có ghi
        monday = today - timedelta(days=today.weekday() + 7 * i)
        days = [d for d in past if monday <= d < monday + timedelta(days=7)]
        if days:
            weeks.append((monday, sum(small.get(d, 0) for d in days) / len(days), len(days)))
    return Progress(
        base=base, start=start, saved=saved, days=len(past), elapsed=elapsed,
        month_saved=sum(base - small.get(d, 0) for d in month), month_days=len(month),
        avg=spent_past / len(past) if past else None, spent_today=small.get(today, 0),
        today_logged=today in logged, yesterday_logged=today - timedelta(days=1) in logged,
        streak=current, best=best, real=real, weeks=weeks,
        movable=max(0, saved - cfg.get("da_chuyen", 0)) // 100_000 * 100_000, cfg=cfg)


def week_part(base, small, logged, monday, today):
    """(số ngày có ghi từ thứ Hai tới hôm nay, số đã bớt trong các ngày đó)."""
    days = [d for d in logged if monday <= d <= today]
    return len(days), sum(base - small.get(d, 0) for d in days)


def reached_streak_marks(p):
    return [n for n in STREAK_MARKS if p.streak >= n]


def reached_saved_marks(p):
    return [m for m in SAVED_MARKS if p.saved >= m]


@dataclass
class Milestones:
    """Mốc thành tích vừa đạt lần đầu (mỗi mốc chỉ báo một lần)."""
    streak: list = field(default_factory=list)
    saved: list = field(default_factory=list)


@dataclass
class NoSpend:
    """Kết quả đánh dấu một ngày không tiêu gì."""
    status: str  # "ngoai_pham_vi" | "da_co_chi" | "ok"
    when: str = ""  # "hôm nay" | "hôm qua"
    progress: Progress | None = None
    milestones: Milestones | None = None


@dataclass
class PeriodInfo:
    """Số đã bớt cho dòng tổng kết tuần/tháng. week_days/week_saved chỉ có khi là tổng kết tuần."""
    progress: Progress
    week_days: int | None = None
    week_saved: float | None = None


@dataclass
class InvestMove:
    """Kết quả chuyển phần đã bớt vào quỹ chờ đầu tư."""
    fund: str
    left: float
    notes: list
