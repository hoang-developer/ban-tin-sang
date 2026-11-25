"""Lệnh của bot chi tiêu: /baocao, /thang, /lichsu, /xoa, /ngansach, /nhom, /chuaxep, /xuat. Đọc lệnh, gọi service, nhờ
presentation dựng tin; mỗi hàm trả tin nhắn HTML, hoặc (tin nhắn, nút bấm), /xuat trả về file CSV."""
import csv
import html
import io
import json
import re
import sys

from domain.chitieu import classify as classify_rules
from domain.chitieu import labels
from domain.chitieu.kinds import INCOME, OTHER
from domain.chitieu.learn import pending
from domain.chitieu.refs import ref
from domain.common.format import vnd
from domain.common.money import parse_amount
from domain.common.text import plain
from infrastructure import ai as ai_client
from interface.chitieu.context import (BACK, REPORT_BUTTONS, bare, budget_label, budget_lines,  # noqa: F401
                                       budget_status, config, entries_message, entry_text, find_group, groups, name,
                                       report, save_config, today)
from repositories.chitieu import budget as budget_repo
from repositories.chitieu import groups as groups_repo
from repositories.chitieu import ledger as ledger_repo
from services.chitieu import ai_sort, ledger
from services.chitieu.groups import (MAX_GROUPS, MAX_WORDS, NHOM_USAGE, add_words, after_change,  # noqa: F401
                                     forget_learned, nhom_them)

MAX_GROUPS, MAX_WORDS = 20, 60  # số nhóm tự tạo, số từ khóa tự thêm cho mỗi nhóm
ai_key = ai_client.key


def baocao(args):
    kind = {"homnay": "ngay", "ngay": "ngay", "tuan": "tuan", "thang": "thang", "thangtruoc": "thangtruoc"}.get(
        plain("".join(args)), "thang")
    return report(kind, today())[0], REPORT_BUTTONS

def thang(args):
    if args and args[0].isdigit() and 1 <= int(args[0]) <= 12:
        return report(str(int(args[0])), today())[0], REPORT_BUTTONS
    return report("thang", today())[0], REPORT_BUTTONS

def lichsu(args):
    day = today()
    items = ledger.recent(day, 10)
    if not items:
        return "Chưa có khoản nào. Nhắn kiểu: cà phê 35k"
    lines = ["🧾 <b>10 khoản gần nhất</b>"] + [
        f"{i}. {e['ngay'][8:]}/{e['ngay'][5:7]} {e.get('gio', '')} · {entry_text(e, day).split(' · ', 1)[0]} · "
        f"{name(e['nhom']).split()[0]} {html.escape(e['ghichu'])}" for i, e in enumerate(items, 1)]
    buttons = [(f"❌ {i}", f"xls:{ref(e)}") for i, e in enumerate(items, 1)]
    return "\n".join(lines), [buttons[i:i + 5] for i in range(0, len(buttons), 5)]

def delete(reference):
    """Xóa một khoản; trả về khoản đã xóa, None nếu đã xóa từ trước."""
    from interface.chitieu import features
    gone = ledger.find(reference)
    if gone:
        ledger_repo.remove(gone["ngay"][:7], gone["id"])
        if gone.get("no"):  # khoản trả nợ: cộng lại dư nợ
            try:
                features.sono().undo(gone)
            except Exception as e:
                print(f"[lỗi] hoàn dư nợ khi xóa khoản: {e!r}", file=sys.stderr)
    return gone

def xoa_cuoi(args):
    items = ledger.recent(today(), 1)
    if not items:
        return "Chưa có khoản nào để xóa"
    gone = delete(ref(items[0]))
    return f"🗑 Đã xóa: {entry_text(gone, today())}"

