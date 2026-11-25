"""Sổ nợ: khai báo, trả nợ (bấm nút, lệnh, hoặc tự nhận từ khoản vừa ghi), bỏ trừ nợ, nhắc hạn, chấm sức khỏe nợ.

Trả kết quả có cấu trúc (domain.no.debt), không trả chữ.
"""
from domain.chitieu.kinds import INCOME, OTHER
from domain.chitieu.refs import ref
from repositories.chitieu import ledger as ledger_repo
from services.chitieu import groups as chitieu_groups
from services.chitieu import ledger as ledger_service
from infrastructure import clock
from services.taisan import accounts
from domain.no import debt as rules
from domain.no.debt import Ask, DeclareResult, Paid, PayResult, ViewState
from infrastructure import kho
from repositories.chitieu import ledger as ledger_repo
from repositories.luong import salary as salary_repo
from repositories.no import debts as debt_repo


# ---- Truy vấn ----------------------------------------------------------------------------

def debts(data=None):
    return rules.debts_of((data or debt_repo.load())["items"])


def active(data=None):
    return rules.active_of((data or debt_repo.load())["items"])


def by_id(data, debt_id):
    return next((d for d in debts(data) if str(d["id"]) == str(debt_id)), None)


def due_now(day, data=None):
    return rules.due_now((data or debt_repo.load())["items"], day)


def monthly_total(data=None):
    return rules.monthly_total((data or debt_repo.load())["items"])


def freed(data=None, ym=None):
    return rules.freed((data or debt_repo.load())["items"], ym)


def pay_day(d, day):
    salary = salary_repo.load()
    return rules.pay_day(d, day, salary.day if salary else None)


def debt_group(create=False):
    """(mã nhóm chi Trả nợ, câu báo nếu vừa tạo). Chưa có nhóm thì tạo khi create=True."""
    code = chitieu_groups.find_group("trả nợ")
    if code or not create:
        return code, ""
    chitieu_groups.nhom_them(rules.GROUP_LABEL)
    chitieu_groups.reset()
    code = chitieu_groups.find_group("trả nợ")
    return code, ("🏦 Đã tạo nhóm chi «Trả nợ» để ghi các lần trả nợ" if code else "")


def now():
    return clock.now_vn()


def home_summary(day):
    """(các khoản còn dư, đã trả, cần trả tháng này) cho dòng tổng quan; None nếu không có nợ."""
    data = debt_repo.load()
    items = active(data)
    if not items:
        return None
    paid, need = rules.month_progress(data["items"], day)
    return items, paid, need


def view_state(day):
    data = debt_repo.load()
    return ViewState(active(data), [d for d in debts(data) if d["tien"] <= 0], monthly_total(data), due_now(day, data))


# ---- Khai báo ----------------------------------------------------------------------------

def declare(text, day):
    """Đọc câu khai báo rồi thêm/cập nhật khoản nợ; None nếu không đọc được tên."""
    info = rules.parse_debt(text)
    if not info or not info["ten"]:
        return None
    return declare_info(info, day)


def declare_info(info, day):
    """Thêm hoặc cập nhật một khoản nợ từ các trường đã đọc: {"ten", "con", "goc", "thang", "lai", "ngay_tra", "nay"}
    (trường không có để None)."""
    info = {"con": None, "goc": None, "thang": None, "lai": None, "ngay_tra": None, "nay": False, **info}
    data = debt_repo.load()
    d = next((x for x in debts(data) if accounts.same_name(x["ten"], info["ten"])), None)
    created = d is None
    if created:
        if not info["con"]:
            return DeclareResult("thieu_con", name=info["ten"])
        d = {"id": debt_repo.new_id(data), "loai": "no", "ten": info["ten"], "tien": info["con"], "ngay": day.isoformat()}
        data["items"].append(d)
    rules.apply_info(d, info, day, created)
    debt_repo.save(data)
    _, group_note = debt_group(create=True)
    return DeclareResult("ok", d["ten"], d, created, group_note)


def main_account_name():
    """Tên tài khoản chính (để hỏi tiền vay đã vào đâu); None nếu chưa chọn."""
    it = accounts.main_account(debt_repo.load())
    return it["ten"] if it else None


def receive_loan(debt_id, amount, day):
    """Tiền vay mới đã vào tài khoản chính: cộng vào số dư, một lần cho mỗi khoản nợ (khai báo nợ một mình làm tài sản ròng
    giảm vì thêm nợ mà không có tiền vào). Trả (trạng thái, dòng báo): "het" (khoản nợ đã xóa) | "da_cong" | "chua_co_tk" | "ok"."""
    data = debt_repo.load()
    d = by_id(data, debt_id)
    if not d:
        return "het", None
    if d.get("tien_vao"):
        return "da_cong", None
    note = accounts.move_main(data, amount, f"tiền vay {d['ten']}", day)
    if not note:
        return "chua_co_tk", None
    d["tien_vao"] = int(amount)
    debt_repo.save(data)
    return "ok", note


