"""Sổ nợ cho bot chi tiêu: từng khoản nợ còn bao nhiêu, mỗi tháng trả bao nhiêu, bao giờ xong, nhắc trả.

- Khoản nợ lưu chung với tài sản (/taisan, loại "no") nên tài sản ròng luôn đúng. /no thêm thông tin trả dần:
  tổng nợ ban đầu, mỗi tháng trả bao nhiêu, lãi (0 là nợ không lãi, như nợ người thân), ngày trả.
- Trả nợ: bấm ✅ Trả, nhắn "trả nợ chú Tư 5tr", hoặc gửi ảnh chuyển khoản: bot ghi khoản chi nhóm Trả nợ và
  trừ dư nợ. Xóa khoản chi đó (hoặc bấm ↩️ Không trừ) thì dư nợ được cộng lại.
- Khoản nợ mới khai báo: tính kỳ trả từ tháng sau (số dư khai báo đã gồm lần trả tháng này, nếu có).
- Tháng nào chưa trả: từ 9h ngày trả (không đặt thì 2 ngày sau ngày lương, không có ngày lương thì ngày 10)
  bot nhắc, 5 ngày sau nhắc thêm một lần.
- Trả xong một khoản: bot báo mỗi tháng dư ra bao nhiêu; /kehoach gợi ý chuyển phần đó vào quỹ dự phòng.
"""
import html
import math
import re
import unicodedata
from calendar import monthrange

import kho
import phantich as pt
import sochitieu as ct
import taisan as ts

USAGE = ("💳 <b>Sổ nợ</b>\n"
         "• Thêm: /no chú Tư 300tr đã trả 32tr, trả 5tr/tháng, không lãi\n"
         "• Trả góp: /no thẻ tín dụng trả góp 8,2tr, trả 4,39tr/tháng, ngày 5\n"
         "  (có lãi thì ghi: lãi 12%; ngày 5 là hạn trả hằng tháng)\n"
         "• Sửa: gõ lại cùng tên với thông tin mới, ví dụ /no chú Tư trả 6tr/tháng\n"
         "• Trả nợ: bấm ✅ Trả trong /no, nhắn «trả nợ chú Tư 5tr», hoặc gửi ảnh chuyển khoản: bot tự trừ dư nợ\n"
         "• Xóa khoản nợ: /no xoa")
GROUP_LABEL = "🏦 Trả nợ: trả nợ, trả góp, trả tiền vay"
# Chữ trong tên khoản nợ: xưng hô và chữ chung chung chỉ tính nửa điểm khi so với ghi chú khoản trả
KIN = {"bac", "chu", "co", "di", "cau", "mo", "thim", "anh", "chi", "em", "ong", "ba", "me", "bo", "duong", "chau",
       "vo", "chong", "ban", "sep"}
WEAK = KIN | {"the", "gop", "tin", "dung", "ngan", "hang"}
SKIP = {"tra", "no", "nop", "tien", "khoan", "cua", "cho", "thang", "ky", "lan", "vay", "va", "cac", "lai"}
AMT = r"\d+(?:[.,]\d+)*\s*(?:k|nghin|ngan|tr|trieu|cu|ty)?\d{0,3}(?:\s*(?:d|dong|vnd))?(?![\w])"
PATTERNS = [  # (trường, mẫu trên chữ đã bỏ dấu); làm lần lượt, phần đã khớp bị xóa trước mẫu sau
    ("nay", r"(?<!\w)(?:thang nay chua tra|chua tra thang nay)(?!\w)"),
    ("lai0", r"(?<!\w)(?:khong (?:co |tinh )?lai|0 lai|lai(?: suat)? 0(?:[.,]0+)?(?![.,]?\d)\s*%?)(?!\w)"),
    ("thang", r"(?<!\w)(?:moi|hang|1)\s*thang\s*(?:tra\s*)?(" + AMT + ")"),  # trước "lãi": "lãi 9% mỗi tháng trả 8tr"
    ("thang", r"(?<!\w)(?:tra\s*)?(" + AMT + r")\s*(?:/|moi|mot|1)\s*(?:thang|th)(?!\w)"),
    ("lai", r"(?<!\w)lai(?: suat)?\s*(\d+(?:[.,]\d+)?)\s*%\s*(?:/\s*|mot |moi |1 )?(nam|thang)?(?!\w)"),
    ("ngay", r"(?<!\w)(?:ngay|han)(?: tra)?\s*(\d{1,2})(?![\d/.,\w])"),
    ("ky", r"(?<!\w)(?:con\s*)?(\d{1,3})\s*(?:ky|thang)(?!\w)"),
    ("datra", r"(?<!\w)(?:da tra(?: duoc)?|tra roi)\s*(" + AMT + ")"),
    ("goc", r"(?<!\w)(?:tong(?: no| cong| vay)?|vay|ban dau|goc)\s*(?:la\s*)?(" + AMT + ")"),
    ("con", r"(?<!\w)con(?: lai| no)?\s*(?:la\s*)?(" + AMT + ")"),
]


