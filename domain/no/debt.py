"""Sổ nợ: luật tính một khoản nợ, đọc câu khai báo nợ, khớp khoản trả với khoản nợ, chấm sức khỏe nợ. Luật thuần.

Khoản nợ lưu chung với tài sản (loại "no") nên tài sản ròng luôn đúng; một khoản nợ là một dict:
{"id", "ten", "tien" (còn nợ), "goc", "thang" (trả mỗi tháng), "lai" (%/năm; 0 là nợ không lãi; None là chưa rõ),
 "ngay_tra", "tu" (kỳ trả đầu 'YYYY-MM'), "tra": [{"ngay", "tien", "ref"}], "xong"}.

- Khoản nợ mới khai báo: tính kỳ trả từ tháng sau (số dư khai báo đã gồm lần trả tháng này, nếu có).
- Tháng nào chưa trả: từ ngày trả (không đặt thì 2 ngày sau ngày lương, không có ngày lương thì ngày 10) bot nhắc,
  5 ngày sau nhắc thêm một lần.
"""
import math
import re
import unicodedata
from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date

from domain.common.money import parse_amount
from domain.common.text import plain

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


# ---- Thời gian ---------------------------------------------------------------------------

def month_of(day):
    return day.strftime("%Y-%m")


def add_ym(ym, n):
    year, month = int(ym[:4]), int(ym[5:]) + n
    year, month = year + (month - 1) // 12, (month - 1) % 12 + 1
    return f"{year}-{month:02d}"


def ym_text(ym):
    return f"{ym[5:]}/{ym[:4]}"


# ---- Một khoản nợ ------------------------------------------------------------------------

def debts_of(items):
    """Các khoản nợ trong danh sách mục tài sản."""
    return [it for it in items if it["loai"] == "no"]


def active_of(items):
    """Các khoản nợ còn dư."""
    return [d for d in debts_of(items) if d["tien"] > 0]


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


def monthly_rate(d):
    """Lãi mỗi tháng (số thập phân) của khoản nợ có lãi: lãi %/năm / 12 / 100; 0 nếu không lãi hoặc chưa rõ lãi."""
    return (d.get("lai") or 0) / 1200


def interest_only(d):
    """Khoản nợ có lãi mà mức trả mỗi tháng không đủ trả lãi một tháng: nợ sẽ không bao giờ hết."""
    return bool(d.get("thang")) and d["tien"] > 0 and monthly_rate(d) > 0 and d["thang"] <= monthly_rate(d) * d["tien"] + 1e-9


def accrual_start(d):
    """Ngày bắt đầu dồn lãi: lần dồn gần nhất (ngay_lai); khoản cũ chưa có thì ngày trả gần nhất, không thì ngày khai báo
    dư nợ; None nếu không có ngày nào."""
    raw = d.get("ngay_lai") or (d["tra"][-1]["ngay"] if d.get("tra") else None) or d.get("ngay")
    return date.fromisoformat(raw) if raw else None


def accrued_interest(d, day):
    """Lãi dồn của khoản nợ có lãi từ lần cập nhật dư nợ gần nhất tới `day`, theo dư nợ giảm dần: dư nợ × lãi%/năm × số ngày
    / 365. 0 nếu không lãi, chưa rõ lãi hay hết nợ."""
    start = accrual_start(d)
    if not d.get("lai") or d["tien"] <= 0 or not start:
        return 0.0
    return d["tien"] * d["lai"] / 100 * max((day - start).days, 0) / 365


def schedule(d, day):
    """(số kỳ còn lại, tháng trả xong 'YYYY-MM') của khoản có mức trả mỗi tháng; None nếu chưa đặt hoặc nợ có lãi mà mức trả
    không đủ trả lãi. Nợ có lãi tính theo dư nợ giảm dần: n = -ln(1 - r·B/P) / ln(1 + r) (r lãi tháng, B dư nợ, P mức trả)."""
    if not d.get("thang") or d["tien"] <= 0 or interest_only(d):
        return None
    r = monthly_rate(d)
    n = (math.ceil(-math.log(1 - r * d["tien"] / d["thang"]) / math.log(1 + r) - 1e-9) if r > 0
         else math.ceil(d["tien"] / d["thang"] - 1e-9))
    ym = month_of(day)
    start = max(d.get("tu") or ym, ym)
    if start == ym and is_due(d, ym) and not month_left(d, ym):
        start = add_ym(ym, 1)  # tháng này đã trả đủ: kỳ tiếp theo là tháng sau
    return n, add_ym(start, n - 1)


