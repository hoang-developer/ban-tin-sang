"""Hiểu mình tiêu thế nào: dự báo cuối tháng, báo bất thường, hỏi bằng câu thường, biểu đồ, nhận xét.

Mọi con số do code tính từ sổ chi tiêu (sochitieu.py). AI, nếu bật, chỉ làm hai việc: hiểu câu hỏi
thành bộ lọc (khoảng ngày, nhóm, từ khóa) và viết nhận xét từ số liệu đã tính sẵn. AI lỗi hay hết lượt
thì bot vẫn trả lời bằng cách hiểu câu hỏi đơn giản hơn, hoặc chỉ đưa số liệu.
"""
import html
import json
import re
import statistics
import sys
import urllib.request
from calendar import monthrange
from datetime import date, timedelta

import kho
import sochitieu as ct
from bantin import WEEKDAYS

LARGE = 1_000_000  # khoản từ 1tr (tiền nhà, học phí...) tính riêng, không tính vào nhịp tiêu hằng ngày
UNUSUAL_MIN, UNUSUAL_RATIO = 200_000, 3  # khoản lạ thường: từ 200k và gấp 3 lần mức thường của nhóm
SURGE_RATIO, SURGE_MIN = 1.6, 300_000  # nhóm tăng vọt: 7 ngày qua gấp 1,6 lần mức thường và nhiều hơn 300k
CHART_URL = "https://quickchart.io/chart"  # vẽ biểu đồ Chart.js thành ảnh PNG; chỉ gửi tên nhóm và số tiền
PALETTE = ["#e8590c", "#2f9e44", "#1971c2", "#9c36b5", "#f08c00", "#0c8599", "#c2255c", "#5c940d",
           "#3b5bdb", "#868e96", "#e64980", "#1098ad", "#74b816", "#ae3ec9", "#fd7e14", "#495057"]


def spending(items):
    return [e for e in items if e["nhom"] != ct.INCOME]


def total(items):
    return sum(e["tien"] for e in items)


def short(x):
    """Số tiền gọn: 1.250.000 -> '1,25tr', 35.000 -> '35k'."""
    if abs(x) >= 1_000_000:
        return f"{x / 1e6:.2f}".rstrip("0").rstrip(".").replace(".", ",") + "tr"
    return f"{round(x / 1000)}k"


def approx(x):
    """Số ước tính (nhịp tiêu, dự báo, trung bình): làm tròn tới nghìn, '232.143' thành '232.000đ'."""
    return ct.vnd(round(x / 1000) * 1000)


def times(x):
    return f"{x:.1f}".rstrip("0").rstrip(".").replace(".", ",")


def dmy(d):
    return f"{d:%d/%m}"


def note_of(e):
    return html.escape(e["ghichu"] or ct.bare(ct.name(e["nhom"])))


# ---- Dự báo cuối tháng ---------------------------------------------------------------

def forecast(day):
    """Số liệu dự báo tháng của ngày day (dict), dùng cho /dubao, dòng sau khi ghi và cảnh báo tối."""
    first = day.replace(day=1)
    days = monthrange(day.year, day.month)[1]
    prev_last = first - timedelta(days=1)
    prev_first = prev_last.replace(day=1)
    window = day - timedelta(days=28)
    items = spending(ct.between(min(prev_first, window), day))
    month = [e for e in items if e["ngay"] >= first.isoformat()]
    prev = [e for e in items if prev_first.isoformat() <= e["ngay"] <= prev_last.isoformat()]
    past = [e for e in items if window.isoformat() <= e["ngay"] < day.isoformat()]
    # Nhịp tiêu: khoản dưới 1tr trong tối đa 28 ngày đã qua, tính từ ngày đầu tiên có ghi
    history = (day - date.fromisoformat(min(e["ngay"] for e in past))).days if past else 0
    pool, span = (past, history) if history else ([e for e in month if e["ngay"] == day.isoformat()], 1)

    def rate(code=None):
        return total(e for e in pool if e["tien"] < LARGE and (code is None or e["nhom"] == code)) / span

    # Khoản lớn tháng trước có mà tháng này chưa thấy, ngày còn ở phía trước: có thể sắp tới
    seen = {ct.learn_key(e["ghichu"]) for e in month if e["ghichu"]}
    upcoming = {}
    for e in prev:
        key = ct.learn_key(e["ghichu"]) if e["ghichu"] else ""
        if e["tien"] >= LARGE and key and key not in seen and int(e["ngay"][8:]) > day.day:
            upcoming[key] = e
    upcoming = list(upcoming.values())
    left = days - day.day
    spent = total(month)
    groups = {}
    for code, limit in kho.get(ct.K_BUDGET, {}).items():
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