def short(x):
    return pt.short(x) if x >= 1000 else "0đ"


def month_of(day):
    return day.strftime("%Y-%m")


def add_ym(ym, n):
    year, month = int(ym[:4]), int(ym[5:]) + n
    year, month = year + (month - 1) // 12, (month - 1) % 12 + 1
    return f"{year}-{month:02d}"


def ym_text(ym):
    return f"{ym[5:]}/{ym[:4]}"


def debts(data=None):
    return [it for it in (data or ts.load())["items"] if it["loai"] == "no"]


def active(data=None):
    return [d for d in debts(data) if d["tien"] > 0]


def by_id(data, debt_id):
    return next((d for d in debts(data) if str(d["id"]) == str(debt_id)), None)


def short_name(d, width=16):
    name = d["ten"]
    return name if len(name) <= width else name[:width - 1].rstrip() + "…"


def paid_in(d, ym):
    return sum(p["tien"] for p in d.get("tra", []) if p["ngay"][:7] == ym)


def due_amount(d):
    """Số phải trả trong một kỳ (kỳ cuối có thể ít hơn mức mỗi tháng); 0 nếu chưa đặt mức trả."""
    return min(d.get("thang") or 0, d["tien"])


def is_due(d, ym):
    return bool(d.get("thang")) and ym >= (d.get("tu") or ym)


def month_left(d, ym):
    """Kỳ tháng ym còn phải trả bao nhiêu (0 là đã trả đủ hoặc chưa tới kỳ)."""
    if not is_due(d, ym):
        return 0
    need = min(d["thang"], d["tien"] + paid_in(d, ym))
    left = need - paid_in(d, ym)
    return left if left > need * 0.02 else 0


def schedule(d, day):
    """(số kỳ còn lại, tháng trả xong 'YYYY-MM') của khoản có mức trả mỗi tháng; None nếu chưa đặt."""
    if not d.get("thang") or d["tien"] <= 0:
        return None
    n = math.ceil(d["tien"] / d["thang"] - 1e-9)
    ym = month_of(day)
    start = max(d.get("tu") or ym, ym)
    if start == ym and is_due(d, ym) and not month_left(d, ym):
        start = add_ym(ym, 1)  # tháng này đã trả đủ: kỳ tiếp theo là tháng sau
    return n, add_ym(start, n - 1)


def interest_text(d):
    rate = d.get("lai")
    return "không lãi" if rate == 0 else "chưa rõ lãi" if rate is None else f"lãi {ts.qty_text(rate)}%/năm"


def has_interest(d):
    return d.get("lai") != 0  # chưa rõ lãi: tính như có lãi cho chắc


def pay_day(d, day):
    """Hạn trả trong tháng: ngày đặt riêng, không có thì 2 ngày sau ngày lương, không có ngày lương thì ngày 10."""
    last = monthrange(day.year, day.month)[1]
    if d.get("ngay_tra"):
        return min(d["ngay_tra"], last)
    salary = kho.get(ts.K_SALARY) or {}
    return min(salary["ngay"] + 2, last) if salary.get("ngay") else 10