def has_interest(d):
    return d.get("lai") != 0  # chưa rõ lãi: tính như có lãi cho chắc


def pay_day(d, day, salary_day=None):
    """Hạn trả trong tháng: ngày đặt riêng, không có thì 2 ngày sau ngày lương, không có ngày lương thì ngày 10."""
    last = monthrange(day.year, day.month)[1]
    if d.get("ngay_tra"):
        return min(d["ngay_tra"], last)
    return min(salary_day + 2, last) if salary_day else 10


def due_now(items, day):
    """[(khoản nợ, số còn phải trả tháng này)] của các khoản còn dư tới kỳ mà chưa trả đủ."""
    ym = month_of(day)
    return [(d, month_left(d, ym)) for d in active_of(items) if month_left(d, ym)]


def monthly_total(items):
    """Tổng mức phải trả mỗi tháng của các khoản còn dư."""
    return sum(due_amount(d) for d in active_of(items))


def freed(items, ym=None):
    """(tổng mức trả mỗi tháng của các khoản đã trả xong, tên các khoản) — tiền mỗi tháng được giải phóng.
    ym: chỉ tính khoản xong từ trước tháng đó (tháng trả kỳ cuối thì tiền chưa dư ra)."""
    done = [d for d in debts_of(items) if d["tien"] <= 0 and d.get("thang") and (not ym or (d.get("xong") or "")[:7] < ym)]
    return sum(d["thang"] for d in done), [d["ten"] for d in done]


def month_progress(items, day):
    """(đã trả, cần trả) tháng này của các khoản tới kỳ."""
    ym = month_of(day)
    due = [d for d in active_of(items) if is_due(d, ym)]
    need = sum(min(d["thang"], d["tien"] + paid_in(d, ym)) for d in due)
    paid = sum(min(paid_in(d, ym), d["thang"]) for d in due)
    return paid, need


# ---- Đọc câu khai báo --------------------------------------------------------------------

def amount_of(text):
    found = parse_amount(text)
    return found[0] if found else None


def parse_debt(text):
    """'chú Tư 300tr đã trả 32tr, trả 5tr/tháng, không lãi' -> {"ten", "con", "goc", "thang", "lai", "ngay_tra", "nay"}.
    Số tiền không kèm chữ nào là số còn nợ; có "đã trả X" thì số đó là tổng nợ ban đầu."""
    raw = " ".join(unicodedata.normalize("NFC", text).split())
    low = plain(raw)  # cùng độ dài với raw: vị trí khớp trên low cắt được trên raw
    if len(low) != len(raw):
        return None
    found = {}

    def cut(m):
        nonlocal raw, low
        a, b = m.span()
        raw, low = raw[:a] + " " * (b - a) + raw[b:], low[:a] + " " * (b - a) + low[b:]

    for field_name, pattern in PATTERNS:
        if field_name in found:
            continue
        m = re.search(pattern, low)
        if not m:
            continue
        if field_name == "lai0":
            found["lai"] = 0.0
        elif field_name == "lai" and "lai" not in found:
            rate = float(m[1].replace(",", "."))
            found["lai"] = rate * 12 if m[2] == "thang" else rate
        elif field_name == "ngay":
            if not 1 <= int(m[1]) <= 31:
                continue
            found["ngay_tra"] = int(m[1])
        elif field_name == "ky":
            found["ky"] = int(m[1])
        elif field_name == "nay":
            found["nay"] = True
        elif field_name != "lai":
            value = amount_of(m[1])
            if not value or value < 10_000:  # "còn 2" không phải số tiền nợ
                continue
            found[field_name] = value
        cut(m)
    bare = parse_amount(low)
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


def apply_info(d, info, day, created):
    """Áp các trường đã đọc (trừ tên) vào khoản nợ d (chưa lưu): số còn nợ, tổng nợ, mức trả, lãi, hạn, kỳ trả đầu."""
    was_bearing = bool(d.get("lai"))
    for field_name in ("goc", "thang", "lai", "ngay_tra"):
        if info[field_name] is not None:
            d[field_name] = info[field_name]
    if d.get("lai") and (info["con"] is not None or not was_bearing):
        d["ngay_lai"] = day.isoformat()  # mốc dồn lãi: số còn nợ mới khai báo, hoặc vừa chuyển sang nợ có lãi
    if info["con"] is not None:
        d["tien"] = info["con"]
        d["ngay"] = day.isoformat()
        if d["tien"] > 0:
            d.pop("xong", None)
    if created or info["nay"] or "tu" not in d:
        d["tu"] = month_of(day) if info["nay"] else add_ym(month_of(day), 1)
    if d.get("goc") and d["goc"] < d["tien"]:
        d["goc"] = d["tien"]


