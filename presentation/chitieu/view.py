"""Màn hình sổ chi tiêu: tin báo các khoản vừa ghi, nút chọn nhóm, báo cáo một kỳ. Chữ và nút dựng từ số liệu đã tính;
cfg là cấu hình nhóm tự chỉnh của người dùng."""
import html
from datetime import timedelta

from domain.chitieu import classify
from domain.chitieu.income import income_kinds
from domain.chitieu.kinds import INCOME
from domain.chitieu.learn import pending
from domain.chitieu.refs import button_ref, ref
from domain.chitieu.text import short
from domain.common.format import vnd

SORT_TITLE = "🗂"  # tin /chuaxep bắt đầu bằng biểu tượng này, vẽ lại vẫn giữ kiểu tin

BACK = ("⬅️ Hôm nay", "m:home")  # nút quay về màn hình 🏠 Hôm nay (menu.py)
REPORT_BUTTONS = [[("Hôm nay", "bc:ngay"), ("Tuần này", "bc:tuan"), ("Tháng này", "bc:thang"),
                   ("Tháng trước", "bc:thangtruoc")],
                  [("📈 Biểu đồ", "bd:thang"), ("🔮 Dự báo", "db"), ("💬 Nhận xét", "nx:thang")]]
CHI_BUTTONS = REPORT_BUTTONS + [[("🧾 Lịch sử", "m:ls"), ("🗂 Chưa xếp", "m:cx"), ("🎯 Ngân sách", "m:ns")], [BACK]]

def entry_text(e, day, cfg):
    when = "" if e["ngay"] == day.isoformat() else (
        " · hôm qua" if e["ngay"] == (day - timedelta(days=1)).isoformat() else f" · {e['ngay'][8:]}/{e['ngay'][5:7]}")
    note = html.escape(e["ghichu"]) if e["ghichu"] else "<i>không ghi chú</i>"
    robot = " ✨" if e.get("ai") else ""  # ✨ nhóm do AI đoán
    return f"<b>{vnd(e['tien'])}</b> · {classify.name(e['nhom'], cfg)}{robot} — {note}{when}"

def budget_label(code, cfg):
    return {"tong": "Tổng chi", "hangngay": "Chi hằng ngày"}.get(code) or classify.name(code, cfg)

def budget_lines(progress, cfg):
    """Dòng tiến độ ngân sách từ [(mã, đã chi, hạn mức)]."""
    lines = []
    for code, spent, limit in progress:
        pct = spent / limit * 100
        label = budget_label(code, cfg)
        mark = "🔴" if pct >= 100 else "🟡" if pct >= 80 else "🟢"
        extra = f" · vượt {short(spent - limit)}" if pct > 100 else ""
        lines.append(f"{mark} {label}: {short(spent)}/{short(limit)} ({pct:.0f}%{extra})")
    return lines

def entries_message(entries, day, cfg, budget_notes, sorting=False, focus=None, extra=()):
    """Tin báo các khoản vừa ghi, kèm nút ✏️ đổi nhóm và ❌ xóa từng khoản. Khoản chưa rõ nhóm (Khác)
    thì hiện luôn nút chọn nhóm, từng khoản một, để ít khoản phải nằm ở Khác. focus: khoản vừa bấm ✏️."""
    if not entries:
        return "🗑 Đã xóa", None
    ask = next((e for e in entries if ref(e) == focus), None) or next((e for e in entries if pending(e)), None)
    notes = [] if sorting else list(budget_notes)
    for tag in dict.fromkeys(e["_tag"] for e in entries if e.get("_tag")):
        notes.append(f"⚠️ Chưa có nhóm «{html.escape(tag)}»: /nhom them {html.escape(tag)}")
    what = html.escape((ask["ghichu"] or vnd(ask["tien"])) if ask else "")
    if ask and pending(ask):
        notes.append(f"❓ «{what}» thuộc nhóm nào?")
    elif ask:
        notes.append(f"✏️ Chọn nhóm đúng cho «{what}»")
    notes += list(extra)
    if sorting:
        left = sum(pending(e) for e in entries)
        lines = [f"{SORT_TITLE} <b>{'Còn ' + str(left) + ' khoản chưa rõ nhóm' if left else 'Đã xếp xong'}</b>"]
        lines += [f"{i}. {entry_text(e, day, cfg)}" for i, e in enumerate(entries, 1)]
        rows = [[(f"✏️ {i}. {e['ghichu'][:12] or vnd(e['tien'])}", f"doi:{ref(e)}"), (f"❌ {i}", f"xoa:{ref(e)}")]
                for i, e in enumerate(entries, 1)]
    elif len(entries) == 1:
        e = entries[0]
        lines = [f"✅ Đã ghi {entry_text(e, day, cfg)}"]
        rows = [[("✏️ Đổi nhóm", f"doi:{ref(e)}"), ("❌ Xóa", f"xoa:{ref(e)}")]]
    else:
        total = sum(e["tien"] for e in entries if e["nhom"] != INCOME)
        lines = [f"✅ Đã ghi {len(entries)} khoản" + (f", chi <b>{vnd(total)}</b>" if total else "")]
        lines += [f"{i}. {entry_text(e, day, cfg)}" for i, e in enumerate(entries, 1)]
        rows = [[(f"✏️ {i}. {e['ghichu'][:12] or vnd(e['tien'])}", f"doi:{ref(e)}"), (f"❌ {i}", f"xoa:{ref(e)}")]
                for i, e in enumerate(entries, 1)]
    if ask:
        rows = with_picker(rows, ref(ask), cfg, "📦 Để ở Khác" if pending(ask) else "↩️ Thôi")
    return "\n".join(lines + notes), rows

