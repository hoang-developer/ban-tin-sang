"""Màn hình phân tích chi tiêu: dự báo tháng và hằng ngày, báo khoản lạ thường và cảnh báo tối, trả lời câu hỏi, cấu hình
biểu đồ, số liệu và nhận xét. Chữ dựng từ số liệu đã tính; cfg là cấu hình nhóm của người dùng."""
import html
from datetime import date, timedelta

from domain.chitieu import classify
from domain.chitieu.kinds import INCOME
from domain.common.dates import WEEKDAYS
from domain.common.format import short, vnd
from domain.phantich import numbers
from domain.phantich.numbers import LARGE, total
from presentation.kehoach import plan as kehoach

PALETTE = ["#e8590c", "#2f9e44", "#1971c2", "#9c36b5", "#f08c00", "#0c8599", "#c2255c", "#5c940d",
           "#3b5bdb", "#868e96", "#e64980", "#1098ad", "#74b816", "#ae3ec9", "#fd7e14", "#495057"]


def vnd_round(x):
    return vnd(round(x))


def approx(x):
    """Số ước tính (nhịp tiêu, dự báo, trung bình): làm tròn tới nghìn, '232.143' thành '232.000đ'."""
    return vnd(round(x / 1000) * 1000)


def times(x):
    return f"{x:.1f}".rstrip("0").rstrip(".").replace(".", ",")


def dmy(d):
    return f"{d:%d/%m}"


def note_of(e, cfg):
    return html.escape(e["ghichu"] or classify.bare(classify.name(e["nhom"], cfg)))


def trend(change):
    """+12% -> '🔺12%' (tiêu nhiều hơn), −8% -> '🔻8%'."""
    return f"{'🔺' if change >= 0 else '🔻'}{abs(change):.0f}%"

def budget_line(code, b, cfg):
    label = "Tổng chi" if code == "tong" else classify.name(code, cfg)
    projected, limit = b["projected"], b["limit"]
    if b["spent"] >= limit:
        return f"🔴 {label}: đã vượt, {short(b['spent'])}/{short(limit)}"
    if projected > limit:
        when = f" · vượt ~ngày {b['over_day']}" if b["over_day"] else ""
        return f"🟡 {label}: ~{short(projected)}/{short(limit)}{when}"
    return f"🟢 {label}: ~{short(projected)}/{short(limit)}"

def forecast_view(f, day, spend_lines, cfg):
    """Màn hình /dubao tatca: dự báo cả tháng; spend_lines(): hàm trả các dòng \"mỗi ngày được tiêu\" (gọi khi cần)."""
    lines = [f"🔮 <b>Dự báo tháng {day.month}</b> · còn {f['left']} ngày"]
    if not f["spent"] and not f["rate"]:
        return "\n".join(lines + ["Chưa có khoản nào. Nhắn kiểu: cà phê 35k"] + spend_lines())
    lines.append(f"💸 Đã chi <b>{short(f['spent'])}</b> · ~{short(f['rate'])}/ngày (bỏ khoản từ {short(LARGE)})")
    if f["upcoming"]:
        lines.append("⏳ Sắp tới (tháng trước có): " + " · ".join(
            f"{note_of(e, cfg)} {short(e['tien'])} ({e['ngay'][8:]})" for e in f["upcoming"][:4]))
    compare = ""
    if f["prev_total"]:
        change = (f["projected"] - f["prev_total"]) / f["prev_total"] * 100
        compare = f" · tháng trước {short(f['prev_total'])} {trend(change)}"
    lines.append(f"➡️ Cả tháng ~<b>{short(f['projected'])}</b>{compare}")
    lines += spend_lines()
    budgets = [budget_line(code, b, cfg) for code, b in f["budgets"].items()]
    if budgets:
        lines += ["", "<b>🎯 Ngân sách</b>"] + budgets
    return "\n".join(lines)

def daily_label(codes, cfg):
    return ", ".join(classify.bare(classify.name(c, cfg)).lower() for c in codes)