# ---- Trả nợ ------------------------------------------------------------------------------

@dataclass
class Payment:
    """Kết quả trừ một khoản trả vào dư nợ."""
    name: str  # tên khoản nợ (chưa escape HTML)
    finished: bool
    left: int
    monthly: int | None  # mức trả mỗi tháng của khoản nợ (nếu có)
    schedule: tuple | None  # (số kỳ còn lại, tháng xong) nếu còn nợ và có mức trả
    interest: int = 0  # nợ có lãi: phần lãi trong khoản trả lần này (lãi dồn tới ngày trả, trả trước)
    principal: int | None = None  # nợ có lãi: phần trả gốc (có thể 0 nếu không đủ trả lãi)
    extra: int = 0  # số trả dư hơn gốc + lãi còn nợ (người dùng nên kiểm tra lại số tiền)
    interest_only: bool = False  # mức trả mỗi tháng không đủ trả lãi


def apply_payment(d, e, reference, day):
    """Trừ khoản trả e vào nợ d (chưa lưu). Nợ không lãi: trừ thẳng. Nợ có lãi: lãi dồn tới ngày trả (dư nợ × lãi × số ngày /
    365) được trả trước, phần còn lại mới trừ gốc; trả không đủ lãi thì lãi chưa trả cộng vào dư nợ."""
    amount = e["tien"]
    before = d["tien"]
    interest = accrued_interest(d, date.fromisoformat(e["ngay"]))
    owed = before + interest
    d["tien"] = max(0, round(owed - amount))
    rec = {"ngay": e["ngay"], "tien": amount, "ref": reference}
    extra = 0
    paid_interest = principal = None
    if d.get("lai"):  # nợ có lãi: nhớ phần lãi/gốc và mốc dồn lãi cũ để hoàn tác được
        paid_interest = round(min(amount, interest))
        principal = max(0, round(min(amount, owed)) - paid_interest)
        extra = max(0, round(amount - owed))
        rec.update(lai=paid_interest, goc=principal, giam=before - d["tien"], tu=d.get("ngay_lai"))
        d["ngay_lai"] = e["ngay"]
    d.setdefault("tra", []).append(rec)
    d["tra"] = d["tra"][-60:]
    if d["tien"] <= 0:
        d["xong"] = day.isoformat()
        return Payment(d["ten"], True, 0, d.get("thang"), None, paid_interest or 0, principal, extra)
    return Payment(d["ten"], False, d["tien"], d.get("thang"), schedule(d, day), paid_interest or 0, principal, extra,
                   interest_only(d))


def undo_payment(d, e, reference):
    """Khoản trả e bị xóa hoặc bỏ trừ: cộng lại dư nợ d (chưa lưu). Nợ có lãi: hoàn lại đúng phần dư nợ đã giảm và mốc dồn lãi."""
    rec = next((p for p in d.get("tra", []) if p.get("ref") == reference), None)
    d["tra"] = [p for p in d.get("tra", []) if p.get("ref") != reference]
    d["tien"] += rec["giam"] if rec and "giam" in rec else e["tien"]
    if rec and rec.get("tu"):
        d["ngay_lai"] = rec["tu"]
    d.pop("xong", None)


def tokens(text):
    return set(re.findall(r"[a-z0-9]+", plain(text or "")))


def match(e, items, group, other_group):
    """Khoản chi e là lần trả khoản nợ nào: so tên khoản nợ với ghi chú; khoản ở nhóm Trả nợ/Khác thì so cả số
    tiền với mức trả mỗi tháng. Không chắc (không khớp hoặc khớp nhiều khoản ngang nhau) thì None."""
    note = tokens(e.get("ghichu"))
    loose = e["nhom"] in (group, other_group)  # chỉ khoản Trả nợ/Khác mới so số tiền (5tr tiền nhà không phải trả nợ)
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


