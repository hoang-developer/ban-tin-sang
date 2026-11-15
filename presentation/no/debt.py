"""Sổ nợ: dựng tin Telegram (HTML) và nút từ kết quả của service. Không logic nghiệp vụ, không đọc kho."""
import html

from domain.common.format import short as format_short
import sochitieu as ct  # module cũ ở gốc: nút ⬅ Về
from domain.taisan import text as taisan_text
from domain.no.debt import Ask, month_left, month_of, paid_in, schedule, ym_text

USAGE = ("💳 <b>Sổ nợ</b>\n"
         "• Thêm: /no chú Tư 300tr đã trả 32tr, trả 5tr/tháng, không lãi\n"
         "• Trả góp: /no thẻ tín dụng trả góp 8,2tr, trả 4,39tr/tháng, ngày 5\n"
         "  (có lãi thì ghi: lãi 12%; ngày 5 là hạn trả hằng tháng)\n"
         "• Sửa: gõ lại cùng tên với thông tin mới, ví dụ /no chú Tư trả 6tr/tháng\n"
         "• Trả nợ: bấm ✅ Trả trong /no, nhắn «trả nợ chú Tư 5tr», hoặc gửi ảnh chuyển khoản: bot tự trừ dư nợ\n"
         "• Xóa khoản nợ: /no xoa")


def short(x):
    return format_short(x) if x >= 1000 else "0đ"


def short_name(d, width=16):
    name = d["ten"]
    return name if len(name) <= width else name[:width - 1].rstrip() + "…"


def bar(ratio, width=10):
    full = max(0, min(width, round(ratio * width)))
    return "▓" * full + "░" * (width - full)


def interest_text(d):
    rate = d.get("lai")
    return "không lãi" if rate == 0 else "chưa rõ lãi" if rate is None else f"lãi {taisan_text.qty_text(rate)}%/năm"


def plan_line(d, day):
    s = schedule(d, day)
    if not s:
        return f"Chưa đặt mỗi tháng trả bao nhiêu: /no {html.escape(d['ten'])} trả 5tr/tháng"
    n, last = s
    return f"{short(d['thang'])}/tháng · xong ~{ym_text(last)} ({n} tháng)"


def month_status(d, day):
    ym = month_of(day)
    if not d.get("thang"):
        return ""
    if ym < d.get("tu", ym):
        return f"⏳ Kỳ trả đầu: tháng {ym_text(d['tu'])}"
    paid, left = paid_in(d, ym), month_left(d, ym)
    if not left:
        return f"✅ Tháng {day.month} đã trả {short(paid)}"
    due = f" · hạn ngày {d['ngay_tra']}" if d.get("ngay_tra") else ""
    return (f"🟡 Tháng {day.month} đã trả {short(paid)}, thiếu {short(left)}{due}" if paid
            else f"⬜ Tháng {day.month} chưa trả {short(left)}{due}")


def payment_lines(p):
    """Các dòng báo sau khi trừ một khoản trả vào dư nợ (p: Payment)."""
    name = html.escape(p.name)
    if p.finished:
        lines = [f"🎉 Đã trả xong nợ {name}!"]
        if p.monthly:
            lines.append(f"🔁 Từ tháng sau mỗi tháng dư ra {short(p.monthly)}: nên chuyển vào quỹ dự phòng (/kehoach)")
        return lines
    return [f"💳 Đã trừ vào nợ {name}: còn {short(p.left)}"
            + (f" · còn {p.schedule[0]} tháng, xong khoảng {ym_text(p.schedule[1])}" if p.schedule else "")]


def declare_text(r, day):
    """Câu báo sau khi khai báo/cập nhật khoản nợ (r: DeclareResult)."""
    if r.status == "thieu_con":
        return (f"Chưa có khoản nợ «{html.escape(r.name)}». Thêm kèm số còn nợ, ví dụ:\n"
                f"/no {html.escape(r.name)} 100tr, trả 5tr/tháng")
    d, created = r.debt, r.created
    total = f" / {short(d['goc'])}" if d.get("goc") and d["goc"] != d["tien"] else ""
    lines = [f"✅ {'Đã thêm' if created else 'Đã cập nhật'} khoản nợ <b>{html.escape(d['ten'])}</b>: còn "
             f"{short(d['tien'])}{total} · {interest_text(d)}", "   " + plan_line(d, day)]
    if d.get("thang"):
        first = max(d["tu"], month_of(day))
        lines.append(f"   Kỳ trả {'đầu' if created else 'tới'}: tháng {ym_text(first)}"
                     + (f", hạn ngày {d['ngay_tra']}" if d.get("ngay_tra") else ""))
    if d.get("lai") is None:
        lines.append("<i>Có lãi không? Nhắn thêm «không lãi» hoặc «lãi 12%»</i>")
    if r.group_note:
        lines.append(r.group_note)
    lines.append("Xem sổ nợ: /no")
    return "\n".join(lines)