def debt_group(create=False):
    """(mã nhóm chi Trả nợ, câu báo nếu vừa tạo). Chưa có nhóm thì tạo khi create=True."""
    code = ct.find_group("trả nợ")
    if code or not create:
        return code, ""
    ct.nhom_them(GROUP_LABEL)
    ct.reset()
    code = ct.find_group("trả nợ")
    return code, ("🏦 Đã tạo nhóm chi «Trả nợ» để ghi các lần trả nợ" if code else "")


# ---- Khai báo -------------------------------------------------------------------------

def amount_of(text):
    found = ct.parse_amount(text)
    return found[0] if found else None


def parse_debt(text):
    """'chú Tư 300tr đã trả 32tr, trả 5tr/tháng, không lãi' -> {"ten", "con", "goc", "thang", "lai", "ngay_tra", "nay"}.
    Số tiền không kèm chữ nào là số còn nợ; có "đã trả X" thì số đó là tổng nợ ban đầu."""
    raw = " ".join(unicodedata.normalize("NFC", text).split())
    low = ct.plain(raw)  # cùng độ dài với raw: vị trí khớp trên low cắt được trên raw
    if len(low) != len(raw):
        return None
    found = {}

    def cut(m):
        nonlocal raw, low
        a, b = m.span()
        raw, low = raw[:a] + " " * (b - a) + raw[b:], low[:a] + " " * (b - a) + low[b:]

    for field, pattern in PATTERNS:
        if field in found:
            continue
        m = re.search(pattern, low)
        if not m:
            continue
        if field == "lai0":
            found["lai"] = 0.0
        elif field == "lai" and "lai" not in found:
            rate = float(m[1].replace(",", "."))
            found["lai"] = rate * 12 if m[2] == "thang" else rate
        elif field == "ngay":
            if not 1 <= int(m[1]) <= 31:
                continue
            found["ngay_tra"] = int(m[1])
        elif field == "ky":
            found["ky"] = int(m[1])
        elif field == "nay":
            found["nay"] = True
        elif field != "lai":
            value = amount_of(m[1])
            if not value or value < 10_000:  # "còn 2" không phải số tiền nợ
                continue
            found[field] = value
        cut(m)
    bare = ct.parse_amount(low)
    if bare:
        value, a, b = bare
        raw = raw[:a] + " " * (b - a) + raw[b:]
        if "datra" in found and "goc" not in found:
            found["goc"] = value
        elif "con" not in found:
            found["con"] = value
    name = re.sub(r"\s+([,.;:])", r"\1", " ".join(raw.split()))
    name = re.sub(r"(?:[,;]\s*){2,}", ", ", name).strip(" ,.;:-–")
    name = re.sub(r"(?i)^(?:khoản nợ|khoan no|nợ|no|còn|con)\s+", "", name).strip(" ,.;:-–")
    name = re.sub(r"[<>&\"]", "", name)[:40]
    con, goc, paid = found.get("con"), found.get("goc"), found.get("datra")
    if con is None and goc is not None:
        con = max(0, goc - (paid or 0))
    if goc is None and con is not None and paid:
        goc = con + paid
    monthly = found.get("thang")
    if not monthly and found.get("ky") and con:
        monthly = int(round(con / found["ky"], -3))
    return {"ten": name, "con": con, "goc": goc, "thang": monthly, "lai": found.get("lai"),
            "ngay_tra": found.get("ngay_tra"), "nay": found.get("nay", False)}


def plan_line(d, day):
    s = schedule(d, day)
    if not s:
        return f"Chưa đặt mỗi tháng trả bao nhiêu: /no {html.escape(d['ten'])} trả 5tr/tháng"
    n, last = s
    return f"{short(d['thang'])}/tháng · xong khoảng {ym_text(last)} ({n} tháng)"


def declare(text, day):
    info = parse_debt(text)
    if not info or not info["ten"]:
        return USAGE
    return declare_info(info, day)