def budget_line(code, b):
    label = "Tổng chi" if code == "tong" else ct.name(code)
    projected, limit = b["projected"], b["limit"]
    if b["spent"] >= limit:
        return f"🚨 {label}: đã vượt, {vnd(b['spent'])} / {vnd(limit)}"
    if projected > limit:
        when = f", vượt khoảng ngày {b['over_day']}" if b["over_day"] else ""
        return f"⚠️ {label}: dự báo {short(projected)} / {short(limit)}{when}"
    return f"✅ {label}: dự báo {short(projected)} / {short(limit)}"


def vnd(x):
    return ct.vnd(round(x))


def forecast_text(day):
    if not kho.ready():
        return ct.NEED_STORE
    f = forecast(day)
    lines = [f"🔮 <b>Dự báo chi tiêu tháng {day.month}</b> (hôm nay {dmy(day)}, còn {f['left']} ngày)"]
    if not f["spent"] and not f["rate"]:
        return "\n".join(lines + ["Chưa có khoản nào để dự báo. Nhắn kiểu: cà phê 35k"])
    lines.append(f"Đã chi: <b>{vnd(f['spent'])}</b>")
    lines.append(f"Mỗi ngày đang tiêu khoảng <b>{approx(f['rate'])}</b> (không tính khoản từ {short(LARGE)})")
    if f["upcoming"]:
        lines.append("Có thể sắp tới (tháng trước có, tháng này chưa thấy): " + " · ".join(
            f"{note_of(e)} {short(e['tien'])} (ngày {e['ngay'][8:]})" for e in f["upcoming"][:4]))
    compare = ""
    if f["prev_total"]:
        change = (f["projected"] - f["prev_total"]) / f["prev_total"] * 100
        compare = f" · tháng trước {short(f['prev_total'])} ({'↑' if change >= 0 else '↓'}{abs(change):.0f}%)"
    lines.append(f"➡️ Cả tháng khoảng <b>{approx(f['projected'])}</b>{compare}")
    room = allowance(f)
    if room:
        per_day, today_left = room
        if per_day <= 0:
            lines.append("🚨 Đã tiêu hết ngân sách tổng tháng này")
        else:
            lines.append(f"💡 Để không vượt ngân sách: mỗi ngày tối đa <b>{approx(per_day)}</b>, hôm nay "
                         + (f"còn được tiêu <b>{approx(today_left)}</b>" if today_left >= 0
                            else f"đã quá <b>{approx(-today_left)}</b>"))
    else:
        lines.append("<i>Đặt ngân sách tổng để biết mỗi ngày được tiêu bao nhiêu: /ngansach tổng 15tr</i>")
    budgets = [budget_line(code, b) for code, b in f["budgets"].items()]
    if budgets:
        lines += ["", "<b>Ngân sách</b>"] + budgets
    if f["history"] < 7:
        lines.append(f"<i>{'Mới có ' + str(f['history']) + ' ngày' if f['history'] else 'Mới bắt đầu có'} dữ liệu, "
                     "dự báo còn thô, ghi đều vài tuần sẽ sát hơn</i>")
    return "\n".join(lines)


# ---- Báo bất thường -----------------------------------------------------------------

def unusual_lines(entries, day):
    """Khoản vừa ghi lớn bất thường so với mức thường của nhóm (trung vị 90 ngày, cần từ 5 khoản)."""
    big = [e for e in entries if e["nhom"] not in (ct.INCOME, ct.OTHER) and e["tien"] >= UNUSUAL_MIN]
    if not big:
        return []
    ids = {e["id"] for e in entries}
    history = [e for e in spending(ct.between(day - timedelta(days=90), day)) if e["id"] not in ids]
    lines = []
    for e in big:
        same = [x["tien"] for x in history if x["nhom"] == e["nhom"]]
        if len(same) < 5:
            continue
        typical = statistics.median(same)
        if e["tien"] >= UNUSUAL_RATIO * typical and e["tien"] - typical >= UNUSUAL_MIN:
            lines.append(f"👀 «{note_of(e)}» gấp {times(e['tien'] / typical)} lần mức thường của {ct.name(e['nhom'])}"
                         f" (thường khoảng {short(typical)})")
    return lines


def after_record(entries, day):
    """Dòng thêm dưới tin "Đã ghi": khoản lạ thường, hôm nay còn được tiêu bao nhiêu (nếu có ngân sách tổng)."""
    lines = unusual_lines(entries, day)
    if any(e["nhom"] != ct.INCOME for e in entries) and "tong" in kho.get(ct.K_BUDGET, {}):
        room = allowance(forecast(day))
        if room:
            per_day, today_left = room
            lines.append(f"💡 Hôm nay còn được tiêu {approx(today_left)} (mỗi ngày tối đa {short(per_day)})"
                         if today_left >= 0 else f"💡 Hôm nay đã tiêu quá {approx(-today_left)} so với mức mỗi ngày "
                         f"{short(max(per_day, 0))}")
    return lines