def daily_view(f, day, spend_lines, cfg):
    """Màn hình /dubao: chi tiêu hằng ngày, không tính khoản đột biến."""
    lines = [f"🔮 <b>Chi hằng ngày tháng {day.month}</b> · còn {f['left']} ngày",
             f"<i>{html.escape(daily_label(f['codes'], cfg))}</i>"]
    if not f["spent"] and not f["rate"]:
        return "\n".join(lines + ["Chưa có khoản nào. Nhắn kiểu: cà phê 35k"] + spend_lines())
    parts = " · ".join(f"{classify.name(c, cfg).split()[0]} {short(r)}" for c, r in f["rates"].items() if r)
    lines.append(f"💸 Đã chi <b>{short(f['spent'])}</b> · hôm nay {short(f['today'])}")
    lines.append(f"📈 ~<b>{short(f['rate'])}</b>/ngày" + (f" ({parts})" if parts else ""))
    compare = ""
    if f["prev_total"]:
        change = (f["projected"] - f["prev_total"]) / f["prev_total"] * 100
        compare = f" · tháng trước {short(f['prev_total'])} {trend(change)}"
    lines.append(f"➡️ Cả tháng ~<b>{short(f['projected'])}</b>{compare}")
    if f["room"]:
        over = f" · 🔴 dự báo vượt {short(f['projected'] - f['budget'])}" if f["projected"] > f["budget"] else ""
        lines.append(kehoach.room_text(*f["room"], bold=True, what=f"ngân sách {short(f['budget'])}") + over)
    else:
        lines += spend_lines()
    if f["spikes"]:
        lines.append(f"<i>Bỏ {len(f['spikes'])} khoản đột biến: " + ", ".join(
            f"{note_of(e, cfg)} {short(e['tien'])}" for e in sorted(f["spikes"], key=lambda e: -e["tien"])[:3]) + "</i>")
    lines.append("<i>Mọi khoản: /dubao tatca</i>")
    return "\n".join(lines)

def unusual_lines(candidates, cfg):
    """Dòng báo khoản lạ thường từ [(khoản, mức thường)]."""
    return [f"👀 «{note_of(e, cfg)}» gấp {times(e['tien'] / typical)} lần thường ({classify.name(e['nhom'], cfg)} "
            f"~{short(typical)})" for e, typical in candidates]


def alert_lines(rises, overs, cfg, habit_items):
    """Dòng cảnh báo tối. rises: [(mã, 7 ngày qua, mức thường, khoản)]; overs: [(mã, số liệu ngân sách)];
    habit_items(khoản): thói quen lặp lại của các khoản đó."""
    lines = []
    for code, now_sum, usual, items in rises:
        lines.append(f"📈 {classify.name(code, cfg)}: 7 ngày qua {vnd_round(now_sum)}, gấp {times(now_sum / usual)} lần mức "
                     f"thường ({short(usual)}/tuần). Nhiều nhất: "
                     + ", ".join(habit_text(k, c, a) for k, c, a in habit_items(items)[:3]))
    for code, b in overs:
        label = "Tổng chi" if code == "tong" else classify.name(code, cfg)
        when = f" vào khoảng ngày {b['over_day']}" if b["over_day"] else " trước cuối tháng"
        lines.append(f"⏳ Theo đà này {label} sẽ vượt ngân sách {short(b['limit'])}{when} "
                     f"(dự báo cả tháng {short(b['projected'])}, đã chi {short(b['spent'])})")
    return lines

def habit_text(key, count, amount):
    return f"{html.escape(key)} {short(amount)}" + (f" ({count} lần)" if count > 1 else "")

HOI_HELP = ("🔎 Hỏi bằng câu thường, ví dụ:\n• tháng này cà phê hết bao nhiêu?\n• tuần này tiêu vào đâu nhiều nhất?\n"
            "• so tháng 10 với tháng 9\n• khoản lớn nhất tháng trước\n• liệt kê các lần đổ xăng tháng này\n"
            "• ngày nào tiêu nhiều nhất?\nGõ thẳng câu hỏi hoặc /hoi câu hỏi.")

def span_text(start, end):
    if start == end:
        return f"{WEEKDAYS[start.weekday()]} {start:%d/%m/%Y}"
    return f"{start:%d/%m}–{end:%d/%m/%Y}"

def by_group_lines(items, cfg, limit=8):
    sums = {}
    for e in items:
        sums[e["nhom"]] = sums.get(e["nhom"], 0) + e["tien"]
    whole, top = sum(sums.values()) or 1, max(sums.values(), default=1)
    return [f"{classify.name(code, cfg)}: <b>{vnd_round(amount)}</b> ({amount / whole * 100:.0f}%)\n" + "▇" * max(1, round(amount / top * 10))
            for code, amount in sorted(sums.items(), key=lambda x: -x[1])[:limit]]

def weekday_lines(items, start, end):
    """Trung bình mỗi ngày cuối tuần và ngày thường trong kỳ."""
    stats = numbers.weekday_stats(items, start, end)
    if not stats:
        return []
    weekdays, weekends, weekday_sum, weekend_sum = stats
    return [f"Ngày thường TB {approx(weekday_sum / weekdays)}/ngày · cuối tuần TB {approx(weekend_sum / weekends)}/ngày"]

