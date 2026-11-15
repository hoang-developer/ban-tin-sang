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
    import sochitieu as ct  # module cũ ở gốc: sổ nợ (nạp muộn để né vòng)
    gone = ledger.find(reference)
    if gone:
        ledger_repo.remove(gone["ngay"][:7], gone["id"])
        if gone.get("no"):  # khoản trả nợ: cộng lại dư nợ
            try:
                ct.sono().undo(gone)
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

NHOM_USAGE = ("<b>Tự chỉnh nhóm</b>\n"
              "• Tạo nhóm: /nhom them 🏦 Trả nợ: trả nợ, trả góp, vay\n"
              "• Thêm từ khóa: /nhom tukhoa Ăn uống: bún chả, bánh tráng\n"
              "• Đổi tên: /nhom doiten Đi lại: 🚗 Xe cộ\n"
              "• Ẩn nhóm không dùng: /nhom xoa Học tập\n"
              "• Chọn nhóm ngay khi ghi: đóng họ 1tr #trả nợ\n"
              "• Xếp các khoản đang ở Khác: /chuaxep")

def add_words(cfg, code, words):
    """Thêm từ khóa cho một nhóm; từ khóa đó có ở nhóm tự chỉnh khác thì chuyển sang nhóm này,
    cụm từ đã học trùng hẳn từ khóa đó (học từ lần sửa cũ) thì bỏ để từ khóa mới có tác dụng."""
    if words:
        learned = groups_repo.learned()
        kept = {k: c for k, c in learned.items() if k not in words or c == code}
        if len(kept) != len(learned):
            groups_repo.save_learned(kept)
    cfg.setdefault("tu", {})
    for other, own in cfg["tu"].items():
        if other != code:
            own[:] = [w for w in own if w not in words]
    cfg["tu"][code] = list(dict.fromkeys(cfg["tu"].get(code, []) + words))[-MAX_WORDS:]
    cfg["tu"] = {c: w for c, w in cfg["tu"].items() if w}

def after_change(cfg, text):
    save_config(cfg)
    moved = ledger.tidy(today())
    return text + (f"\n↪️ Đã xếp lại {moved} khoản đang ở Khác theo nhóm mới" if moved else "")

def nhom_them(rest):
    head, words = labels.split_spec(rest)
    cfg = json.loads(json.dumps(config()))  # bản sao để sửa
    label = labels.make_label(head) if head else None
    code = find_group(head, include_hidden=True, cfg=cfg) if label else None
    if code and plain(bare(name(code, cfg))) != plain(bare(label)):
        code = None  # chỉ khớp một phần tên ("Ăn" với "Ăn uống"): tạo nhóm mới
    if code:
        was_hidden = code in cfg.get("an", [])
        cfg["an"] = [c for c in cfg.get("an", []) if c != code]
        add_words(cfg, code, words)
        text = (f"✅ Đã dùng lại nhóm {name(code, cfg)}" if was_hidden else f"Nhóm {name(code, cfg)} đã có")
        return after_change(cfg, text + (f", thêm từ khóa: {html.escape(', '.join(words))}" if words else ""))
    if not label:
        return NHOM_USAGE
    if len(cfg.get("moi", [])) >= MAX_GROUPS:
        return f"Đã có {MAX_GROUPS} nhóm tự tạo, ẩn bớt nhóm không dùng (/nhom xoa tên nhóm) rồi tạo tiếp"
    cfg["dem"] = cfg.get("dem", 0) + 1
    code = f"r{cfg['dem']}"
    cfg.setdefault("moi", []).append(code)
    cfg.setdefault("ten", {})[code] = label
    add_words(cfg, code, words)
    text = f"✅ Đã tạo nhóm {html.escape(label)}" + (
        f", từ khóa: {html.escape(', '.join(words))}" if words else
        f"\nThêm từ khóa để bot tự xếp: /nhom tukhoa {html.escape(bare(label))}: từ khóa 1, từ khóa 2")
    return after_change(cfg, text)

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

def nhom_cmd(args):
    action = plain(args[0]) if args else ""
    rest = " ".join(args[1:])
    for words, handler in [(("them", "tao", "moi"), nhom_them), (("tukhoa", "tu", "tk"), nhom_tukhoa),
                           (("doiten", "ten", "sua"), nhom_doiten), (("xoa",), nhom_xoa)]:
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