def alerts(day):
    """Việc tối: nhóm tiêu tăng vọt 7 ngày qua, nhóm đang trên đà vượt ngân sách. Mỗi chuyện chỉ báo
    một lần mỗi tuần (đánh dấu trong kho)."""
    lines = []
    items = spending(ct.between(day - timedelta(days=34), day))
    cut = (day - timedelta(days=7)).isoformat()
    if items and min(e["ngay"] for e in items) <= (day - timedelta(days=27)).isoformat():  # cần đủ 4 tuần trước
        week = [e for e in items if e["ngay"] > cut]
        before = [e for e in items if e["ngay"] <= cut]
        for code in ct.groups():
            if code == ct.OTHER:
                continue
            now_sum = total(e for e in week if e["nhom"] == code)
            usual = total(e for e in before if e["nhom"] == code) / 4
            if usual and now_sum >= SURGE_RATIO * usual and now_sum - usual >= SURGE_MIN \
                    and kho.put_new(f"chitieu:canhbao:tang:{code}", True, 7 * 86400):
                lines.append(f"📈 {ct.name(code)}: 7 ngày qua {vnd(now_sum)}, gấp {times(now_sum / usual)} lần mức "
                             f"thường ({short(usual)}/tuần). Nhiều nhất: "
                             + ", ".join(habit_text(k, c, a) for k, c, a in habits([e for e in week if e["nhom"] == code])[:3]))
    f = forecast(day)
    for code, b in f["budgets"].items():
        if b["spent"] < b["limit"] < b["projected"] and f["history"] >= 7 \
                and kho.put_new(f"chitieu:canhbao:ngansach:{code}:{day:%Y-%m}", True, 7 * 86400):
            label = "Tổng chi" if code == "tong" else ct.name(code)
            when = f" vào khoảng ngày {b['over_day']}" if b["over_day"] else " trước cuối tháng"
            lines.append(f"⏳ Theo đà này {label} sẽ vượt ngân sách {short(b['limit'])}{when} "
                         f"(dự báo cả tháng {short(b['projected'])}, đã chi {short(b['spent'])})")
    return lines


def habits(items):
    """Gộp khoản cùng nội dung (bỏ số, ngày): [(nội dung, số lần, tổng tiền)] nhiều tiền nhất trước."""
    groups = {}
    for e in items:
        key = ct.learn_key(e["ghichu"]) if e["ghichu"] else ct.bare(ct.name(e["nhom"]))
        count, amount = groups.get(key, (0, 0))
        groups[key] = (count + 1, amount + e["tien"])
    return sorted(((k, c, a) for k, (c, a) in groups.items()), key=lambda x: -x[2])


def habit_text(key, count, amount):
    return f"{html.escape(key)} {short(amount)}" + (f" ({count} lần)" if count > 1 else "")


# ---- Hỏi bằng câu thường ------------------------------------------------------------

QUESTION_WORDS = ["bao nhieu", "nhieu nhat", "it nhat", "lon nhat", "may lan", "so voi", "so sanh", "the nao",
                  "tai sao", "liet ke", "nhung khoan", "cac khoan", "het bao", "khoan nao", "nhom nao", "ngay nao",
                  "trung binh", "co phai", "vao dau", "tieu gi", "chi gi", "nhieu hon", "it hon"]
QUESTION_ENDS = ("khong", "ko", "chua", "nhi")  # "tháng này tiêu nhiều hơn tháng trước không"
KINDS = ("tong", "nhom", "lon_nhat", "liet_ke", "so_sanh", "theo_ngay")
HOI_HELP = ("🔎 Hỏi bằng câu thường, ví dụ:\n• tháng này cà phê hết bao nhiêu?\n• tuần này tiêu vào đâu nhiều nhất?\n"
            "• so tháng 10 với tháng 9\n• khoản lớn nhất tháng trước\n• liệt kê các lần đổ xăng tháng này\n"
            "• ngày nào tiêu nhiều nhất?\nGõ thẳng câu hỏi hoặc /hoi câu hỏi.")


def is_question(text):
    """Tin một dòng có dấu hỏi hoặc từ để hỏi ("bao nhiêu", "so với"...): là câu hỏi, không ghi khoản."""
    text = text.strip()
    if not text or "\n" in text:
        return False
    bare = ct.plain(text)
    return (text.endswith("?") or bare.rstrip(" .!").split()[-1] in QUESTION_ENDS
            or any(re.search(rf"(?<!\w){w}(?!\w)", bare) for w in QUESTION_WORDS))


def month_range(year, month, day):
    start = date(year, month, 1)
    return start, min(date(year, month, monthrange(year, month)[1]), day)