def pay_lines(r):
    """Các dòng báo sau khi bấm ✅ Trả (r: PayResult)."""
    if r.status == "het_hoac_xoa":
        return ["Khoản nợ này đã trả xong hoặc đã xóa"]
    return payment_lines(r.payment) + ([r.group_note] if r.group_note else [])


def after_record_view(events):
    """(dòng thêm, hàng nút) dưới tin "Đã ghi" khi khoản vừa ghi là trả nợ (events: Paid/Ask)."""
    lines, rows = [], []
    for ev in events:
        if isinstance(ev, Ask):
            lines.append(f"💳 Khoản trả nợ {short(ev.entry['tien'])} này trừ vào khoản nợ nào?")
            rows.append([(short_name(d, 14), f"no:gan:{ev.ref}:{d['id']}") for d in ev.choices]
                        + [("Không trừ", f"no:kg:{ev.ref}")])
        else:
            lines += payment_lines(ev.payment)
            rows.append([(f"↩️ Không trừ vào nợ {short_name(ev.debt)}", f"no:bo:{ev.ref}")])
    return lines, rows


def view_view(state, day):
    """(tin, nút) của màn hình sổ nợ (state: ViewState)."""
    items, done = state.items, state.done
    back = [("🗂 Sửa, xóa", "no:ds"), ("➕ Thêm khoản nợ", "y:them:no_moi"), ct.BACK]
    if not items and not done:
        return ("💳 Chưa có khoản nợ nào. Bấm ➕ để thêm, hoặc nhắn câu thường, ví dụ: «vay anh Nam 10tr, mỗi tháng trả "
                "2tr, không lãi».", [[("➕ Thêm khoản nợ", "y:them:no_moi"), ct.BACK]])
    total, monthly = sum(d["tien"] for d in items), state.monthly
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
        lines.append(f"\n🔁 {ym_text(last)} xong {html.escape(d['ten'])}: dư {short(d['thang'])}/tháng")
    rows = [[(f"✅ Trả {short_name(d)} {short(left)}", f"no:tra:{d['id']}:{int(left)}")] for d, left in state.due]
    return "\n".join(lines), rows + [back]


def edit_list_view(items):
    if not items:
        return "Chưa có khoản nợ nào", [[("↩️ Sổ nợ", "no:xem")]]
    lines = ["🗂 <b>Bấm ❌ để xóa khoản nợ</b> (sửa: gõ lại /no cùng tên với thông tin mới)"]
    lines += [f"{i}. {html.escape(d['ten'])}: còn {short(d['tien'])}" for i, d in enumerate(items, 1)]
    buttons = [(f"❌ {i}", f"no:x:{d['id']}") for i, d in enumerate(items, 1)]
    return "\n".join(lines), [buttons[i:i + 5] for i in range(0, len(buttons), 5)] + [[("↩️ Sổ nợ", "no:xem")]]


def home_line(items, paid, need, day):
    """Một dòng cho màn hình tổng quan (items: các khoản nợ còn dư; paid/need: đã trả/cần trả tháng này)."""
    line = f"💳 Nợ còn <b>{short(sum(d['tien'] for d in items))}</b>"
    if need:
        line += f" · tháng {day.month} đã trả {short(paid)}/{short(need)}"
    elif any(d.get("thang") for d in items):
        line += " · kỳ trả đầu tháng sau"
    return line


def reminders_view(due, day):
    """(tin nhắc trả nợ, nút) cho các khoản đến hạn chưa trả đủ (due: [(khoản nợ, còn phải trả)])."""
    lines = [f"💳 <b>Nhắc trả nợ tháng {day.month}</b>"]
    lines += [f"• {html.escape(d['ten'])}: {short(left)}" + (f" (hạn ngày {d['ngay_tra']})" if d.get("ngay_tra") else "")
              for d, left in due]
    rows = [[(f"✅ Đã trả {short_name(d)} {short(left)}", f"no:tra:{d['id']}:{int(left)}")] for d, left in due]
    return "\n".join(lines), rows + [[("💳 Sổ nợ", "no:xem")]]


def health_line(h):
    """(điểm 0–20, dấu, dòng) cho khám sức khỏe tài chính (h: DebtHealth)."""
    if h.none:
        return 20, "✅", "Nợ: không có"
    parts = []
    if h.basis == "thu":
        parts.append(f"trả {short(h.monthly)}/tháng = {h.share:.0f}% thu (nên < 30%)")
    elif h.owed:
        parts.append(f"nợ có lãi = {h.ratio:.0f}% tài sản (nên < 30%)")
    if h.has_bearing:
        parts.append(f"nợ có lãi {short(h.bearing_total)}" + (f" · xong ~{ym_text(h.bearing_last)}" if h.bearing_last else ""))
    if h.has_zero:
        parts.append(f"nợ không lãi {short(h.zero_total)}")
    if h.late:
        parts.append("⬜ tháng này: " + ", ".join(html.escape(n) for n in h.late))
    return h.score, h.mark, "Nợ: " + " · ".join(parts)