def declare_info(info, day):
    """Thêm hoặc cập nhật một khoản nợ từ các trường đã đọc: {"ten", "con", "goc", "thang", "lai", "ngay_tra", "nay"}
    (trường không có để None)."""
    info = {"con": None, "goc": None, "thang": None, "lai": None, "ngay_tra": None, "nay": False, **info}
    data = ts.load()
    d = next((x for x in debts(data) if ts.same_name(x["ten"], info["ten"])), None)
    created = d is None
    if created:
        if not info["con"]:
            return (f"Chưa có khoản nợ «{html.escape(info['ten'])}». Thêm kèm số còn nợ, ví dụ:\n"
                    f"/no {html.escape(info['ten'])} 100tr, trả 5tr/tháng")
        d = {"id": ts.new_id(data), "loai": "no", "ten": info["ten"], "tien": info["con"], "ngay": day.isoformat()}
        data["items"].append(d)
    for field in ("goc", "thang", "lai", "ngay_tra"):
        if info[field] is not None:
            d[field] = info[field]
    if info["con"] is not None:
        d["tien"] = info["con"]
        d["ngay"] = day.isoformat()
        if d["tien"] > 0:
            d.pop("xong", None)
    if created or info["nay"] or "tu" not in d:
        d["tu"] = month_of(day) if info["nay"] else add_ym(month_of(day), 1)
    if d.get("goc") and d["goc"] < d["tien"]:
        d["goc"] = d["tien"]
    ts.save(data)
    _, group_note = debt_group(create=True)
    total = f" / {short(d['goc'])}" if d.get("goc") and d["goc"] != d["tien"] else ""
    lines = [f"✅ {'Đã thêm' if created else 'Đã cập nhật'} khoản nợ <b>{html.escape(d['ten'])}</b>: còn "
             f"{short(d['tien'])}{total} · {interest_text(d)}", "   " + plan_line(d, day)]
    if d.get("thang"):
        first = max(d["tu"], month_of(day))
        lines.append(f"   Kỳ trả {'đầu' if created else 'tới'}: tháng {ym_text(first)}"
                     + (f", hạn ngày {d['ngay_tra']}" if d.get("ngay_tra") else ""))
    if d.get("lai") is None:
        lines.append("<i>Có lãi không? Thêm «không lãi» hoặc «lãi 12%» để bot chấm sức khỏe tài chính đúng</i>")
    if group_note:
        lines.append(group_note)
    lines.append("Xem sổ nợ: /no")
    return "\n".join(lines)


# ---- Trả nợ ---------------------------------------------------------------------------

def apply_payment(d, e, day):
    """Trừ khoản trả e vào nợ d (chưa lưu); trả các dòng báo."""
    d["tien"] = max(0, d["tien"] - e["tien"])
    d.setdefault("tra", []).append({"ngay": e["ngay"], "tien": e["tien"], "ref": ct.ref(e)})
    d["tra"] = d["tra"][-60:]
    name = html.escape(d["ten"])
    if d["tien"] <= 0:
        d["xong"] = day.isoformat()
        lines = [f"🎉 Đã trả xong nợ {name}!"]
        if d.get("thang"):
            lines.append(f"🔁 Từ tháng sau mỗi tháng dư ra {short(d['thang'])}: nên chuyển vào quỹ dự phòng (/kehoach)")
        return lines
    s = schedule(d, day)
    return [f"💳 Đã trừ vào nợ {name}: còn {short(d['tien'])}"
            + (f" · còn {s[0]} tháng, xong khoảng {ym_text(s[1])}" if s else "")]


def tokens(text):
    return set(re.findall(r"[a-z0-9]+", ct.plain(text or "")))


def match(e, items, group):
    """Khoản chi e là lần trả khoản nợ nào: so tên khoản nợ với ghi chú; khoản ở nhóm Trả nợ/Khác thì so cả số
    tiền với mức trả mỗi tháng. Không chắc (không khớp hoặc khớp nhiều khoản ngang nhau) thì None."""
    note = tokens(e.get("ghichu"))
    loose = e["nhom"] in (group, ct.OTHER)  # chỉ khoản Trả nợ/Khác mới so số tiền (5tr tiền nhà không phải trả nợ)
    if not (e["nhom"] == group or "tra" in note or "gop" in note):
        return None
    scored = []
    for d in items:
        score = sum(1 if w in WEAK else 2 for w in (tokens(d["ten"]) - SKIP) & note)
        if loose and d.get("thang") and abs(e["tien"] - d["thang"]) <= d["thang"] * 0.02:
            score += 2
        if score >= 2:
            scored.append((score, d))
    scored.sort(key=lambda x: -x[0])
    if not scored or (len(scored) > 1 and scored[0][0] == scored[1][0]):
        return None
    return scored[0][1]