def query_view(spec, items, other, cfg):
    """Trả lời một câu hỏi từ bộ lọc, các khoản khớp và (nếu so sánh) các khoản khớp ở kỳ đem so."""
    start, end = spec["tu"], spec["den"]
    what = "Thu" if spec["thu"] else "Chi"
    filters = [classify.name(c, cfg) for c in spec["nhom"]] + (
        ["có chữ «" + "/".join(html.escape(w) for w in spec["tu_khoa"]) + "»"] if spec["tu_khoa"] else [])
    lines = [f"🔎 <b>{what} {span_text(start, end)}</b>" + (" · " + " · ".join(filters) if filters else "")]
    days = (end - start).days + 1
    summary = f"Tổng: <b>{vnd_round(total(items))}</b> · {len(items)} khoản" + (
        f" · TB {approx(total(items) / days)}/ngày" if days > 1 and items else "")
    kind = spec["kieu"]
    if kind == "so_sanh":
        start2, end2 = spec["tu2"], spec["den2"]
        a, b = total(items), total(other)
        change = f"{'↑' if a >= b else '↓'} {abs(a - b) / b * 100:.0f}% ({'+' if a >= b else '−'}{vnd_round(abs(a - b))})" \
            if b else "kỳ trước chưa có khoản nào"
        lines += [f"{span_text(start, end)}: <b>{vnd_round(a)}</b> ({len(items)} khoản)",
                  f"{span_text(start2, end2)}: <b>{vnd_round(b)}</b> ({len(other)} khoản)", f"➡️ {change}"]
        if not spec["nhom"] and not spec["tu_khoa"]:
            diff = {}
            for e in items:
                diff[e["nhom"]] = diff.get(e["nhom"], 0) + e["tien"]
            for e in other:
                diff[e["nhom"]] = diff.get(e["nhom"], 0) - e["tien"]
            moves = sorted((x for x in diff.items() if x[1]), key=lambda x: -abs(x[1]))[:5]
            if moves:
                lines += ["Chênh nhiều nhất:"] + [f"{classify.name(c, cfg)}: {'+' if d > 0 else '−'}{vnd_round(abs(d))}" for c, d in moves]
        return "\n".join(lines)
    if not items:
        return "\n".join(lines + ["Không có khoản nào khớp."])
    lines.append(summary)
    if kind == "nhom":
        lines += by_group_lines(items, cfg)
    elif kind == "lon_nhat":
        lines += [f"{i}. {e['ngay'][8:]}/{e['ngay'][5:7]} <b>{vnd_round(e['tien'])}</b> · {note_of(e, cfg)}"
                  for i, e in enumerate(sorted(items, key=lambda e: -e["tien"])[:5], 1)]
    elif kind == "liet_ke":
        newest = sorted(items, key=lambda e: (e["ngay"], e.get("gio", ""), e["id"]), reverse=True)
        lines += [f"{e['ngay'][8:]}/{e['ngay'][5:7]} <b>{vnd_round(e['tien'])}</b> · {classify.name(e['nhom'], cfg).split()[0]} "
                  f"{note_of(e, cfg)}" for e in newest[:15]]
        if len(newest) > 15:
            lines.append(f"… và {len(newest) - 15} khoản nữa")
    elif kind == "theo_ngay":
        per_day = {}
        for e in items:
            per_day[e["ngay"]] = per_day.get(e["ngay"], 0) + e["tien"]
        lines += [f"{WEEKDAYS[date.fromisoformat(d).weekday()]} {d[8:]}/{d[5:7]}: <b>{vnd_round(v)}</b>"
                  for d, v in sorted(per_day.items(), key=lambda x: -x[1])[:5]]
        lines += weekday_lines(items, start, end)
    return "\n".join(lines)

def color(code, codes):
    """Màu của nhóm trong biểu đồ; codes: thứ tự mã nhóm (có sẵn rồi tự tạo)."""
    return PALETTE[codes.index(code) % len(PALETTE)] if code in codes else PALETTE[-1]


def chart_configs(items, start, end, label, cfg, codes):
    """(biểu đồ tròn theo nhóm, biểu đồ cột theo ngày hoặc None nếu kỳ chỉ một ngày, tổng chi) của khoản chi trong kỳ."""
    sums = {}
    for e in items:
        sums[e["nhom"]] = sums.get(e["nhom"], 0) + e["tien"]
    order = sorted(sums.items(), key=lambda x: -x[1])
    whole = total(items)
    plugins = {"datalabels": {"display": False}}
    pie = {"type": "doughnut", "data": {
        "labels": [f"{classify.bare(classify.name(c, cfg))} {short(v)} ({v / whole * 100:.0f}%)" for c, v in order],
        "datasets": [{"data": [v for _, v in order], "backgroundColor": [color(c, codes) for c, _ in order]}]},
        "options": {"plugins": {**plugins, "title": {"display": True, "text": f"Chi tiêu {label}: {vnd_round(whole)}",
                                                     "font": {"size": 22}},
                                "legend": {"position": "right", "labels": {"font": {"size": 16}}}}}}
    days = (end - start).days + 1
    bars = None
    if days > 1:
        per_day = {}
        for e in items:
            per_day[e["ngay"]] = per_day.get(e["ngay"], 0) + e["tien"]
        dates = [start + timedelta(days=i) for i in range(days)]
        values = [round(per_day.get(d.isoformat(), 0) / 1000) for d in dates]
        average = round(whole / days / 1000)
        datasets = [{"type": "bar", "label": "Chi trong ngày", "data": values, "backgroundColor": "#1971c2"},
                    {"type": "line", "label": f"Trung bình {average}k/ngày", "data": [average] * days,
                     "borderColor": "#e8590c", "borderDash": [6, 4], "pointRadius": 0, "fill": False}]
        bars = {"type": "bar", "data": {"labels": [f"{d.day}/{d.month}" if days > 31 else str(d.day) for d in dates],
                                        "datasets": datasets},
                "options": {"locale": "vi-VN", "plugins": {**plugins, "title": {"display": True, "font": {"size": 20},
                                                             "text": f"Chi mỗi ngày, {label} (nghìn đồng)"}},
                            "scales": {"y": {"beginAtZero": True}}}}
    return pie, bars, whole