def find_by_name_words(items, text):
    """Khoản nợ mà mọi chữ đặc trưng trong tên đều có trong text (cho /no tra <tên> <số tiền>); None nếu không có."""
    return next((x for x in items if tokens(x["ten"]) - SKIP and (tokens(x["ten"]) - SKIP) <= tokens(text)), None)


# ---- Sức khỏe nợ -------------------------------------------------------------------------

@dataclass
class DebtHealth:
    """Kết quả chấm nợ cho khám sức khỏe tài chính: điểm 0–20 và các số để dựng dòng báo."""
    none: bool = False  # không có nợ nào
    score: int = 20
    mark: str = "✅"
    basis: str = ""  # "thu": chấm theo tiền trả mỗi tháng so với thu nhập; "tai_san": theo nợ có lãi so với tài sản
    monthly: int = 0
    share: float = 0  # phần trăm tiền trả mỗi tháng trên thu nhập
    owed: float = 0  # tổng nợ có lãi
    ratio: float = 0  # phần trăm nợ có lãi trên tài sản
    has_bearing: bool = False  # có khoản nợ có lãi
    bearing_total: float = 0
    bearing_last: str | None = None  # tháng xong của khoản nợ có lãi xong muộn nhất, nếu đủ thông tin
    has_zero: bool = False  # có khoản nợ không lãi
    zero_total: float = 0
    late: list = field(default_factory=list)  # tên các khoản trễ hạn tháng này


def debt_health(items, assets, income, day, due, pay_day_of):
    """Chấm theo tiền trả nợ mỗi tháng so với thu nhập; chưa biết thu nhập thì theo nợ CÓ LÃI so với tài sản.
    Nợ không lãi (người thân) ghi riêng, không bị coi như nợ vay. due: due_now(...); pay_day_of(d): hạn trả của d."""
    active = active_of(items)
    if not active:
        return DebtHealth(none=True)
    bearing = [d for d in active if has_interest(d)]
    zero = [d for d in active if not has_interest(d)]
    monthly = monthly_total(items)
    h = DebtHealth(monthly=monthly)
    if monthly and income:
        h.basis = "thu"
        h.share = share = monthly / income * 100
        h.score = 20 if share <= 20 else 16 if share <= 30 else 10 if share <= 40 else 5 if share <= 50 else 0
        h.mark = "✅" if share <= 30 else "⚠️" if share <= 50 else "🚨"
    else:
        h.basis = "tai_san"
        h.owed = owed = sum(d["tien"] for d in bearing)
        h.ratio = ratio = owed / assets * 100 if assets else (100 if owed else 0)
        h.score = 20 if not owed else 16 if ratio < 30 else 8 if ratio < 50 else 0
        h.mark = "✅" if ratio < 30 else "⚠️" if ratio < 50 else "🚨"
    h.has_bearing, h.has_zero = bool(bearing), bool(zero)
    h.bearing_total = sum(d["tien"] for d in bearing)
    if bearing:
        ends = [schedule(d, day) for d in bearing]
        h.bearing_last = max(s[1] for s in ends) if all(ends) else None
    h.zero_total = sum(d["tien"] for d in zero)
    h.late = [d["ten"] for d, _ in due if day.day >= pay_day_of(d) + 5]
    if h.late:
        h.score = max(0, h.score - 5)
        h.mark = "⚠️" if h.mark == "✅" else h.mark
    return h


# ---- Kết quả của các việc ------------------------------------------------------------------

@dataclass
class DeclareResult:
    status: str  # "thieu_con": khoản mới mà chưa có số còn nợ | "ok"
    name: str = ""
    debt: dict | None = None
    created: bool = False
    group_note: str = ""


@dataclass
class PayResult:
    status: str  # "het_hoac_xoa" | "ok"
    entry: dict | None = None
    payment: Payment | None = None
    group_note: str = ""


@dataclass
class Paid:
    """Một khoản vừa ghi đã trừ vào khoản nợ d."""
    debt: dict
    payment: Payment
    ref: str


@dataclass
class Ask:
    """Khoản trả nợ chưa rõ của khoản nợ nào: hỏi (kèm các khoản nợ để chọn)."""
    entry: dict
    ref: str
    choices: list = field(default_factory=list)


@dataclass
class ViewState:
    items: list  # khoản nợ còn dư
    done: list  # khoản nợ đã trả xong
    monthly: int
    due: list  # [(khoản nợ, còn phải trả tháng này)]