def after_record(entries, day):
    """Vừa ghi các khoản (tin nhắn hoặc ảnh): khoản nào là trả nợ thì trừ dư nợ. Trả (dòng thêm, hàng nút)."""
    entries = [e for e in entries if e["nhom"] != ct.INCOME and not e.get("no")]
    if not entries or not kho.ready():
        return [], []
    data = ts.load()
    items = active(data)
    if not items:
        return [], []
    group = debt_group()[0]
    lines, rows, changed, asked = [], [], False, False
    for e in entries:
        d = match(e, items, group)
        if d:
            if group and e["nhom"] != group and (e["nhom"] == ct.OTHER or e.get("ai")):
                e["nhom"] = group
                e.pop("ai", None)
                ct.learn(e["ghichu"], group)  # lần sau ghi giống vậy vào thẳng nhóm Trả nợ
            e["no"] = d["id"]
            ct.save(e)
            lines += apply_payment(d, e, day)
            rows.append([(f"↩️ Không trừ vào nợ {short_name(d)}", f"no:bo:{ct.ref(e)}")])
            changed = True
        elif group and e["nhom"] == group and not asked:
            asked = True  # khoản trả nợ chưa rõ của khoản nợ nào: hỏi (một khoản mỗi tin)
            lines.append(f"💳 Khoản trả nợ {short(e['tien'])} này trừ vào khoản nợ nào?")
            rows.append([(short_name(d, 14), f"no:gan:{ct.ref(e)}:{d['id']}") for d in items[:3]]
                        + [("Không trừ", f"no:kg:{ct.ref(e)}")])
    if changed:
        ts.save(data)
    return lines, rows


def undo(e):
    """Khoản trả nợ e bị xóa hoặc bỏ trừ: cộng lại dư nợ. Trả khoản nợ, None nếu không còn."""
    data = ts.load()
    d = by_id(data, e.get("no"))
    if not d:
        return None
    reference = ct.ref(e)
    d["tra"] = [p for p in d.get("tra", []) if p.get("ref") != reference]
    d["tien"] += e["tien"]
    d.pop("xong", None)
    ts.save(data)
    return d


def pay(debt_id, amount, now):
    """Bấm ✅ Trả: ghi khoản chi nhóm Trả nợ và trừ dư nợ. Trả (khoản đã ghi hoặc None, các dòng báo)."""
    data = ts.load()
    d = by_id(data, debt_id)
    if not d or d["tien"] <= 0:
        return None, ["Khoản nợ này đã trả xong hoặc đã xóa"]
    group, note = debt_group(create=True)
    day = now.date()
    e = {"id": kho.command("INCR", ct.K_COUNTER), "ngay": day.isoformat(), "gio": now.strftime("%H:%M"),
         "tien": int(amount), "ghichu": f"trả nợ {d['ten']}", "nhom": group or ct.OTHER, "no": d["id"]}
    if not group:
        e["dekhac"] = True
    ct.save(e)
    lines = apply_payment(d, e, day)
    ts.save(data)
    return e, lines + ([note] if note else [])


# ---- Xem, nhắc ------------------------------------------------------------------------

def bar(ratio, width=10):
    full = max(0, min(width, round(ratio * width)))
    return "▓" * full + "░" * (width - full)


def month_status(d, day):
    ym = month_of(day)
    if not d.get("thang"):
        return ""
    if ym < d.get("tu", ym):
        return f"⏳ Kỳ trả đầu: tháng {ym_text(d['tu'])}"
    paid, left = paid_in(d, ym), month_left(d, ym)
    if not left:
        return f"✅ Tháng {day.month} đã trả {short(paid)}"
    due = f", hạn ngày {d['ngay_tra']}" if d.get("ngay_tra") else ""
    return (f"🟡 Tháng {day.month} đã trả {short(paid)}, còn {short(left)}{due}" if paid
            else f"⬜ Tháng {day.month} chưa trả {short(left)}{due}")