def remove(debt_id):
    """Xóa khoản nợ; False nếu đã xóa rồi."""
    data = debt_repo.load()
    kept = [it for it in data["items"] if not (it["loai"] == "no" and str(it["id"]) == str(debt_id))]
    if len(kept) == len(data["items"]):
        return False
    data["items"] = kept
    debt_repo.save(data)
    return True


# ---- Trả nợ ------------------------------------------------------------------------------

def pay(debt_id, amount, now):
    """Bấm ✅ Trả: ghi khoản chi nhóm Trả nợ và trừ dư nợ."""
    data = debt_repo.load()
    d = by_id(data, debt_id)
    if not d or d["tien"] <= 0:
        return PayResult("het_hoac_xoa")
    group, note = debt_group(create=True)
    day = now.date()
    e = {"id": ledger_repo.next_id(), "ngay": day.isoformat(), "gio": now.strftime("%H:%M"),
         "tien": int(amount), "ghichu": f"trả nợ {d['ten']}", "nhom": group or OTHER, "no": d["id"]}
    if not group:
        e["dekhac"] = True
    ledger_repo.save(e)
    payment = rules.apply_payment(d, e, ref(e), day)
    debt_repo.save(data)
    return PayResult("ok", e, payment, note)


def after_record(entries, day):
    """Vừa ghi các khoản (tin nhắn hoặc ảnh): khoản nào là trả nợ thì trừ dư nợ. Trả danh sách Paid/Ask."""
    entries = [e for e in entries if e["nhom"] != INCOME and not e.get("no")]
    if not entries or not kho.ready():
        return []
    data = debt_repo.load()
    items = active(data)
    if not items:
        return []
    group = debt_group()[0]
    events, changed, asked = [], False, False
    for e in entries:
        d = rules.match(e, items, group, OTHER)
        if d:
            if group and e["nhom"] != group and (e["nhom"] == OTHER or e.get("ai")):
                e["nhom"] = group
                e.pop("ai", None)
                ledger_service.learn(e["ghichu"], group)  # lần sau ghi giống vậy vào thẳng nhóm Trả nợ
            e["no"] = d["id"]
            ledger_repo.save(e)
            events.append(Paid(d, rules.apply_payment(d, e, ref(e), day), ref(e)))
            changed = True
        elif group and e["nhom"] == group and not asked:
            asked = True  # khoản trả nợ chưa rõ của khoản nợ nào: hỏi (một khoản mỗi tin)
            events.append(Ask(e, ref(e), items[:3]))
    if changed:
        debt_repo.save(data)
    return events


def undo(e):
    """Khoản trả nợ e bị xóa hoặc bỏ trừ: cộng lại dư nợ. Trả khoản nợ, None nếu không còn."""
    data = debt_repo.load()
    d = by_id(data, e.get("no"))
    if not d:
        return None
    rules.undo_payment(d, e, ref(e))
    debt_repo.save(data)
    return d


def assign(e, debt_id, day):
    """Gán khoản chi e vào khoản nợ debt_id (khi bot hỏi): Payment, hoặc None nếu khoản nợ không còn hoặc e đã trừ nợ rồi."""
    data = debt_repo.load()
    d = by_id(data, debt_id)
    if not d or e.get("no"):
        return None
    e["no"] = d["id"]
    ledger_repo.save(e)
    payment = rules.apply_payment(d, e, ref(e), day)
    debt_repo.save(data)
    return payment


def unassign(e):
    """Bỏ trừ nợ của khoản chi e: trả khoản nợ (đã cộng lại) hoặc None nếu không còn khoản nợ."""
    d = undo(e)
    e.pop("no", None)
    ledger_repo.save(e)
    return d


def find_for_command(rest):
    """Khoản nợ ứng với câu '/no tra <tên> <số tiền>'."""
    return rules.find_by_name_words(active(), rest)


# ---- Nhắc, sức khỏe ----------------------------------------------------------------------

def reminders(day):
    """[(khoản nợ, còn phải trả)] cần nhắc hôm nay: tới hạn mà tháng này chưa trả đủ; mỗi khoản nhắc tối đa 2 lần mỗi
    tháng (ngày hạn và 5 ngày sau) nên đánh dấu đã nhắc ngay ở đây."""
    ym = rules.month_of(day)
    due = []
    for d, left in due_now(day):
        start = pay_day(d, day)
        if day.day < start:
            continue
        stage = 1 if day.day < start + 5 else 2
        if debt_repo.claim_reminder(d["id"], ym, stage):
            due.append((d, left))
    return due


def health(day, v, income):
    """DebtHealth cho khám sức khỏe tài chính (v: định giá tài sản, income: thu nhập hoặc None)."""
    data = debt_repo.load()
    return rules.debt_health(data["items"], v["assets"], income, day, due_now(day, data), lambda d: pay_day(d, day))
