"""Khai báo tài sản: tiền, tiết kiệm, cổ phiếu/ETF/quỹ/tiền số, ngoại tệ, vàng. Câu báo còn nằm trong module này
(tách sang presentation sau)."""
import html
import re
from datetime import date

from domain.common.dates import add_months
from domain.common.format import vnd
from domain.common.money import number
from domain.common.text import plain
from domain.taisan import rules
from domain.taisan.kinds import TYPES
from domain.taisan.text import gold_name, qty_text
from domain.vang.gold import GoldLot
from infrastructure import clock
from repositories.taisan import assets as assets_repo
from repositories.vang import gold as gold_repo
from services.taisan import accounts
from services.taisan.prices import prices


def add_simple(data, kind, args):
    got = rules.money_and_name(args)
    if not got:
        return None
    name, amount = got
    for it in data["items"]:
        if it["loai"] == kind and accounts.same_name(it["ten"], name):  # cùng tên: cập nhật
            it.update(tien=amount, ngay=clock.now_vn().date().isoformat())
            if it.get("chinh"):
                accounts.pin_balance(it, amount)
            return f"✅ Đã cập nhật {TYPES[kind]}: {html.escape(name)} {vnd(amount)}"
    data["items"].append({"id": assets_repo.new_id(data), "loai": kind, "ten": name, "tien": amount,
                          "ngay": clock.now_vn().date().isoformat()})
    return f"✅ Đã thêm {TYPES[kind]}: {html.escape(name)} {vnd(amount)}"

def add_loan(data, borrower, amount):
    """Cho người khác vay (chưa lưu): khoản phải thu "Cho X vay" thuộc Tài sản khác. Người này đã có khoản phải thu thì
    cộng dồn (cho vay thêm), không ghi đè như khai báo số dư."""
    name = f"Cho {borrower} vay"[:30]
    for it in data["items"]:
        if it["loai"] == "khac" and accounts.same_name(it["ten"], name):
            it.update(tien=it["tien"] + amount, ngay=clock.now_vn().date().isoformat())
            return (f"✅ Đã cộng thêm vào {TYPES['khac']}: {html.escape(it['ten'])} +{vnd(amount)} → "
                    f"tổng {vnd(it['tien'])}")
    return add_simple(data, "khac", [name, f"{amount}đ"])


def add_saving(data, args):
    text = " ".join(args)
    bare = plain(text)
    rate = re.search(r"(\d+(?:[.,]\d+)?)\s*%", text)
    term = re.search(r"(?<!\w)(\d{1,2})\s*(?:thang|th|t)(?!\w)", bare)
    when = re.search(r"(?<![\d/])(\d{1,2})/(\d{1,2})(?:/(\d{4}))?(?![\d/])", text)
    rest = text
    for m in (rate, when):
        if m:
            rest = rest.replace(m[0], " ")
    if term:  # bỏ "6 tháng" ở chữ gốc (cùng vị trí với chữ đã bỏ dấu)
        rest = re.sub(r"(?<!\w)\d{1,2}\s*(?:tháng|thang|th|t)(?!\w)", " ", rest, count=1, flags=re.IGNORECASE)
    rest = re.sub(r"(?i)không kỳ hạn|khong ky han|kkh", " ", rest)
    got = rules.money_and_name(rest.split())
    if not got or not rate:
        return None
    name, amount = got
    start = clock.now_vn().date()
    if when:
        try:
            start = date(int(when[3]) if when[3] else start.year, int(when[2]), int(when[1]))
        except ValueError:
            return None
    months = 0 if re.search(r"khong ky han|kkh", bare) or not term else int(term[1])
    return add_saving_item(data, name, amount, number(rate[1]), months, start)