def due_now(day, data=None):
    """[(khoản nợ, số còn phải trả tháng này)] của các khoản tới kỳ mà chưa trả đủ."""
    ym = month_of(day)
    return [(d, month_left(d, ym)) for d in active(data) if month_left(d, ym)]


def monthly_total(data=None):
    return sum(due_amount(d) for d in active(data))


def freed(data=None, ym=None):
    """(tổng mức trả mỗi tháng của các khoản đã trả xong, tên các khoản) — tiền mỗi tháng được giải phóng.
    ym: chỉ tính khoản xong từ trước tháng đó (tháng trả kỳ cuối thì tiền chưa dư ra)."""
    done = [d for d in debts(data) if d["tien"] <= 0 and d.get("thang") and (not ym or (d.get("xong") or "")[:7] < ym)]
    return sum(d["thang"] for d in done), [d["ten"] for d in done]


def view(day):
    data = ts.load()
    items, done = active(data), [d for d in debts(data) if d["tien"] <= 0]
    back = [("🗂 Sửa, xóa", "no:ds"), ("➕ Thêm khoản nợ", "y:them:no_moi"), ct.BACK]
    if not items and not done:
        return ("💳 Chưa có khoản nợ nào. Bấm ➕ để thêm, hoặc nhắn câu thường, ví dụ: «vay anh Nam 10tr, mỗi tháng trả "
                "2tr, không lãi».", [[("➕ Thêm khoản nợ", "y:them:no_moi"), ct.BACK]])
    total, monthly = sum(d["tien"] for d in items), monthly_total(data)
    lines = [f"💳 <b>Sổ nợ: còn {short(total)}</b>" + (f" · trả {short(monthly)}/tháng" if monthly else "")]
    for i, d in enumerate(items, 1):
        head = f"\n{i}. <b>{html.escape(d['ten'])}</b>: còn {short(d['tien'])}"
        if d.get("goc") and d["goc"] > d["tien"]:
            head += f" / {short(d['goc'])}"
        lines.append(head + f" · {interest_text(d)}")
        if d.get("goc") and d["goc"] > d["tien"]:
            ratio = 1 - d["tien"] / d["goc"]
            lines.append(f"   {bar(ratio)} đã trả {ratio * 100:.0f}%")
        lines.append("   " + plan_line(d, day))
        status = month_status(d, day)
        if status:
            lines.append("   " + status)
    if done:
        lines.append("\n✅ Đã trả xong: " + ", ".join(html.escape(d["ten"]) for d in done))
    upcoming = sorted(((s[1], d) for d in items for s in [schedule(d, day)] if s), key=lambda x: x[0])
    if upcoming and len(items) > 1:
        last, d = upcoming[0]
        lines.append(f"\n💡 {ym_text(last)} trả xong {html.escape(d['ten'])}: từ tháng sau mỗi tháng dư ra "
                     f"{short(d['thang'])}, dồn vào quỹ dự phòng (quỹ đủ rồi thì để đầu tư)")
    rows = [[(f"✅ Trả {short_name(d)} {short(left)}", f"no:tra:{d['id']}:{int(left)}")] for d, left in due_now(day, data)]
    return "\n".join(lines), rows + [back]


def edit_list():
    items = debts()
    if not items:
        return "Chưa có khoản nợ nào", [[("↩️ Sổ nợ", "no:xem")]]
    lines = ["🗂 <b>Bấm ❌ để xóa khoản nợ</b> (sửa: gõ lại /no cùng tên với thông tin mới)"]
    lines += [f"{i}. {html.escape(d['ten'])}: còn {short(d['tien'])}" for i, d in enumerate(items, 1)]
    buttons = [(f"❌ {i}", f"no:x:{d['id']}") for i, d in enumerate(items, 1)]
    return "\n".join(lines), [buttons[i:i + 5] for i in range(0, len(buttons), 5)] + [[("↩️ Sổ nợ", "no:xem")]]


