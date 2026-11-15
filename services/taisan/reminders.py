"""Nhắc lương và nhắc sổ tiết kiệm đáo hạn. Câu nhắc còn nằm trong module này (tách sang presentation sau)."""
import html
from calendar import monthrange

from domain.chitieu.kinds import INCOME
from domain.common.format import short
from domain.common.text import plain
from domain.taisan import rules
from repositories.chitieu import ledger as ledger_repo
from repositories.luong import salary as salary_repo
from repositories.taisan import assets as assets_repo
from repositories.taisan import reminders as reminders_repo


def salary_due(day):
    """(tin nhắc, nút) nếu hôm nay trong 3 ngày từ ngày lương mà tháng này chưa ghi lương; None nếu không."""
    s = salary_repo.load()
    if not s:
        return None
    payday = min(s.day, monthrange(day.year, day.month)[1])
    if not 0 <= day.day - payday <= 3:
        return None
    month = ledger_repo.between(day.replace(day=1), day)
    if any(e["nhom"] == INCOME and "luong" in plain(e["ghichu"]) for e in month):
        return None
    return (f"💼 {'Hôm nay ngày lương' if day.day == payday else f'Đã qua ngày lương {payday}'}: đã nhận chưa?",
            [[(f"✅ Đã nhận {short(s.amount)}", f"ts:luong:{s.amount}"), ("Chưa", "ts:chua")]])


def maturity_notes(day):
    """Sổ tiết kiệm đáo hạn trong 3 ngày tới (mỗi sổ nhắc một lần)."""
    notes = []
    for it in assets_repo.load()["items"]:
        if it["loai"] == "tietkiem" and it.get("ky"):
            interest, maturity = rules.accrued(it, day)
            if 0 <= (maturity - day).days <= 3 and reminders_repo.claim_maturity(it["id"], maturity):
                notes.append(f"🐷 Sổ {html.escape(it['ten'])} {short(it['tien'])} đáo hạn {maturity:%d/%m}"
                             f" (lãi ~{short(interest)})")
    return notes
