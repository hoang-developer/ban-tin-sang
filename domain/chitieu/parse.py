"""Đọc một dòng tin nhắn chi tiêu: ngày, #nhóm, số tiền, ghi chú."""
import re
from datetime import date, timedelta

from domain.chitieu.categories import word_pattern
from domain.chitieu.classify import classify, find_group
from domain.chitieu.kinds import INCOME, OTHER
from domain.common.money import parse_amount
from domain.common.text import norm, plain

DATE = re.compile(r"(?<![\d/])(\d{1,2})/(\d{1,2})(?:/(\d{2}|\d{4}))?(?![\d/])")
# "tối qua", "đêm qua"... là buổi của hôm qua, kể cả nhắn lúc sau nửa đêm
DAY_WORDS = {"hôm nay": 0, "hôm qua": -1, "hôm kia": -2, "tối qua": -1, "đêm qua": -1, "sáng qua": -1,
             "chiều qua": -1, "trưa qua": -1}
FUTURE_DAYS = 31  # "dd/mm" sau hôm nay tới ngần này ngày: khoản sắp tới hay của năm trước? (xa hơn: năm trước)


def has_day_word(text):
    t = norm(text)
    return any(word_pattern(form).search(t) for words in DAY_WORDS for form in (words, plain(words)))


def vague_date(line, day):
    """Dòng có ngày "dd/mm" (không ghi năm) rơi sau hôm nay nhưng chưa quá FUTURE_DAYS ngày tới: chưa rõ là khoản sắp
    tới hay của năm trước. Trả (cùng ngày năm nay, cùng ngày năm trước, chữ ngày trong câu); None nếu đã rõ."""
    if has_day_word(line):
        return None  # chữ "hôm qua"... thắng ngày ghi bằng số (parse_date cũng làm vậy)
    m = DATE.search(norm(line))
    if not m or m[3]:
        return None
    try:
        soon = date(day.year, int(m[2]), int(m[1]))
        earlier = date(day.year - 1, int(m[2]), int(m[1]))
    except ValueError:
        return None
    return (soon, earlier, m[0]) if 0 < (soon - day).days <= FUTURE_DAYS else None


def first_vague_date(text, day):
    """vague_date của dòng đầu tiên chưa rõ ngày trong tin (mỗi dòng một khoản); None nếu mọi dòng đã rõ."""
    return next(filter(None, (vague_date(line, day) for line in text.splitlines())), None)


def resolve_vague(text, choice, day):
    """Tin với mọi ngày chưa rõ đã chọn: "toi" (ngày sắp tới), "trc" (năm trước) thêm năm vào "dd/mm"; "nay" đổi thành
    "hôm nay"."""
    out = []
    for line in text.splitlines():
        v = vague_date(line, day)
        if v:
            soon, earlier, raw = v
            fixed = {"toi": f"{raw}/{soon.year}", "trc": f"{raw}/{earlier.year}"}.get(choice, "hôm nay")
            line = DATE.sub(fixed, line, count=1)
        out.append(line)
    return "\n".join(out)


def parse_date(text, day):
    """Ngày ghi trong câu ('hôm qua', '02/11'): (ngày, câu đã bỏ phần ngày)."""
    t = norm(text)
    for words, offset in DAY_WORDS.items():
        for form in (words, plain(words)):
            if word_pattern(form).search(t):
                return day + timedelta(days=offset), word_pattern(form).sub(" ", t)
    m = DATE.search(t)
    if m:
        year = int(m[3]) + (2000 if m[3] and len(m[3]) == 2 else 0) if m[3] else day.year
        try:
            d = date(year, int(m[2]), int(m[1]))
            if not m[3] and d > day:
                d = d.replace(year=year - 1)  # 25/12 nhắn hồi tháng 1 là năm trước
            return d, t[:m.start()] + " " + t[m.end():]
        except ValueError:
            pass
    return day, t


TAG = re.compile(r"#\s*([^#\d\n]+)")  # "đóng họ 1tr #tiết kiệm": tự chọn nhóm khi ghi


def read_tag(line, cfg):
    """'#nhóm' trong dòng: (mã nhóm, tên nhóm chưa có, dòng đã bỏ phần #nhóm). Tên nhóm có thể nhiều chữ
    ("#tiết kiệm"); #nhóm đứng giữa câu thì lấy cụm chữ dài nhất trùng tên một nhóm, phần sau trả về ghi chú."""
    tag = TAG.search(line)
    words = tag[1].split() if tag else []
    if not words:
        return None, None, line
    before, after = line[:tag.start()], line[tag.end():]
    for n in range(len(words), 0, -1):
        code = find_group(" ".join(words[:n]), cfg)
        if code:
            return code, None, " ".join([before, *words[n:], after])
    if not after.strip() and classify(" ".join(words), None, cfg) != OTHER:  # "#cafe", "#xe": từ khóa của một nhóm
        return classify(" ".join(words), None, cfg), None, before
    n = len(words) if not after.strip() else 1  # không có nhóm nào: ở cuối dòng thì lấy hết, giữa câu lấy 1 chữ
    return None, " ".join(words[:n]).strip(" .,;:"), " ".join([before, *words[n:], after])


def parse_line(line, day, learned, cfg):
    """Một dòng tin nhắn -> khoản chi/thu (chưa có id), None nếu không có số tiền."""
    line = line.strip()
    income = line.startswith("+")
    chosen, missing, line = read_tag(line, cfg)
    when, text = parse_date(line.lstrip("+").strip(), day)
    found = parse_amount(text)
    if not found:
        return None
    amount, start, end = found
    note = " ".join((text[:start] + " " + text[end:]).split()).strip(" ,.:;-–")
    e = {"ngay": when.isoformat(), "tien": amount, "ghichu": note,
         "nhom": INCOME if income else chosen or classify(note, learned, cfg)}
    if missing:
        e["_tag"] = missing  # chưa có nhóm tên này: nhắc tạo nhóm
    if chosen and not income:
        e["_chon"] = True  # người dùng ghi #nhóm: không hỏi AI, nhớ cho lần sau
        if chosen == OTHER:
            e["dekhac"] = True
    return e
