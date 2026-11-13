"""Gộp thông báo của bot chi tiêu: mỗi buổi một tin thay vì nhiều tin rời.

- ☀️ Sáng (từ 9h, lich.tai_chinh_sang): đã nhận lương chưa, sổ tiết kiệm sắp đáo hạn, khoản nợ tới hạn chưa trả.
- 🌙 Tối (từ 21h, lich.tong_ket_toi): hôm nay chưa ghi gì thì nhắc (kèm nút "không tiêu"), nhóm tiêu tăng vọt hay sắp vượt
  ngân sách, lãi/lỗ các quỹ ngày có NAV mới. Không có gì đáng nói thì không gửi.
Tin theo sự kiện vẫn gửi riêng vì cần làm ngay: nhắc hạn đặt lệnh quỹ (8:30, 13:00), lệnh quỹ vừa khớp (sau 17h).
"""
import sys

import sochitieu as ct


def part(name, make):
    try:
        return make()
    except Exception as e:
        print(f"[lỗi] thông báo, phần {name}: {e!r}", file=sys.stderr)
        return None


def join(title, parts):
    """[(chữ, hàng nút)] -> một tin (chữ, nút); None nếu không có phần nào."""
    parts = [p for p in parts if p and p[0]]
    if not parts:
        return None
    text = title + "\n" + "\n\n".join(p[0] for p in parts)
    rows = [row for p in parts for row in (p[1] or [])]
    return text, rows


def morning(day):
    """Tin sáng gộp; None nếu không có gì cần nhắc."""
    ts, sono = ct.taisan(), ct.sono()
    salary = part("nhắc lương", lambda: ts.salary_due(day))
    notes = part("đáo hạn", lambda: ts.maturity_notes(day)) or []
    debts = part("nhắc nợ", lambda: sono.reminders(day))
    parts = [salary, ("\n".join(notes), [[("💰 Tiền của tôi", "m:tien")]]) if notes else None, debts]
    return join(f"☀️ <b>Sáng {day:%d/%m}</b>", parts)


def evening(now):
    """Tin tối gộp; None nếu không có gì đáng nói."""
    day = now.date()
    pt = ct.phantich()
    remind = part("nhắc ghi chép", lambda: ct.tietkiem().reminder(day))
    alerts = part("để ý chi tiêu", lambda: pt.alerts(day)) or []
    fund = part("lãi lỗ quỹ", lambda: ct.dautu().daily_report(now))
    parts = [remind]
    if alerts:
        parts.append(("👀 <b>Để ý</b>\n" + "\n".join(alerts), [[("🔮 Dự báo", "db"), ("💬 Nhận xét", "nx:thang")]]))
    if fund:  # tiêu đề tin đã có ngày: bỏ ngày lặp trong phần quỹ
        parts.append((fund[0].replace(f"Quỹ tối {day:%d/%m}", "Quỹ"), fund[1]))
    if not remind and (alerts or fund):  # đã ghi hôm nay: thêm một dòng hôm nay tiêu thế nào
        today = part("hôm nay", lambda: today_line(day))
        if today:
            parts.insert(0, (today, None))
    return join(f"🌙 <b>Tối {day:%d/%m}</b>", parts)


def today_line(day):
    """'💸 Hôm nay chi 85k · trong mức (dư 246k)' theo con số mỗi ngày được tiêu."""
    import kehoach
    group = ct.sono().debt_group()[0]
    spent = sum(e["tien"] for e in ct.load(day.strftime("%Y-%m")) if e["ngay"] == day.isoformat()
                and e["nhom"] not in (ct.INCOME, group) and not e.get("no"))
    s = kehoach.spendable_safe(day)
    if not s or s["per_day"] <= 0:
        return f"💸 Hôm nay chi {kehoach.short(spent)}"
    if s["today_left"] >= 0:
        return f"💸 Hôm nay chi {kehoach.short(spent)} · trong mức, dư {kehoach.short(s['today_left'])}"
    return f"💸 Hôm nay chi {kehoach.short(spent)} · quá mức mỗi ngày {kehoach.short(-s['today_left'])}"
