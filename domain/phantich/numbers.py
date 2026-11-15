"""Số liệu chi tiêu tính từ các khoản đã ghi: dự báo cuối tháng, dự báo hằng ngày (bỏ khoản đột biến), khoản lạ thường,
nhóm tăng vọt, thói quen lặp lại. Mọi hàm nhận sẵn danh sách khoản và ngân sách, không đọc kho."""
import statistics
from calendar import monthrange
from datetime import date, timedelta

from domain.chitieu import classify
from domain.chitieu.kinds import INCOME
from domain.chitieu.learn import learn_key

LARGE = 1_000_000  # khoản từ 1tr (tiền nhà, học phí...) tính riêng, không tính vào nhịp tiêu hằng ngày
UNUSUAL_MIN, UNUSUAL_RATIO = 200_000, 3  # khoản lạ thường: từ 200k và gấp 3 lần mức thường của nhóm
SURGE_RATIO, SURGE_MIN = 1.6, 300_000  # nhóm tăng vọt: 7 ngày qua gấp 1,6 lần mức thường và nhiều hơn 300k
DAILY_DEFAULT = ["an", "cho", "xe"]  # ăn uống, đi chợ/siêu thị, đi lại
SPIKE_MIN, SPIKE_RATIO = 300_000, 3  # khoản đột biến: từ 300k và gấp 3 lần mức thường (trung vị) của nhóm


def spending(items):
    return [e for e in items if e["nhom"] != INCOME]


def total(items):
    return sum(e["tien"] for e in items)


def forecast_start(day):
    """Ngày đầu của các khoản cần đọc để dự báo tháng của day."""
    prev_first = (day.replace(day=1) - timedelta(days=1)).replace(day=1)
    return min(prev_first, day - timedelta(days=28))


def daily_start(day):
    """Ngày đầu của các khoản cần đọc để dự báo chi tiêu hằng ngày của day."""
    prev_first = (day.replace(day=1) - timedelta(days=1)).replace(day=1)
    return min(prev_first, day - timedelta(days=62))