def ngansach(args):
    usage = ("Đặt ngân sách tháng: /ngansach ăn uống 3tr · /ngansach tổng 15tr\n"
             "Chi tiêu hằng ngày (ăn uống, đi chợ, đi lại…): /ngansach hằng ngày 9tr\n"
             "Bỏ ngân sách: /ngansach ăn uống 0")
    budgets = budget_repo.load()
    if not args:
        lines = budget_status(today())
        return "\n".join(["🎯 <b>Ngân sách tháng này</b>"] + lines + ["", usage]) if lines else usage
    code = classify_rules.find_category(" ".join(args[:-1]), config())
    if code is None or code == INCOME:
        return usage
    if args[-1] == "0":
        budgets.pop(code, None)
        budget_repo.save(budgets)
        return f"Đã bỏ ngân sách {budget_label(code)}"
    found = parse_amount(args[-1])
    if found is None:
        return usage
    budgets[code] = found[0]
    budget_repo.save(budgets)
    label = budget_label(code)
    return "\n".join([f"🎯 Ngân sách {label}: {vnd(found[0])}/tháng"] + budget_lines([code], today()))





def nhom_tukhoa(rest):
    head, words = labels.split_spec(rest)
    cfg = json.loads(json.dumps(config()))
    code = find_group(head, cfg=cfg) if head else None
    if not code or not words:
        return "Thêm từ khóa: /nhom tukhoa Ăn uống: bún chả, bánh tráng\n(tên nhóm, dấu hai chấm, các từ khóa cách nhau dấu phẩy)"
    if code == OTHER:
        return "Nhóm Khác dành cho khoản không khớp nhóm nào, không thêm từ khóa được"
    add_words(cfg, code, words)
    return after_change(cfg, f"✅ {name(code, cfg)} thêm từ khóa: {html.escape(', '.join(words))}")

def nhom_doiten(rest):
    head, _, new = rest.partition(":")
    cfg = json.loads(json.dumps(config()))
    code = find_group(head, cfg=cfg) if head.strip() else None
    label = labels.make_label(new, name(code, cfg)) if code and new.strip() else None
    if not label:
        return "Đổi tên: /nhom doiten Đi lại: 🚗 Xe cộ"
    old = name(code, cfg)
    cfg.setdefault("ten", {})[code] = label
    save_config(cfg)
    return f"✅ Đã đổi {html.escape(old)} thành {html.escape(label)}"

def nhom_xoa(rest):
    cfg = json.loads(json.dumps(config()))
    code = find_group(rest, cfg=cfg) if rest.strip() else None
    if not code:
        return "Ẩn nhóm: /nhom xoa Học tập"
    if code in (OTHER, INCOME):
        return "Không ẩn được nhóm Khác và Thu nhập"
    cfg.setdefault("an", []).append(code)
    save_config(cfg)
    return (f"✅ Đã ẩn nhóm {name(code, cfg)}: không còn trên nút chọn, bot không xếp vào nữa. Khoản cũ giữ "
            f"nguyên. Dùng lại: /nhom them {html.escape(bare(name(code, cfg)))}")

def nhom_hoc(rest):
    """/nhom hoc: các cụm bot đã học, gom theo nhóm; /nhom hoc xoa <cụm>: bỏ một cụm học nhầm."""
    words = rest.split()
    if words and plain(words[0]) in ("xoa", "bo"):
        phrase = " ".join(words[1:])
        if not phrase:
            return "Bỏ cụm học nhầm: /nhom hoc xoa bò"
        gone = forget_learned(phrase)
        if not gone:
            return f"Không thấy cụm «{html.escape(phrase)}» trong những cụm đã học. Xem danh sách: /nhom hoc"
        return (f"✅ Đã bỏ cụm {html.escape(', '.join(gone))}: lần sau bot xếp theo từ khóa, hoặc hỏi lại nhóm. "
                "Khoản đã ghi giữ nguyên nhóm.")
    learned = groups_repo.learned()
    if not learned:
        return "Bot chưa học cụm nào: mỗi lần bạn bấm chọn nhóm cho một khoản, bot nhớ cụm đó cho lần sau."
    by_group = {}
    for key, code in learned.items():
        by_group.setdefault(code, []).append(key)
    lines = [f"🧠 <b>Cụm bot đã học</b> ({len(learned)}), từ những lần bạn tự chọn nhóm",
             "<i>Cụm 1 chữ chỉ áp dụng khi cả ghi chú là chữ đó; cụm 2 chữ trở lên áp dụng ở bất kỳ chỗ nào trong câu.</i>"]
    for code, keys in by_group.items():
        keep = keys[:15]
        more = f" …+{len(keys) - len(keep)}" if len(keys) > len(keep) else ""
        lines.append(f"{html.escape(name(code))}: " + html.escape(", ".join(keep)) + more)
    lines.append("\nBỏ cụm học nhầm: /nhom hoc xoa bò")
    return "\n".join(lines)