def month_of(number, day):
    """'tháng 10' nói vào tháng 11 là tháng 10 năm nay; nói vào tháng 2 là tháng 10 năm trước."""
    return month_range(day.year if number <= day.month else day.year - 1, number, day)


def periods_in(bare, day):
    """Các khoảng ngày nhắc trong câu (đã bỏ dấu), theo thứ tự xuất hiện: [(vị trí, từ, tới)]."""
    found = []
    monday = day - timedelta(days=day.weekday())
    simple = {"hom nay": (day, day), "hom qua": (day - timedelta(days=1),) * 2,
              "tuan nay": (monday, day), "tuan truoc": (monday - timedelta(days=7), monday - timedelta(days=1)),
              "thang nay": (day.replace(day=1), day), "nam nay": (date(day.year, 1, 1), day),
              "thang truoc": month_of(12 if day.month == 1 else day.month - 1, day)}
    for words, span in simple.items():
        for m in re.finditer(rf"(?<!\w){words}(?!\w)", bare):
            found.append((m.start(), *span))
    for m in re.finditer(r"(?<!\w)thang (\d{1,2})(?:/(\d{4}))?(?!\w)", bare):
        if 1 <= int(m[1]) <= 12:
            span = month_range(int(m[2]), int(m[1]), day) if m[2] else month_of(int(m[1]), day)
            found.append((m.start(), *span))
    for m in re.finditer(r"(?<!\w)(\d{1,3}) ngay (?:qua|gan day|vua qua|vua roi|truoc)(?!\w)", bare):
        found.append((m.start(), day - timedelta(days=int(m[1]) - 1), day))
    for m in re.finditer(r"(?<!\w)tu (\d{1,2})/(\d{1,2}) (?:den|toi) (\d{1,2})/(\d{1,2})(?!\w)", bare):
        try:
            a, b = date(day.year, int(m[2]), int(m[1])), date(day.year, int(m[4]), int(m[3]))
            found.append((m.start(), *(sorted((a, b)))))
        except ValueError:
            pass
    return [(pos, a, min(b, day)) for pos, a, b in sorted(found) if a <= day]


def previous_span(start, end):
    """Kỳ đem ra so: cả tháng thì tháng trước, còn lại là khoảng ngay trước có cùng số ngày."""
    if start.day == 1 and (end + timedelta(days=1)).day == 1:
        prev_end = start - timedelta(days=1)
        return prev_end.replace(day=1), prev_end
    if start.day == 1:  # tháng đang dở: so cùng kỳ tháng trước
        prev_end = start - timedelta(days=1)
        prev_start = prev_end.replace(day=1)
        return prev_start, min(prev_start + (end - start), prev_end)
    if (end - start).days < 7:  # trong tuần: cùng các thứ của tuần trước
        return start - timedelta(days=7), end - timedelta(days=7)
    length = end - start
    return start - length - timedelta(days=1), start - timedelta(days=1)


def rule_spec(question, day):
    """Hiểu câu hỏi không cần AI: khoảng ngày, nhóm, từ khóa, kiểu câu hỏi."""
    bare = " ".join(ct.plain(question).replace("?", " ").split())
    spans = periods_in(bare, day)
    start, end = (spans[0][1], spans[0][2]) if spans else (day.replace(day=1), day)
    has = lambda *words: any(re.search(rf"(?<!\w){w}(?!\w)", bare) for w in words)  # noqa: E731
    kind = ("so_sanh" if has("so voi", "so sanh", "hon hay", "nhieu hon", "it hon") else
            "lon_nhat" if has("lon nhat", "to nhat", "dat nhat", "khoan nao") else
            "theo_ngay" if has("ngay nao") else
            "nhom" if has("nhom nao", "vao dau", "tieu gi", "chi gi", "nhieu nhat") else
            "liet_ke" if has("liet ke", "nhung khoan", "cac khoan", "may lan", "nhung lan", "cac lan") else "tong")
    spec = {"kieu": kind, "tu": start, "den": end, "nhom": [], "tu_khoa": [],
            "thu": has("thu nhap", "thu vao", "luong", "kiem duoc", "thu duoc")}
    if kind == "so_sanh":
        if len(spans) >= 2:
            spec["tu2"], spec["den2"] = spans[1][1], spans[1][2]
        else:
            spec["tu2"], spec["den2"] = previous_span(start, end)
    for code, (label, _, _) in ct.groups().items():  # tên nhóm nhắc trong câu: "ăn uống", "đi chợ", "đi lại"
        parts = [" ".join(ct.plain(p).split()) for p in re.split(r"[,&]", ct.bare(label))]
        if code != ct.INCOME and any(len(p) >= 4 and re.search(rf"(?<!\w){re.escape(p)}(?!\w)", bare) for p in parts):
            spec["nhom"].append(code)
    if not spec["nhom"] and not spec["thu"]:  # món cụ thể: từ khóa dài nhất khớp trong câu
        text = ct.norm(question)
        typed_plain = text == ct.plain(text)
        hits = [(len(pattern.pattern), pattern) for exact, plain_p, score, code in ct.rules(kho.get(ct.K_LEARN, {}))
                for pattern in [plain_p if typed_plain else exact] if pattern and pattern.search(text) and score >= 2]
        if hits:
            word = max(hits, key=lambda x: x[0])[1].search(text)[0]
            spec["tu_khoa"] = [word]
    return spec