def forecast_numbers(day, items, budgets):
    """Số liệu dự báo tháng của ngày day (dict), dùng cho /dubao, dòng sau khi ghi và cảnh báo tối.
    items: khoản chi từ forecast_start(day) tới day; budgets: ngân sách tháng {mã nhóm | "tong": hạn mức}."""
    first = day.replace(day=1)
    days = monthrange(day.year, day.month)[1]
    prev_last = first - timedelta(days=1)
    prev_first = prev_last.replace(day=1)
    window = day - timedelta(days=28)
    month = [e for e in items if e["ngay"] >= first.isoformat()]
    prev = [e for e in items if prev_first.isoformat() <= e["ngay"] <= prev_last.isoformat()]
    past = [e for e in items if window.isoformat() <= e["ngay"] < day.isoformat()]
    # Nhịp tiêu: khoản dưới 1tr trong tối đa 28 ngày đã qua, tính từ ngày đầu tiên có ghi
    history = (day - date.fromisoformat(min(e["ngay"] for e in past))).days if past else 0
    pool, span = (past, history) if history else ([e for e in month if e["ngay"] == day.isoformat()], 1)

    def rate(code=None):
        return total(e for e in pool if e["tien"] < LARGE and (code is None or e["nhom"] == code)) / span

    # Khoản lớn tháng trước có mà tháng này chưa thấy, ngày còn ở phía trước: có thể sắp tới
    seen = {learn_key(e["ghichu"]) for e in month if e["ghichu"]}
    upcoming = {}
    for e in prev:
        key = learn_key(e["ghichu"]) if e["ghichu"] else ""
        if e["tien"] >= LARGE and key and key not in seen and int(e["ngay"][8:]) > day.day:
            upcoming[key] = e
    upcoming = list(upcoming.values())
    left = days - day.day
    spent = total(month)
    groups = {}
    for code, limit in budgets.items():
        if code == "hangngay":  # ngân sách chi tiêu hằng ngày: tính ở daily_numbers
            continue
        mine = month if code == "tong" else [e for e in month if e["nhom"] == code]
        up = upcoming if code == "tong" else [e for e in upcoming if e["nhom"] == code]
        r = rate(None if code == "tong" else code)
        projected = total(mine) + r * left + total(up)
        over_day = None
        if total(mine) < limit < projected and r > 0:
            over_day = min(days, day.day + int((limit - total(mine)) // r) + 1)
        groups[code] = {"limit": limit, "spent": total(mine), "projected": projected, "over_day": over_day,
                        "upcoming": total(up)}
    return {"day": day, "days": days, "left": left, "spent": spent, "today": total(e for e in month
                                                                                  if e["ngay"] == day.isoformat()),
            "rate": rate(), "history": history, "upcoming": upcoming, "projected": spent + rate() * left
            + total(upcoming), "prev_total": total(prev), "budgets": groups}


def allowance(f):
    """(mỗi ngày còn lại được tiêu, hôm nay còn được tiêu) theo ngân sách tổng; None nếu chưa đặt."""
    budget = f["budgets"].get("tong")
    if not budget:
        return None
    room = budget["limit"] - (f["spent"] - f["today"]) - budget["upcoming"]  # chưa tính hôm nay
    per_day = room / (f["left"] + 1)
    return per_day, per_day - f["today"]


def spike_limits(items, codes):
    """{nhóm: mức tiền từ đó coi là đột biến}: gấp 3 lần trung vị các khoản của nhóm (cần từ 5 khoản), ít nhất
    300k; chưa đủ dữ liệu thì 500k."""
    limits = {}
    for code in codes:
        amounts = [e["tien"] for e in items if e["nhom"] == code]
        limits[code] = max(SPIKE_MIN, SPIKE_RATIO * statistics.median(amounts)) if len(amounts) >= 5 else 500_000
    return limits


def daily_codes(saved, cfg):
    """Các nhóm tính là chi tiêu hằng ngày: người dùng chọn (saved), mặc định ăn uống, đi chợ/siêu thị, đi lại."""
    active = classify.groups(cfg)
    codes = [c for c in (saved or DAILY_DEFAULT) if c in active and c != INCOME]
    return codes or [c for c in DAILY_DEFAULT if c in active]


def daily_numbers(day, items, codes, budgets):
    """Dự báo tháng chỉ cho chi tiêu hằng ngày, bỏ khoản đột biến: dict cho /dubao và dòng sau khi ghi.
    items: khoản chi từ daily_start(day) tới day."""
    first = day.replace(day=1)
    days = monthrange(day.year, day.month)[1]
    prev_last = first - timedelta(days=1)
    prev_first = prev_last.replace(day=1)
    window = day - timedelta(days=28)
    items = [e for e in items if e["nhom"] in codes]
    limits = spike_limits(items, codes)
    regular = [e for e in items if e["tien"] < limits[e["nhom"]]]
    month = [e for e in regular if e["ngay"] >= first.isoformat()]
    spikes = [e for e in items if e["tien"] >= limits[e["nhom"]] and e["ngay"] >= first.isoformat()]
    prev = [e for e in regular if prev_first.isoformat() <= e["ngay"] <= prev_last.isoformat()]
    past = [e for e in regular if window.isoformat() <= e["ngay"] < day.isoformat()]
    history = (day - date.fromisoformat(min(e["ngay"] for e in past))).days if past else 0
    pool, span = (past, history) if history else ([e for e in month if e["ngay"] == day.isoformat()], 1)
    rates = {c: total(e for e in pool if e["nhom"] == c) / span for c in codes}
    left = days - day.day
    spent = total(month)
    today = total(e for e in month if e["ngay"] == day.isoformat())
    # Ngân sách: "hằng ngày" nếu có; không thì cộng ngân sách các nhóm hằng ngày khi nhóm nào cũng đã đặt
    limit = budgets.get("hangngay") or (sum(budgets[c] for c in codes) if all(c in budgets for c in codes) else None)
    room = None
    if limit:
        per_day = (limit - (spent - today)) / (left + 1)  # chia đều phần còn lại cho hôm nay và các ngày tới
        room = (per_day, per_day - today)
    return {"codes": codes, "days": days, "left": left, "spent": spent, "today": today, "rates": rates,
            "rate": sum(rates.values()), "projected": spent + sum(rates.values()) * left, "history": history,
            "prev_total": total(prev), "spikes": spikes, "limits": limits, "budget": limit, "room": room,
            "elapsed": day.day}


def unusual(entries, history):
    """Khoản vừa ghi lớn bất thường so với mức thường của nhóm (trung vị, cần từ 5 khoản cùng nhóm trong history):
    [(khoản, mức thường)]."""
    big = [e for e in entries if e["nhom"] not in (INCOME, "khac") and e["tien"] >= UNUSUAL_MIN]
    out = []
    for e in big:
        same = [x["tien"] for x in history if x["nhom"] == e["nhom"]]
        if len(same) < 5:
            continue
        typical = statistics.median(same)
        if e["tien"] >= UNUSUAL_RATIO * typical and e["tien"] - typical >= UNUSUAL_MIN:
            out.append((e, typical))
    return out


def surges(items, day, codes):
    """Nhóm tiêu tăng vọt 7 ngày qua so với mức thường của 4 tuần trước: [(mã, 7 ngày qua, mức thường/tuần, các khoản
    7 ngày qua)]. items: khoản chi 34 ngày tới day; cần đủ 4 tuần dữ liệu."""
    out = []
    cut = (day - timedelta(days=7)).isoformat()
    if items and min(e["ngay"] for e in items) <= (day - timedelta(days=27)).isoformat():
        week = [e for e in items if e["ngay"] > cut]
        before = [e for e in items if e["ngay"] <= cut]
        for code in codes:
            if code == "khac":
                continue
            now_sum = total(e for e in week if e["nhom"] == code)
            usual = total(e for e in before if e["nhom"] == code) / 4
            if usual and now_sum >= SURGE_RATIO * usual and now_sum - usual >= SURGE_MIN:
                out.append((code, now_sum, usual, [e for e in week if e["nhom"] == code]))
    return out


def habits(items, fallback_label):
    """Gộp khoản cùng nội dung (bỏ số, ngày): [(nội dung, số lần, tổng tiền)] nhiều tiền nhất trước.
    fallback_label(mã nhóm): tên dùng khi khoản không có ghi chú."""
    groups = {}
    for e in items:
        key = learn_key(e["ghichu"]) if e["ghichu"] else fallback_label(e["nhom"])
        count, amount = groups.get(key, (0, 0))
        groups[key] = (count + 1, amount + e["tien"])
    return sorted(((k, c, a) for k, (c, a) in groups.items()), key=lambda x: -x[2])


def weekday_stats(items, start, end):
    """(số ngày thường, số ngày cuối tuần, tiền ngày thường, tiền cuối tuần) trong kỳ; None nếu kỳ chưa có đủ cả hai loại ngày."""
    counts = [0, 0]
    d = start
    while d <= end:
        counts[d.weekday() >= 5] += 1
        d += timedelta(days=1)
    sums = [0, 0]
    for e in items:
        sums[date.fromisoformat(e["ngay"]).weekday() >= 5] += e["tien"]
    if not all(counts):
        return None
    return counts[0], counts[1], sums[0], sums[1]