def nhom_cmd(args):
    action = plain(args[0]) if args else ""
    rest = " ".join(args[1:])
    for words, handler in [(("them", "tao", "moi"), nhom_them), (("tukhoa", "tu", "tk"), nhom_tukhoa),
                           (("doiten", "ten", "sua"), nhom_doiten), (("xoa",), nhom_xoa), (("hoc",), nhom_hoc)]:
        if action in words:
            return handler(rest)
    learned = groups_repo.learned()
    cfg = config()
    lines = ["🗂 <b>Các nhóm và vài từ khóa</b>"]
    for code, (label, own, builtin) in groups().items():
        sample = ", ".join(list(dict.fromkeys(own + builtin))[:6])
        if code == OTHER:
            sample = "những khoản không khớp nhóm nào"
        mine = " (nhóm bạn tạo)" if code in cfg.get("moi", []) else ""
        lines.append(f"{html.escape(label)}{mine}: <i>{html.escape(sample) or 'chưa có từ khóa'}</i>")
    hidden = [name(c) for c in cfg.get("an", [])]
    if hidden:
        lines.append("Đã ẩn: " + html.escape(", ".join(hidden)))
    lines.append(f"\nBot đã học {len(learned)} cụm từ từ những lần bạn tự chọn nhóm.")
    guessed, fixed = ai_sort.ai_stats()
    accuracy = f"; đã đoán {guessed} khoản, bạn sửa {fixed}" + (
        f" (đúng {100 - fixed / guessed * 100:.0f}%)" if guessed else "") if guessed or fixed else ""
    quota = ai_sort.quota_text() if ai_key() else ""
    lines.append(f"✨ AI xếp nhóm cho khoản lạ: {'bật' if ai_key() else 'tắt'}{accuracy}"
                 + (f"\n✨ AI {html.escape(quota)}" if quota else ""))
    return "\n".join(lines + ["", NHOM_USAGE])

def chuaxep(args):
    """Các khoản đang ở Khác: xếp lại theo từ khóa, hỏi lại AI, còn lại thì hiện nút chọn từng khoản."""
    day = today()
    ledger.tidy(day)
    items = [e for e in ledger.recent(day, 1000) if pending(e)][:8]
    if not items:
        return "✅ Không còn khoản nào chưa rõ nhóm. Khoản mới chưa rõ nhóm thì bot hỏi ngay khi ghi."
    if ai_sort.ask_ai(items, groups_repo.learned()):
        for e in items:
            if e.get("ai"):
                ledger_repo.save(e)
    return entries_message(items, day, sorting=True)

def xuat(args):
    day = today()
    if args and args[0].isdigit() and 1 <= int(args[0]) <= 12:
        month = int(args[0])
        year = day.year if month <= day.month else day.year - 1
    else:
        year, month = day.year, day.month
    items = sorted(ledger_repo.load(f"{year}-{month:02d}"), key=lambda e: (e["ngay"], e.get("gio", ""), e["id"]))
    if not items:
        return f"Tháng {month}/{year} chưa có khoản nào"
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Ngày", "Giờ", "Số tiền", "Thu/Chi", "Nhóm", "Ghi chú"])
    for e in items:
        writer.writerow([f"{e['ngay'][8:]}/{e['ngay'][5:7]}/{e['ngay'][:4]}", e.get("gio", ""), e["tien"],
                         "Thu" if e["nhom"] == INCOME else "Chi", bare(name(e["nhom"])), e["ghichu"]])
    # BOM để Excel nhận đúng tiếng Việt
    return {"file": ("\ufeff" + buf.getvalue()).encode("utf-8"), "name": f"chitieu-{year}-{month:02d}.csv",
            "caption": f"Chi tiêu tháng {month}/{year}: {len(items)} khoản"}