def ai_spec(question, day):
    """Nhờ AI hiểu câu hỏi thành bộ lọc JSON; số liệu vẫn do code tính."""
    groups = "\n".join(f"{code}: {ct.bare(label)}" for code, (label, _, _) in ct.groups().items()
                       if code != ct.INCOME)
    system = (
        f"Hôm nay là {WEEKDAYS[day.weekday()]} {day:%d/%m/%Y}. Chuyển câu hỏi về sổ chi tiêu cá nhân thành một "
        "dòng JSON, không giải thích:\n"
        '{"kieu": "tong" | "nhom" | "lon_nhat" | "liet_ke" | "so_sanh" | "theo_ngay", "tu": "YYYY-MM-DD", '
        '"den": "YYYY-MM-DD", "tu2": "YYYY-MM-DD", "den2": "YYYY-MM-DD", "nhom": [mã nhóm], '
        '"tu_khoa": [chữ trong ghi chú], "thu": true/false}\n'
        "- tong: tổng tiền; nhom: chia theo nhóm (tiêu vào đâu, nhóm nào nhiều nhất); lon_nhat: các khoản lớn "
        "nhất; liet_ke: liệt kê từng khoản (mấy lần, những khoản nào); so_sanh: so kỳ tu–den với kỳ tu2–den2 "
        "(thường là kỳ trước đó); theo_ngay: theo từng ngày (ngày nào tiêu nhiều).\n"
        "- Tuần tính từ thứ Hai. \"Tháng này\" là từ ngày 1 tới hôm nay, \"tháng trước\" là cả tháng trước. "
        "Không nói thời gian thì là tháng này. tu2/den2 chỉ dùng cho so_sanh.\n"
        "- nhom: chỉ điền khi hỏi cả một nhóm. Món cụ thể (cà phê, xăng, trà sữa, Grab...) thì để vào tu_khoa, "
        "kèm các cách viết hay gặp (vd [\"cà phê\", \"cafe\", \"coffee\"]).\n"
        "- thu: true nếu hỏi tiền thu vào (lương, thu nhập).\nCác nhóm (mã: tên):\n" + groups)
    text, _ = ct.ai_chat(system, question)
    raw = ct.first_json(text)
    if not isinstance(raw, dict):
        raise RuntimeError(f"AI trả lời không đúng dạng: {text[:100]!r}")
    return clean_spec(raw, day)


def clean_spec(raw, day):
    """Kiểm tra bộ lọc AI đưa: ngày hợp lệ, không quá hôm nay, nhóm có thật, từ khóa ngắn."""
    def when(key, default):
        try:
            return min(date.fromisoformat(str(raw.get(key))[:10]), day)
        except ValueError:
            return default
    start, end = when("tu", day.replace(day=1)), when("den", day)
    start, end = min(start, end), max(start, end)
    start = max(start, end - timedelta(days=400))
    spec = {"kieu": raw.get("kieu") if raw.get("kieu") in KINDS else "tong", "tu": start, "den": end,
            "nhom": [c for c in raw.get("nhom") or [] if isinstance(c, str) and c in ct.groups() and c != ct.INCOME],
            "tu_khoa": [str(w)[:30] for w in raw.get("tu_khoa") or [] if str(w).strip()][:5],
            "thu": raw.get("thu") is True}
    if spec["kieu"] == "so_sanh":
        prev = previous_span(start, end)
        a, b = when("tu2", prev[0]), when("den2", prev[1])
        spec["tu2"], spec["den2"] = min(a, b), max(a, b)
    return spec


def matches(e, spec):
    if spec["thu"] != (e["nhom"] == ct.INCOME):
        return False
    if spec["nhom"] and e["nhom"] not in spec["nhom"]:
        return False
    note = ct.plain(e["ghichu"] or "")
    return not spec["tu_khoa"] or any(re.search(rf"(?<!\w){re.escape(ct.plain(w))}", note) for w in spec["tu_khoa"])


def span_text(start, end):
    if start == end:
        return f"{WEEKDAYS[start.weekday()]} {start:%d/%m/%Y}"
    return f"{start:%d/%m}–{end:%d/%m/%Y}"