def home_line(day):
    """Một dòng cho màn hình tổng quan; None nếu không có nợ."""
    data = ts.load()
    items = active(data)
    if not items:
        return None
    ym = month_of(day)
    need = sum(min(d["thang"], d["tien"] + paid_in(d, ym)) for d in items if is_due(d, ym))
    paid = sum(min(paid_in(d, ym), d["thang"]) for d in items if is_due(d, ym))
    line = f"💳 Nợ còn <b>{short(sum(d['tien'] for d in items))}</b>"
    if need:
        line += f" · tháng {day.month} đã trả {short(paid)}/{short(need)}"
    elif any(d.get("thang") for d in items):
        line += " · kỳ trả đầu tháng sau"
    return line


def reminders(day):
    """Tin nhắc trả nợ (tin, nút) cho các khoản tới hạn mà tháng này chưa trả đủ; mỗi khoản nhắc tối đa 2 lần
    mỗi tháng (ngày hạn và 5 ngày sau). None nếu không có gì cần nhắc."""
    ym = month_of(day)
    due = []
    for d, left in due_now(day):
        start = pay_day(d, day)
        if day.day < start:
            continue
        stage = 1 if day.day < start + 5 else 2
        if kho.put_new(f"chitieu:nhac:no:{d['id']}:{ym}:{stage}", True, 40 * 86400):
            due.append((d, left))
    if not due:
        return None
    lines = [f"💳 <b>Nhắc trả nợ tháng {day.month}</b>"]
    lines += [f"• {html.escape(d['ten'])}: {short(left)}" + (f" (hạn ngày {d['ngay_tra']})" if d.get("ngay_tra") else "")
              for d, left in due]
    lines.append("Trả rồi thì bấm nút để ghi khoản chi và trừ dư nợ")
    rows = [[(f"✅ Đã trả {short_name(d)} {short(left)}", f"no:tra:{d['id']}:{int(left)}")] for d, left in due]
    return "\n".join(lines), rows + [[("💳 Sổ nợ", "no:xem")]]


def health_check(day, v, income):
    """(điểm 0–20, dấu, dòng) cho khám sức khỏe tài chính: chấm theo tiền trả nợ mỗi tháng so với thu nhập; chưa
    biết thu nhập thì theo nợ CÓ LÃI so với tài sản. Nợ không lãi (người thân) ghi riêng, không bị coi như nợ vay."""
    data = ts.load()
    items = active(data)
    if not items:
        return 20, "✅", "Nợ: không có"
    bearing = [d for d in items if has_interest(d)]
    zero = [d for d in items if not has_interest(d)]
    monthly = monthly_total(data)
    parts = []
    if monthly and income:
        share = monthly / income * 100
        score = 20 if share <= 20 else 16 if share <= 30 else 10 if share <= 40 else 5 if share <= 50 else 0
        mark = "✅" if share <= 30 else "⚠️" if share <= 50 else "🚨"
        parts.append(f"trả {short(monthly)}/tháng, bằng {share:.0f}% thu nhập (nên dưới 30%)")
    else:
        owed = sum(d["tien"] for d in bearing)
        ratio = owed / v["assets"] * 100 if v["assets"] else (100 if owed else 0)
        score = 20 if not owed else 16 if ratio < 30 else 8 if ratio < 50 else 0
        mark = "✅" if ratio < 30 else "⚠️" if ratio < 50 else "🚨"
        if owed:
            parts.append(f"nợ có lãi bằng {ratio:.0f}% tài sản (nên dưới 30%)")
    if bearing:
        ends = [schedule(d, day) for d in bearing]
        last = max(s[1] for s in ends) if all(ends) else None
        parts.append(f"nợ có lãi {short(sum(d['tien'] for d in bearing))}" + (f", xong khoảng {ym_text(last)}" if last else ""))
    if zero:
        parts.append(f"nợ không lãi {short(sum(d['tien'] for d in zero))}")
    late = [d for d, _ in due_now(day, data) if day.day >= pay_day(d, day) + 5]
    if late:
        score = max(0, score - 5)
        mark = "⚠️" if mark == "✅" else mark
        parts.append("tháng này chưa trả: " + ", ".join(html.escape(d["ten"]) for d in late))
    return score, mark, "Nợ: " + " · ".join(parts) + " · /no"