def picker(reference, cfg, keep="↩️ Thôi"):
    """Nút chọn nhóm cho một khoản: mọi nhóm đang dùng (kể cả nhóm tự tạo), rồi nút giữ nguyên/xóa."""
    choices = [(label, f"nhom:{reference}:{code}") for code, (label, _, _) in classify.groups(cfg).items()]
    rows = [choices[i:i + 2] for i in range(0, len(choices), 2)]
    return rows + [[(keep, f"giu:{reference}"), ("❌ Xóa", f"xoa:{reference}")]]

def with_picker(rows, reference, cfg, keep="↩️ Thôi"):
    """Thay hàng nút của một khoản bằng nút chọn nhóm, ngay tại chỗ; nút của khoản khác giữ nguyên."""
    out, done = [], False
    for row in rows:
        if any(button_ref(data) == reference for _, data in row):
            if not done:
                out += picker(reference, cfg, keep)
                done = True
        else:
            out.append(row)
    return out if done else picker(reference, cfg, keep) + rows

def report_text(data, cfg):
    """(nội dung báo cáo, số khoản chi) của một kỳ từ số liệu của services.chitieu.report."""
    start, end, label, prev_start, prev_end, prev_label = data["period"]
    items = data["items"]
    spend = [e for e in items if e["nhom"] != INCOME]
    income = sum(e["tien"] for e in items if e["nhom"] == INCOME)
    total = sum(e["tien"] for e in spend)
    span = f"{start:%d/%m}" + (f" – {end:%d/%m}" if end != start else "")
    lines = [f"📊 <b>Chi tiêu {label}</b> ({span})"]
    if not items:
        return "\n".join(lines + ["Chưa có khoản nào. Nhắn kiểu: cà phê 35k"]), 0
    days = (end - start).days + 1
    lines.append(f"💸 Chi <b>{vnd(total)}</b> · {len(spend)} khoản" + (f" · ~{short(total / days)}/ngày" if days > 1 else ""))
    by_cat = {}
    for e in spend:
        by_cat[e["nhom"]] = by_cat.get(e["nhom"], 0) + e["tien"]
    top = max(by_cat.values(), default=0)
    for code, amount in sorted(by_cat.items(), key=lambda x: -x[1]):
        lines.append(f"{classify.name(code, cfg)} <b>{short(amount)}</b> · {amount / total * 100:.0f}%\n"
                     + "▇" * max(1, round(amount / top * 10)))
    prev_total = data["prev_total"]
    if prev_total:
        change = (total - prev_total) / prev_total * 100
        lines.append(f"{'🔺' if change >= 0 else '🔻'}{abs(change):.0f}% so với {prev_label} ({short(prev_total)})")
    if income:
        kinds = income_kinds([e for e in items if e["nhom"] == INCOME])
        detail = f" ({' · '.join(f'{k} {short(v)}' for k, v in kinds)})" if len(kinds) > 1 else ""
        left = income - total
        lines.append(f"💰 Thu {short(income)}{detail} → {'🟢' if left >= 0 else '🔴'} còn <b>{short(left)}</b>")
    biggest = sorted(spend, key=lambda e: -e["tien"])[:3]
    if biggest and len(spend) > 3:
        lines.append("🏆 " + " · ".join(f"{html.escape(e['ghichu'] or classify.name(e['nhom'], cfg))} {short(e['tien'])}"
                                       for e in biggest))
    unsorted = sum(pending(e) for e in spend)
    if unsorted:
        lines.append(f"❓ {unsorted} khoản chưa rõ nhóm: /chuaxep")
    status = budget_lines(data["budget"], cfg)
    if status:
        lines += ["", "<b>🎯 Ngân sách</b>"] + status
    return "\n".join(lines), len(spend)