def by_group_lines(items, limit=8):
    sums = {}
    for e in items:
        sums[e["nhom"]] = sums.get(e["nhom"], 0) + e["tien"]
    whole, top = sum(sums.values()) or 1, max(sums.values(), default=1)
    return [f"{ct.name(code)}: <b>{vnd(amount)}</b> ({amount / whole * 100:.0f}%)\n" + "▇" * max(1, round(amount / top * 10))
            for code, amount in sorted(sums.items(), key=lambda x: -x[1])[:limit]]


def run_query(spec, day):
    start, end = spec["tu"], spec["den"]
    items = [e for e in ct.between(start, end) if matches(e, spec)]
    what = "Thu" if spec["thu"] else "Chi"
    filters = [ct.name(c) for c in spec["nhom"]] + (
        ["có chữ «" + "/".join(html.escape(w) for w in spec["tu_khoa"]) + "»"] if spec["tu_khoa"] else [])
    lines = [f"🔎 <b>{what} {span_text(start, end)}</b>" + (" · " + " · ".join(filters) if filters else "")]
    days = (end - start).days + 1
    summary = f"Tổng: <b>{vnd(total(items))}</b> · {len(items)} khoản" + (
        f" · TB {approx(total(items) / days)}/ngày" if days > 1 and items else "")
    kind = spec["kieu"]
    if kind == "so_sanh":
        start2, end2 = spec["tu2"], spec["den2"]
        other = [e for e in ct.between(start2, end2) if matches(e, spec)]
        a, b = total(items), total(other)
        change = f"{'↑' if a >= b else '↓'} {abs(a - b) / b * 100:.0f}% ({'+' if a >= b else '−'}{vnd(abs(a - b))})" \
            if b else "kỳ trước chưa có khoản nào"
        lines += [f"{span_text(start, end)}: <b>{vnd(a)}</b> ({len(items)} khoản)",
                  f"{span_text(start2, end2)}: <b>{vnd(b)}</b> ({len(other)} khoản)", f"➡️ {change}"]
        if not spec["nhom"] and not spec["tu_khoa"]:
            diff = {}
            for e in items:
                diff[e["nhom"]] = diff.get(e["nhom"], 0) + e["tien"]
            for e in other:
                diff[e["nhom"]] = diff.get(e["nhom"], 0) - e["tien"]
            moves = sorted((x for x in diff.items() if x[1]), key=lambda x: -abs(x[1]))[:5]
            if moves:
                lines += ["Chênh nhiều nhất:"] + [f"{ct.name(c)}: {'+' if d > 0 else '−'}{vnd(abs(d))}" for c, d in moves]
        return "\n".join(lines)
    if not items:
        return "\n".join(lines + ["Không có khoản nào khớp."])
    lines.append(summary)
    if kind == "nhom":
        lines += by_group_lines(items)
    elif kind == "lon_nhat":
        lines += [f"{i}. {e['ngay'][8:]}/{e['ngay'][5:7]} <b>{vnd(e['tien'])}</b> · {note_of(e)}"
                  for i, e in enumerate(sorted(items, key=lambda e: -e["tien"])[:5], 1)]
    elif kind == "liet_ke":
        newest = sorted(items, key=lambda e: (e["ngay"], e.get("gio", ""), e["id"]), reverse=True)
        lines += [f"{e['ngay'][8:]}/{e['ngay'][5:7]} <b>{vnd(e['tien'])}</b> · {ct.name(e['nhom']).split()[0]} "
                  f"{note_of(e)}" for e in newest[:15]]
        if len(newest) > 15:
            lines.append(f"… và {len(newest) - 15} khoản nữa")
    elif kind == "theo_ngay":
        per_day = {}
        for e in items:
            per_day[e["ngay"]] = per_day.get(e["ngay"], 0) + e["tien"]
        lines += [f"{WEEKDAYS[date.fromisoformat(d).weekday()]} {d[8:]}/{d[5:7]}: <b>{vnd(v)}</b>"
                  for d, v in sorted(per_day.items(), key=lambda x: -x[1])[:5]]
        lines += weekday_lines(items, start, end)
    return "\n".join(lines)


def weekday_lines(items, start, end):
    """Trung bình mỗi ngày cuối tuần và ngày thường trong kỳ."""
    counts = [0, 0]
    d = start
    while d <= end:
        counts[d.weekday() >= 5] += 1
        d += timedelta(days=1)
    sums = [0, 0]
    for e in items:
        sums[date.fromisoformat(e["ngay"]).weekday() >= 5] += e["tien"]
    if not all(counts):
        return []
    return [f"Ngày thường TB {approx(sums[0] / counts[0])}/ngày · cuối tuần TB {approx(sums[1] / counts[1])}/ngày"]