def add_saving_item(data, name, amount, rate, months, start):
    """Thêm một sổ tiết kiệm (chưa lưu): tên, tiền gốc, lãi %/năm, kỳ hạn tháng (0 là không kỳ hạn), ngày gửi. Sổ
    cùng tên đã có thì cập nhật (khai báo lại khi đối chiếu, gửi tiếp), không tạo sổ trùng."""
    same = next((it for it in data["items"] if it["loai"] == "tietkiem" and accounts.same_name(it["ten"], name[:30])), None)
    if same:
        same.update(tien=amount, lai=rate, ky=months, ngay=start.isoformat())
        due = f", đáo hạn {add_months(start, months):%d/%m/%Y}" if months else ", không kỳ hạn"
        return f"✅ Đã cập nhật sổ tiết kiệm {html.escape(name[:30])} {vnd(amount)}, lãi {qty_text(rate)}%/năm{due}"
    data["items"].append({"id": assets_repo.new_id(data), "loai": "tietkiem", "ten": name[:30], "tien": amount,
                          "lai": rate, "ky": months, "ngay": start.isoformat()})
    due = f", đáo hạn {add_months(start, months):%d/%m/%Y}" if months else ", không kỳ hạn"
    return f"✅ Đã thêm sổ tiết kiệm {html.escape(name[:30])} {vnd(amount)}, lãi {qty_text(rate)}%/năm{due}"

def add_holding(data, kind, args):
    """cp/etf/quy/coin: mã, số lượng, giá vốn (không bắt buộc với coin). Mã đã có thì ghi đè (khai báo lại)."""
    if len(args) < 2 or (kind != "coin" and len(args) < 3):
        return None
    code = args[0].upper() if kind != "coin" else args[0].lower()
    try:
        qty = number(args[1])
        cost = (rules.stock_price(args[2]) if kind in ("cp", "etf", "quy") else number(args[2])) if len(args) > 2 else None
    except ValueError:
        return None
    if qty <= 0:
        return None
    if kind in ("cp", "etf"):
        if not re.fullmatch(r"[A-Z0-9]{3,8}", code):
            return None
        kind = "etf" if rules.is_etf(code) else "cp"  # "/taisan cp E1VFVN30 ..." cũng vào ETF
        listed, _, stale = prices(kind, [code])
        if code not in listed and not stale:
            return f"Không thấy mã {html.escape(code)} trên sàn"
    data["items"] = [it for it in data["items"] if not (it["loai"] in (kind, "cp", "etf") and it["ma"] == code)]
    data["items"].append({"id": assets_repo.new_id(data), "loai": kind, "ma": code, "sl": qty, "gia_von": cost})
    return (f"✅ Đã khai báo {TYPES[kind]} {html.escape(code.upper())}: {qty_text(qty)}"
            + (f", giá vốn {vnd(cost)}" if cost else ""))

def add_fx(data, code, args):
    try:
        qty = number(args[0])
    except (IndexError, ValueError):
        return None
    code = code.upper()
    data["items"] = [it for it in data["items"] if not (it["loai"] == "ngoaite" and it["ma"] == code)]
    data["items"].append({"id": assets_repo.new_id(data), "loai": "ngoaite", "ma": code, "sl": qty, "gia_von": None})
    return f"✅ Đã khai báo ngoại tệ {code}: {qty_text(qty)}"

def add_gold(args):
    """/taisan vang nhan 0,1 chi 148,02 [20/10]: loại, số lượng, đơn vị, giá mua triệu/lượng, ngày mua (không bắt buộc;
    có thì hiện ở 💼 Tài sản)."""
    from domain.lenh import rules as lenh  # dùng chung cách nhập của /vivang bên bot bản tin
    bought = None
    if args and re.fullmatch(r"\d{1,2}/\d{1,2}(?:/\d{4})?", args[-1]):
        parts = [int(x) for x in args[-1].split("/")]
        today = clock.now_vn().date()
        try:
            bought = date(parts[2] if len(parts) > 2 else today.year, parts[1], parts[0])
        except ValueError:
            return None
        if bought > today:
            bought = bought.replace(year=bought.year - 1)
        args = args[:-1]
    try:
        kind = lenh.KINDS[args[0].lower()]
        taels = number(args[1]) * lenh.UNITS[args[2].lower()]
        paid = number(args[3]) if len(args) > 3 else None
    except (KeyError, IndexError, ValueError):
        return None
    if not 0 < taels <= 1000:
        return None
    gold_repo.add(GoldLot(kind, taels, paid, bought.isoformat() if bought else None))
    return f"✅ Đã thêm {lenh.amount_text(taels)} {gold_name(kind).lower()} vào ví vàng (dùng chung với bot bản tin)"
