"""Đối chiếu tài sản mỗi tháng: liệt kê ngăn, ghi số thật, đánh dấu khớp, ghi khoản lệch của tài khoản chính.

Trả kết quả có cấu trúc (domain.doichieu.reconcile), không trả chữ.
"""
import sys

from domain.chitieu.kinds import INCOME
from domain.chitieu.kinds import OTHER
from repositories.taisan import assets as assets_repo
from services.taisan import accounts
from domain.doichieu import reconcile as rules
from domain.doichieu.reconcile import DAY, GapBooked, ScreenState, SetResult, Slot
from repositories.chitieu import ledger as ledger_repo
from repositories.dautu import fund as fund_repo
from repositories.doichieu import reconcile as reconcile_repo


def ym_of(day):
    return day.strftime("%Y-%m")


def done_in(day):
    """{id ngăn: bản ghi} các ngăn đã đối chiếu trong tháng của day."""
    return reconcile_repo.load_month(ym_of(day))["muc"]


def items(day):
    """Các ngăn cần đối chiếu: [Slot(mục tài sản, giá trị bot đang tính, đơn vị)]."""
    data = assets_repo.load()
    out = []
    for it in data["items"]:
        kind = it["loai"]
        if kind == "tien":
            out.append(Slot(it, accounts.main_balance(it, day) if it.get("chinh") else it["tien"], "đ"))
        elif kind in ("tietkiem", "khac"):
            out.append(Slot(it, it["tien"], "đ"))
        elif kind == "no" and it.get("tien", 0) > 0:
            out.append(Slot(it, it["tien"], "đ"))
        elif kind in rules.UNITS:
            out.append(Slot(it, it["sl"], rules.unit_of(it)))
    return out


def pending_fund(it):
    """Quỹ mở còn lệnh chờ khớp hoặc hoán đổi đang chuyển."""
    if it["loai"] != "quy":
        return False
    try:
        return rules.has_pending_order(it, fund_repo.load())
    except Exception as e:
        print(f"[lỗi] lệnh quỹ khi đối chiếu: {e!r}", file=sys.stderr)
        return False


def screen_state(day):
    done = done_in(day)
    entries = []
    for slot in items(day):
        rec = done.get(str(slot.item["id"]))
        entries.append((slot, rec, False if rec else pending_fund(slot.item)))
    return ScreenState(entries, done)


def record(day, it, bot_value, real, unit):
    ym = ym_of(day)
    month = reconcile_repo.load_month(ym)
    gap = rules.gap_of(real, bot_value, unit)
    month["muc"][str(it["id"])] = rules.make_record(it, bot_value, real, unit, gap)
    reconcile_repo.save_month(ym, month)
    return gap


def _find(day, item_id):
    return next((s for s in items(day) if str(s.item["id"]) == str(item_id)), None)


def set_value(item_id, real, now):
    """Ghi số thật của một ngăn: ghi đè, lưu khoản lệch."""
    day = now.date()
    data = assets_repo.load()
    found = _find(day, item_id)
    if not found:
        return SetResult("khong_con")
    it, bot_value, unit = found
    if pending_fund(it):
        return SetResult("cho_khop", it, bot_value, real, unit)
    it = next(x for x in data["items"] if x["id"] == it["id"])
    if unit == "đ":
        real = int(round(real))
        if it.get("chinh"):
            accounts.pin_balance(it, real)
        else:
            it["tien"] = real
        it["ngay"] = day.isoformat()
        if it["loai"] == "no" and real <= 0:
            it["xong"] = day.isoformat()
    else:
        if real < 0:
            return SetResult("so_am", it, bot_value, real, unit)
        it["sl"] = round(real, 4)
    assets_repo.save(data)
    gap = record(day, it, bot_value, real, unit)
    return SetResult("lech" if gap else "khop", it, bot_value, real, unit, gap)


def mark_ok(item_id, day):
    """Đánh dấu một ngăn khớp; False nếu ngăn không còn hoặc còn lệnh chờ khớp."""
    found = _find(day, item_id)
    if not found or pending_fund(found.item):
        return False
    it, value, unit = found
    record(day, it, value, value, unit)
    return True


def all_ok(day):
    """Đánh dấu khớp hết các ngăn chưa đối chiếu (trừ ngăn còn lệnh chờ khớp); trả số ngăn đã đánh dấu."""
    n = 0
    for it, value, unit in items(day):
        if str(it["id"]) not in done_in(day) and not pending_fund(it):
            record(day, it, value, value, unit)
            n += 1
    return n


def book_gap(item_id, now):
    """Khoản lệch của tài khoản chính thành khoản chi (thu) chưa ghi: vào báo cáo, không trừ số dư lần nữa."""
    day = now.date()
    ym = ym_of(day)
    rec = reconcile_repo.load_month(ym)["muc"].get(str(item_id))
    if not rec or not rec["lech"] or rec.get("ghi"):
        return GapBooked("da_xu_ly")
    gap = rec["lech"]
    ledger_repo.save({"id": ledger_repo.next_id(), "ngay": day.isoformat(), "gio": now.strftime("%H:%M"),
                      "tien": abs(gap), "ghichu": f"{'chi' if gap < 0 else 'thu'} chưa ghi (đối chiếu {rec['ten']})",
                      "nhom": INCOME if gap > 0 else OTHER, "khong_tk": True})
    month = reconcile_repo.load_month(ym)
    month["muc"][str(item_id)]["ghi"] = True
    reconcile_repo.save_month(ym, month)
    return GapBooked("ok", gap)


def remaining(day):
    done = done_in(day)
    return [it for it, _, _ in items(day) if str(it["id"]) not in done]


def morning_count(day):
    """Số ngăn còn lại để nhắc trong tin sáng ngày 15 (mỗi tháng một lần); None nếu không nhắc."""
    if day.day != DAY:
        return None
    left = remaining(day)
    if not left or not reconcile_repo.claim_reminder(f"{day:%Y-%m}"):
        return None
    return len(left)


def todo_count(day):
    """Số ngăn còn lại từ ngày 15 tới hết tháng; None nếu chưa tới hoặc đã xong."""
    if day.day < DAY:
        return None
    left = remaining(day)
    return len(left) if left else None
