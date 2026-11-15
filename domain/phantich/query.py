"""Hiểu câu hỏi về chi tiêu không cần AI: nhận ra câu hỏi, các khoảng ngày nhắc trong câu, nhóm, từ khóa, kiểu câu hỏi;
kiểm tra bộ lọc do AI đưa. cfg là cấu hình nhóm của người dùng, learned là các cụm từ đã học."""
import re
from calendar import monthrange
from datetime import date, timedelta

from domain.chitieu import classify
from domain.chitieu.kinds import INCOME
from domain.common.text import norm, plain

QUESTION_WORDS = ["bao nhieu", "nhieu nhat", "it nhat", "lon nhat", "may lan", "so voi", "so sanh", "the nao",
                  "tai sao", "liet ke", "nhung khoan", "cac khoan", "het bao", "khoan nao", "nhom nao", "ngay nao",
                  "trung binh", "co phai", "vao dau", "tieu gi", "chi gi", "nhieu hon", "it hon", "bao gio", "khi nao",
                  "luc nao", "co nen"]
QUESTION_ENDS = ("khong", "ko", "chua", "nhi")  # "tháng này tiêu nhiều hơn tháng trước không"
KINDS = ("tong", "nhom", "lon_nhat", "liet_ke", "so_sanh", "theo_ngay")


def is_question(text):
    """Tin một dòng có dấu hỏi hoặc từ để hỏi ("bao nhiêu", "so với"...): là câu hỏi, không ghi khoản."""
    text = text.strip()
    if not text or "\n" in text:
        return False
    bare = plain(text)
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


def rule_spec(question, day, cfg, learned):
    """Hiểu câu hỏi không cần AI: khoảng ngày, nhóm, từ khóa, kiểu câu hỏi."""
    bare = " ".join(plain(question).replace("?", " ").split())
    spans = periods_in(bare, day)
    start, end = (spans[0][1], spans[0][2]) if spans else (day.replace(day=1), day)
    has = lambda *words: any(re.search(rf"(?<!\w){w}(?!\w)", bare) for w in words)  # noqa: E731
    kind = ("so_sanh" if has("so voi", "so sanh", "hon hay", "nhieu hon", "it hon") else
            "lon_nhat" if has("lon nhat", "to nhat", "dat nhat", "khoan nao") else
            "theo_ngay" if has("ngay nao") else
            "nhom" if has("nhom nao", "vao dau", "tieu gi", "chi gi", "nhieu nhat") else
            "liet_ke" if has("liet ke", "nhung khoan", "cac khoan", "may lan", "nhung lan", "cac lan", "bao nhieu lan", "bao nhieu khoan") else "tong")
    spec = {"kieu": kind, "tu": start, "den": end, "nhom": [], "tu_khoa": [],
            "thu": has("thu nhap", "thu vao", "luong", "kiem duoc", "thu duoc")}
    if kind == "so_sanh":
        if len(spans) >= 2:
            spec["tu2"], spec["den2"] = spans[1][1], spans[1][2]
        else:
            spec["tu2"], spec["den2"] = previous_span(start, end)
        spec["tu2"], spec["den2"] = same_period(spec)
    for code, (label, _, _) in classify.groups(cfg).items():  # tên nhóm nhắc trong câu: "ăn uống", "đi chợ", "đi lại"
        parts = [" ".join(plain(p).split()) for p in re.split(r"[,&]", classify.bare(label))]
        if code != INCOME and any(len(p) >= 4 and re.search(rf"(?<!\w){re.escape(p)}(?!\w)", bare) for p in parts):
            spec["nhom"].append(code)
    if not spec["nhom"] and not spec["thu"]:  # món cụ thể: từ khóa dài nhất khớp trong câu
        text = norm(question)
        typed_plain = text == plain(text)
        hits = [(len(pattern.pattern), pattern) for exact, plain_p, score, code in classify.rules(learned, cfg)
                for pattern in [plain_p if typed_plain else exact] if pattern and pattern.search(text) and score >= 2]
        if hits:
            word = max(hits, key=lambda x: x[0])[1].search(text)[0]
            spec["tu_khoa"] = [word]
    return spec


def clean_spec(raw, day, cfg):
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
            "nhom": [c for c in raw.get("nhom") or [] if isinstance(c, str) and c in classify.groups(cfg) and c != INCOME],
            "tu_khoa": [str(w)[:30] for w in raw.get("tu_khoa") or [] if str(w).strip()][:5],
            "thu": raw.get("thu") is True}
    if spec["kieu"] == "so_sanh":
        prev = previous_span(start, end)
        a, b = when("tu2", prev[0]), when("den2", prev[1])
        spec["tu2"], spec["den2"] = min(a, b), max(a, b)
        spec["tu2"], spec["den2"] = same_period(spec)
    return spec


def same_period(spec):
    """Tháng đang dở (1/11–20/11) mà đem so cả tháng trước thì so cùng kỳ (1/10–20/10) cho công bằng."""
    start, end, start2, end2 = spec["tu"], spec["den"], spec["tu2"], spec["den2"]
    month_end = (end.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    prev_end = (end2.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    if start.day == 1 and end < month_end and start2.day == 1 and end2 == prev_end and start2 < start:
        return start2, min(start2 + (end - start), end2)
    return start2, end2


def has_word(note, word):
    """Ghi chú có từ này (đầu từ)? Gõ có dấu thì khớp đúng dấu ("phở" không khớp "phớ" của tào phớ);
    gõ không dấu thì khớp không phân biệt dấu."""
    word, note = norm(word), norm(note)
    if word == plain(word) or note == plain(note):  # một bên không dấu: không biết dấu đúng, so không dấu
        text, word = plain(note), plain(word)
    else:
        text = note
    return bool(re.search(rf"(?<!\w){re.escape(word)}", text))


def matches(e, spec):
    if spec["thu"] != (e["nhom"] == INCOME):
        return False
    if spec["nhom"] and e["nhom"] not in spec["nhom"]:
        return False
    return not spec["tu_khoa"] or any(has_word(e["ghichu"] or "", w) for w in spec["tu_khoa"])