# ---- Lệnh, nút ------------------------------------------------------------------------

def no_cmd(args):
    if not kho.ready():
        return ct.NEED_STORE
    day = ct.today()
    word = ct.plain(args[0]) if args else ""
    if not args:
        return view(day)
    if word in ("xoa", "sua", "ds"):
        return edit_list()
    if word in ("huongdan", "help", "?"):
        return USAGE
    if word == "tra" and len(args) > 1:  # /no tra chú Tư 5tr
        rest = " ".join(args[1:])
        found = ct.parse_amount(rest)
        d = next((x for x in active() if tokens(x["ten"]) - SKIP and (tokens(x["ten"]) - SKIP) <= tokens(rest)), None)
        if not found or not d:
            return "Trả nợ: /no tra <tên khoản nợ> <số tiền>, ví dụ /no tra chú Tư 5tr"
        _, lines = pay(d["id"], found[0], ts.now_vn())
        return "\n".join(lines)
    return declare(" ".join(args), day)


def on_button(arg, message, now):
    """Nút "no:...": (thông báo nhỏ, việc tiếp theo)."""
    kind, _, rest = arg.partition(":")
    day = now.date()
    if kind == "xem":
        return None, ("edit", lambda: view(day))
    if kind == "hd":
        return None, ("send", lambda: USAGE)
    if kind == "ds":
        return None, ("edit", edit_list)
    if kind == "x":
        data = ts.load()
        kept = [it for it in data["items"] if not (it["loai"] == "no" and str(it["id"]) == rest)]
        if len(kept) != len(data["items"]):
            data["items"] = kept
            ts.save(data)
            return "Đã xóa khoản nợ", ("edit", edit_list)
        return "Khoản này đã xóa rồi", ("edit", edit_list)
    if kind == "tra":
        debt_id, _, amount = rest.partition(":")
        if not amount.isdigit():
            return None, None
        e, lines = pay(debt_id, int(amount), now)
        toast = re.sub(r"<[^>]+>", "", lines[0])[:190]
        if not e:
            return toast, None
        title = message.get("text") or ""
        if title.startswith("📋"):
            import kehoach
            return toast, ("edit", lambda: kehoach.plan(day))
        if title.startswith("🏠"):
            import menu
            return toast, ("edit", lambda: menu.home(day))
        if title.startswith("💳"):
            return toast, ("edit", lambda: view(day))
        rows = [row for row in ct.keyboard_rows(message) if not any(d == f"no:{arg}" for _, d in row)]
        return toast, ("buttons", lambda: rows)
    reference = rest.rpartition(":")[0] if kind == "gan" else rest
    e = ct.find(reference) if kind in ("gan", "kg", "bo") else None
    if kind in ("gan", "kg", "bo") and e is None:
        return "Khoản chi này đã xóa rồi", None
    keep = [row for row in ct.keyboard_rows(message)
            if not any(d.startswith((f"no:gan:{reference}:", f"no:kg:{reference}", f"no:bo:{reference}")) for _, d in row)]
    if kind == "gan":
        data = ts.load()
        d = by_id(data, rest.rpartition(":")[2])
        if not d or e.get("no"):
            return "Khoản này đã trừ nợ rồi hoặc khoản nợ không còn", ("buttons", lambda: keep)
        e["no"] = d["id"]
        ct.save(e)
        lines = apply_payment(d, e, day)
        ts.save(data)
        return re.sub(r"<[^>]+>", "", lines[0])[:190], ("buttons", lambda: keep)
    if kind == "kg":
        return "Không trừ vào khoản nợ nào", ("buttons", lambda: keep)
    if kind == "bo":
        if not e.get("no"):
            return "Khoản này không trừ nợ", ("buttons", lambda: keep)
        d = undo(e)
        e.pop("no", None)
        ct.save(e)
        return (f"Đã bỏ trừ nợ, {d['ten']} còn {short(d['tien'])}" if d else "Đã bỏ trừ nợ")[:190], ("buttons", lambda: keep)
    return None, None