def hoi(question, day):
    """Trả lời câu hỏi về chi tiêu. AI (nếu bật) hiểu câu hỏi; AI lỗi thì hiểu theo cách đơn giản."""
    if not kho.ready():
        return ct.NEED_STORE
    question = question.strip()
    if not question:
        return HOI_HELP
    spec, note = None, ""
    if ct.ai_key():
        try:
            spec = ai_spec(question, day)
        except Exception as e:
            print(f"[lỗi] AI hiểu câu hỏi: {e!r}", file=sys.stderr)
            note = "\n<i>(AI đang bận, bot hiểu câu hỏi theo cách đơn giản; sai thì hỏi lại rõ hơn)</i>"
    spec = spec or rule_spec(question, day)
    return run_query(spec, day) + note


# ---- Biểu đồ ------------------------------------------------------------------------

def chart_png(chart, width=800, height=500):
    """Vẽ biểu đồ Chart.js thành ảnh PNG bằng QuickChart."""
    body = {"version": "4", "width": width, "height": height, "devicePixelRatio": 2, "backgroundColor": "white",
            "format": "png", "chart": chart}
    req = urllib.request.Request(CHART_URL, data=json.dumps(body, ensure_ascii=False).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = r.read()
    if not data.startswith(b"\x89PNG"):
        raise RuntimeError(f"QuickChart không trả ảnh: {data[:80]!r}")
    return data


def color(code):
    codes = list(ct.CATEGORIES) + list(ct.config().get("moi", []))
    return PALETTE[codes.index(code) % len(PALETTE)] if code in codes else PALETTE[-1]


def charts(start, end, label):
    """[ảnh tròn theo nhóm, ảnh cột theo ngày] của khoản chi trong kỳ."""
    items = spending(ct.between(start, end))
    sums = {}
    for e in items:
        sums[e["nhom"]] = sums.get(e["nhom"], 0) + e["tien"]
    order = sorted(sums.items(), key=lambda x: -x[1])
    whole = total(items)
    plugins = {"datalabels": {"display": False}}
    pie = {"type": "doughnut", "data": {
        "labels": [f"{ct.bare(ct.name(c))} {short(v)} ({v / whole * 100:.0f}%)" for c, v in order],
        "datasets": [{"data": [v for _, v in order], "backgroundColor": [color(c) for c, _ in order]}]},
        "options": {"plugins": {**plugins, "title": {"display": True, "text": f"Chi tiêu {label}: {vnd(whole)}",
                                                     "font": {"size": 22}},
                                "legend": {"position": "right", "labels": {"font": {"size": 16}}}}}}
    images = [chart_png(pie)]
    days = (end - start).days + 1
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
        images.append(chart_png(bars, 900, 450))
    return images, whole


def chart_reply(kind, day):
    if not kho.ready():
        return ct.NEED_STORE
    start, end, label, *_ = ct.period(kind, day)
    if not spending(ct.between(start, end)):
        return f"Chưa có khoản chi nào trong {label} để vẽ biểu đồ"
    try:
        images, whole = charts(start, end, label)
    except Exception as e:
        print(f"[lỗi] vẽ biểu đồ: {e!r}", file=sys.stderr)
        return "⚠️ Chưa vẽ được biểu đồ (dịch vụ vẽ không trả lời), thử lại sau hoặc xem /thang"
    return {"photos": images, "caption": f"📈 <b>Chi tiêu {label}</b>: {vnd(whole)}"}


# ---- Nhận xét -----------------------------------------------------------------------

def facts(kind, day):
    """(tên kỳ, các dòng số liệu HTML) để người dùng đọc và để AI viết nhận xét."""
    start, end, label, prev_start, prev_end, prev_label = ct.period(kind, day)
    items = ct.between(start, end)
    spend = spending(items)
    if not spend:
        return label, []
    whole, days = total(spend), (end - start).days + 1
    prev = spending(ct.between(prev_start, prev_end))
    lines = [f"Chi {label}: {vnd(whole)} · {len(spend)} khoản · TB {approx(whole / days)}/ngày"]
    if prev:
        change = (whole - total(prev)) / total(prev) * 100
        lines.append(f"So với {prev_label}: {'↑' if change >= 0 else '↓'}{abs(change):.0f}% ({vnd(total(prev))})")
    if start.day == 1 and kind != "thang":  # cả tháng: so trung bình 3 tháng trước
        olds, d = [], start
        for _ in range(3):
            d = (d - timedelta(days=1)).replace(day=1)
            month = spending(ct.between(d, month_range(d.year, d.month, day)[1]))
            if month:
                olds.append(total(month))
        if len(olds) >= 2:
            lines.append(f"Trung bình {len(olds)} tháng trước: {approx(sum(olds) / len(olds))}")
    now_g, prev_g = {}, {}
    for e in spend:
        now_g[e["nhom"]] = now_g.get(e["nhom"], 0) + e["tien"]
    for e in prev:
        prev_g[e["nhom"]] = prev_g.get(e["nhom"], 0) + e["tien"]
    lines.append("Theo nhóm: " + " · ".join(f"{ct.name(c)} {short(v)} ({v / whole * 100:.0f}%)"
                                             for c, v in sorted(now_g.items(), key=lambda x: -x[1])[:6]))
    if prev:
        moves = sorted(((c, now_g.get(c, 0) - prev_g.get(c, 0)) for c in set(now_g) | set(prev_g)),
                       key=lambda x: -abs(x[1]))
        up = [f"{ct.name(c)} +{short(d)}" for c, d in moves if d >= 100_000][:3]
        down = [f"{ct.name(c)} −{short(-d)}" for c, d in moves if d <= -100_000][:2]
        if up:
            lines.append("Tăng nhiều: " + " · ".join(up))
        if down:
            lines.append("Giảm: " + " · ".join(down))
    repeat = [h for h in habits([e for e in spend if e["ghichu"]]) if h[1] >= 3][:5]
    if repeat:
        lines.append("Lặp lại nhiều: " + " · ".join(f"{html.escape(k)} {c} lần {short(a)}" for k, c, a in repeat))
    biggest = sorted(spend, key=lambda e: -e["tien"])[:3]
    lines.append("Khoản lớn nhất: " + " · ".join(f"{note_of(e)} {short(e['tien'])}" for e in biggest))
    lines += weekday_lines(spend, start, end)
    first_day = date.fromisoformat(min(e["ngay"] for e in items))
    quiet = sum(1 for i in range((end - first_day).days + 1)
                if not any(e["ngay"] == (first_day + timedelta(days=i)).isoformat() for e in spend))
    if quiet:
        lines.append(f"{quiet} ngày không tiêu gì")
    income = total(e for e in items if e["nhom"] == ct.INCOME)
    if income:
        saved = income - whole
        lines.append(f"Thu {vnd(income)} → " + (f"để dành được {vnd(saved)} ({saved / income * 100:.0f}% thu nhập)"
                                                 if saved >= 0 else f"chi vượt thu {vnd(-saved)}"))
    return label, lines


def commentary(kind, day):
    """Số liệu của kỳ + nhận xét của AI (3 điểm đáng chú ý, 1 gợi ý tiết kiệm có con số)."""
    if not kho.ready():
        return ct.NEED_STORE
    label, lines = facts(kind, day)
    if not lines:
        return f"Chưa có khoản chi nào trong {label} để nhận xét"
    text = [f"📌 <b>Số liệu {label}</b>"] + [f"• {line}" for line in lines]
    if not ct.ai_key():
        return "\n".join(text + ["", "<i>Bật AI (biến AI_API_KEY) để có thêm nhận xét và gợi ý tiết kiệm</i>"])
    plain_facts = re.sub(r"<[^>]+>", "", html.unescape("\n".join(lines)))
    system = ("Bạn là trợ lý tài chính cá nhân, viết tiếng Việt có dấu, ngắn gọn, thân thiện, xưng \"bạn\". "
              "Chỉ dùng số liệu được cho, không bịa thêm số. Trả lời đúng 4 dòng, không markdown: 3 dòng đầu mỗi "
              "dòng bắt đầu bằng \"• \" là 3 điểm đáng chú ý nhất (mỗi dòng dưới 25 chữ); dòng cuối bắt đầu bằng "
              "\"💡 \" là 1 gợi ý tiết kiệm cụ thể có con số (vd bớt 2 ly trà sữa mỗi tuần thì để dành thêm "
              "khoảng 400k/tháng).")
    try:
        answer, _ = ct.ai_chat(system, f"Số liệu chi tiêu {label}:\n{plain_facts}")
        lines_ai = [line.strip() for line in answer.splitlines()]
        bullets = ["• " + re.sub(r"^([-*•]|\d+[.)])\s*", "", x) for x in lines_ai
                   if re.match(r"([-*•]|\d+[.)])\s*\S", x)][:3]  # model có khi đánh dấu "-" hay "1."
        tips = [x for x in lines_ai if x.startswith("💡")][:1]
        notes = bullets + tips
    except Exception as e:
        print(f"[lỗi] AI nhận xét: {e!r}", file=sys.stderr)
        notes = []
    if not notes:
        return "\n".join(text + ["", "<i>AI đang bận nên chưa có nhận xét, thử lại sau: /nhanxet</i>"])
    return "\n".join(text + ["", "🤖 <b>Nhận xét</b>"] + [html.escape(n) for n in notes])
