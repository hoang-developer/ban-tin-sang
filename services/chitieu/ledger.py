"""Sổ thu chi: ghi các khoản trong tin nhắn (xếp nhóm bằng từ khóa, cụm đã học, AI), nhớ nhóm người dùng chọn,
xếp lại khoản đang ở Khác, các khoản gần đây."""
from datetime import timedelta

from domain.chitieu import classify
from domain.chitieu import learn as learn_rules
from domain.chitieu import parse
from domain.chitieu.kinds import OTHER
from repositories.chitieu import groups as groups_repo
from repositories.chitieu import ledger as ledger_repo
from services.chitieu import ai_sort


def add(text, now):
    """Ghi mọi khoản trong tin nhắn (mỗi dòng một khoản); trả về các khoản đã ghi."""
    learned = groups_repo.learned()
    cfg = groups_repo.config()
    entries = [e for e in (parse.parse_line(line, now.date(), learned, cfg) for line in text.splitlines()) if e]
    chosen = [(e["ghichu"], e["nhom"]) for e in entries if e.get("_chon") and e["nhom"] != OTHER]
    if chosen:
        learn_all(chosen)
    ai_sort.ask_ai(entries, learned)
    for e in entries:
        e["id"] = ledger_repo.next_id()
        e["gio"] = now.strftime("%H:%M")
        ledger_repo.save(e)
    return entries


def recent(day, limit):
    """Các khoản mới nhất của tháng này và tháng trước."""
    prev = (day.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    items = ledger_repo.load(prev) + ledger_repo.load(day.strftime("%Y-%m"))
    return sorted(items, key=lambda e: (e["ngay"], e.get("gio", ""), e["id"]), reverse=True)[:limit]


def learn_all(pairs):
    """Nhớ nhóm người dùng chọn cho các ghi chú [(ghi chú, mã)]."""
    pairs = [(learn_rules.learn_key(note), code) for note, code in pairs if note]
    if not pairs:
        return
    groups_repo.save_learned(learn_rules.merge_learned(groups_repo.learned(), pairs))


def learn(note, code):
    learn_all([(note, code)])


def tidy(day):
    """Xếp lại các khoản đang ở Khác (tháng này và tháng trước) theo từ khóa, cụm từ đã học mới nhất.
    Trả về số khoản đã chuyển nhóm."""
    table = classify.rules(groups_repo.learned(), groups_repo.config())
    prev = (day.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    moved = 0
    for e in ledger_repo.load(prev) + ledger_repo.load(day.strftime("%Y-%m")):
        if learn_rules.pending(e) and e["ghichu"]:
            code = classify.pick(e["ghichu"], table)
            if code != OTHER:
                e["nhom"] = code
                ledger_repo.save(e)
                moved += 1
    return moved


def find(reference):
    """'2026-11:12' -> khoản đó, None nếu đã xóa."""
    ym, _, rid = reference.partition(":")
    return ledger_repo.find(ym, rid)