def facts_lines(data, cfg):
    """Các dòng số liệu HTML của một kỳ (để người dùng đọc và để AI viết nhận xét); [] nếu kỳ chưa có khoản chi."""
    if data["empty"]:
        return []
    start, end = data["start"], data["end"]
    items, spend, prev, olds = data["items"], data["spend"], data["prev"], data["olds"]
    label, prev_label = data["label"], data["prev_label"]
    whole, days = total(spend), (end - start).days + 1
    lines = [f"Chi {label}: {vnd_round(whole)} · {len(spend)} khoản · TB {approx(whole / days)}/ngày"]
    if prev:
        change = (whole - total(prev)) / total(prev) * 100
        lines.append(f"So với {prev_label}: {trend(change)} ({short(total(prev))})")
    if len(olds) >= 2:
        lines.append(f"Trung bình {len(olds)} tháng trước: {approx(sum(olds) / len(olds))}")
    now_g, prev_g = {}, {}
    for e in spend:
        now_g[e["nhom"]] = now_g.get(e["nhom"], 0) + e["tien"]
    for e in prev:
        prev_g[e["nhom"]] = prev_g.get(e["nhom"], 0) + e["tien"]
    lines.append("Theo nhóm: " + " · ".join(f"{classify.name(c, cfg)} {short(v)} ({v / whole * 100:.0f}%)"
                                             for c, v in sorted(now_g.items(), key=lambda x: -x[1])[:6]))
    if prev:
        moves = sorted(((c, now_g.get(c, 0) - prev_g.get(c, 0)) for c in set(now_g) | set(prev_g)),
                       key=lambda x: -abs(x[1]))
        up = [f"{classify.name(c, cfg)} +{short(d)}" for c, d in moves if d >= 100_000][:3]
        down = [f"{classify.name(c, cfg)} −{short(-d)}" for c, d in moves if d <= -100_000][:2]
        if up:
            lines.append("🔺 " + " · ".join(up))
        if down:
            lines.append("🔻 " + " · ".join(down))
    fallback = lambda code: classify.bare(classify.name(code, cfg))  # noqa: E731
    repeat = [h for h in numbers.habits([e for e in spend if e["ghichu"]], fallback) if h[1] >= 3][:5]
    if repeat:
        lines.append("Lặp lại nhiều: " + " · ".join(f"{html.escape(k)} {c} lần {short(a)}" for k, c, a in repeat))
    biggest = sorted(spend, key=lambda e: -e["tien"])[:3]
    lines.append("Khoản lớn nhất: " + " · ".join(f"{note_of(e, cfg)} {short(e['tien'])}" for e in biggest))
    lines += weekday_lines(spend, start, end)
    first_day = date.fromisoformat(min(e["ngay"] for e in items))
    quiet = sum(1 for i in range((end - first_day).days + 1)
                if not any(e["ngay"] == (first_day + timedelta(days=i)).isoformat() for e in spend))
    if quiet:
        lines.append(f"{quiet} ngày không tiêu gì")
    income = total(e for e in items if e["nhom"] == INCOME)
    if income:
        saved = income - whole
        lines.append(f"Thu {short(income)} → " + (f"🟢 dư {short(saved)} ({saved / income * 100:.0f}% thu)"
                                                   if saved >= 0 else f"🔴 chi vượt thu {short(-saved)}"))
    return lines


def commentary_view(label, lines, notes):
    """Số liệu của kỳ kèm nhận xét của AI (nếu có)."""
    text = [f"📌 <b>Số liệu {label}</b>"] + [f"• {line}" for line in lines]
    if not notes:
        return "\n".join(text)
    return "\n".join(text + ["", "💬 <b>Nhận xét</b>"] + [html.escape(n) for n in notes])
