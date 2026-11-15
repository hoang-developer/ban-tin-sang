"""Quỹ dự phòng: dựng tin Telegram (HTML) và nút từ kết quả của service. Không logic nghiệp vụ, không đọc kho."""
import html
import math

from domain.common.format import short as format_short
import sochitieu as ct  # module cũ ở gốc: nút ⬅ Về
from domain.taisan import text as taisan_text
from domain.common.format import vn_num
from domain.duphong.reserve import DEADLINE_CHOICES, MIN_DAYS, MONTHS_CHOICES


def bar(ratio, width=10):
    full = max(0, min(width, round(ratio * width)))
    return "▓" * full + "░" * (width - full)


def money(x):
    return format_short(x) if x >= 1000 else "0đ"


def buttons(s):
    rows = [[(f"➕ {money(a)}", f"dp:nap:{a}") for a in (1_000_000, 2_000_000, 5_000_000)]]
    if s.per_month >= 100_000:
        rows[0].insert(0, (f"➕ {money(round(s.per_month, -5))}", f"dp:nap:{int(round(s.per_month, -5))}"))
    rows.append([(f"{'🎯' if s.months == m else ''}{m} tháng", f"dp:thang:{m}") for m in MONTHS_CHOICES])
    rows.append([(f"{'⏳' if s.deadline_months == m else ''}đạt trong {m}t", f"dp:han:{m}") for m in DEADLINE_CHOICES])
    rows.append([("🏦 Để quỹ ở đâu?", "dp:noi"), ct.BACK])
    return rows


def status_view(s):
    """(tin, nút) của màn hình quỹ dự phòng."""
    if not s.monthly:
        return ("🛟 <b>Quỹ dự phòng</b>\n"
                f"📒 {s.days}/{MIN_DAYS} ngày ghi chép để tự tính chi thiết yếu mỗi tháng. "
                "Tự đặt luôn: /duphong chi 12tr (ăn, đi lại, nhà, điện nước, trả nợ…)"), None
    ratio = s.balance / s.target if s.target else 0
    lines = [f"🛟 <b>Quỹ dự phòng {money(s.balance)}/{money(s.target)}</b> · {s.months} tháng chi",
             f"{bar(ratio)} {ratio * 100:.0f}% · đủ {vn_num(s.covered, 1)} tháng"]
    if s.covered < 1:
        lines.append(f"🚩 Mốc 1 tháng ({money(s.monthly)}): thiếu {money(s.monthly - s.balance)}")
    elif s.covered < 3 <= s.months:
        lines.append(f"✅ Mốc 1 tháng · 🚩 tiếp: 3 tháng ({money(3 * s.monthly)})")
    basis = "tự đặt" if s.manual else f"{s.days} ngày qua"
    parts = " · ".join(f"{s.group_labels[c].split()[0]} {money(v)}" for c, v in list(s.by_group.items())[:6])
    lines.append(f"🧾 Chi thiết yếu <b>{money(s.monthly)}/tháng</b> ({basis})" + (f"\n   {parts}" if parts and not s.manual else ""))
    if s.missing:
        plan = (f"📅 <b>{money(s.per_month)}/tháng</b> để đủ trước {s.deadline:%m/%Y}"
                if not s.overdue else f"🔴 Quá hạn {s.deadline:%m/%Y}: chọn hạn mới bên dưới")
        lines.append(plan)
        if s.surplus is not None:
            if s.surplus <= 0:
                lines.append(f"🔴 3 tháng qua chi > thu {money(-s.surplus)}/tháng")
            else:
                share = s.per_month / s.surplus * 100
                lines.append(f"💰 Dư TB {money(s.surplus)}/tháng · mức trên = {share:.0f}%"
                             + (" 🟢" if share <= 70 else
                                f" 🟡 · để 70% ({money(0.7 * s.surplus)}) thì ~"
                                f"{math.ceil(s.missing / (0.7 * s.surplus))} tháng"))
    else:
        lines.append("🎉 Quỹ dự phòng đã đủ!")
    if s.rows and s.has_other_funds:  # có sổ, quỹ khác tính vào quỹ
        lines.append("🏦 " + " · ".join(f"{html.escape(n)} {money(v)}" for n, v in s.rows))
    else:
        lines.append("<i>Chưa có tiền trong quỹ: bấm ➕ hoặc nhắn «nạp 2tr vào quỹ dự phòng»</i>")
    return "\n".join(lines), buttons(s)


def change_note(c):
    """Câu báo sau khi nạp/rút (dòng đầu: kết quả, các dòng sau: chúc mừng mốc, tiền đi/về tài khoản chính)."""
    after = c.after
    if c.amount >= 0:
        note = f"✅ +{money(c.amount)} quỹ dự phòng: {money(after.balance)}" + (f"/{money(after.target)}" if after.target else "")
        if c.milestone:
            note += f"\n🎉 Chúc mừng: quỹ đã {c.milestone}!"
    else:
        note = f"✅ −{money(-c.amount)} quỹ dự phòng: còn {money(after.balance)}"
    return note + (f"\n{c.moved}" if c.moved else "")


def toggle_text(t):
    if not t.found:
        return ("Không thấy tài sản tên «" + html.escape(t.name) + "» trong /taisan. Có: "
                + html.escape(", ".join(t.available) or "chưa có tài khoản, sổ tiết kiệm nào"))
    return (f"✅ Đã tính «{html.escape(t.label)}» vào quỹ dự phòng" if t.enabled
            else f"Đã bỏ «{html.escape(t.label)}» khỏi quỹ dự phòng") + "\nXem: /duphong"


def where_text(books):
    """books: [(tên sổ, lãi %/năm, đã tính vào quỹ)]."""
    lines = ["🏦 <b>Để quỹ dự phòng ở đâu</b>",
             "Cần: rút được ngay hoặc trong vài ngày, không mất vốn, lãi là phụ.",
             "• Tiết kiệm không kỳ hạn, hoặc tiết kiệm online kỳ hạn 1–3 tháng: rút trước hạn chỉ mất lãi, không mất "
             "gốc; nên chia vài sổ nhỏ để cần bao nhiêu rút bấy nhiêu",
             "• Có thể để 1 tháng chi ở tài khoản thanh toán, phần còn lại gửi tiết kiệm"]
    if books:
        lines.append("   Sổ của bạn: " + " · ".join(
            f"{html.escape(name)} {taisan_text.qty_text(rate)}%" + (" ✅" if in_fund else "") for name, rate, in_fund in books))
    lines.append("• Không để quỹ dự phòng ở cổ phiếu, ETF, vàng (giá lên xuống, lúc cần có thể đang lỗ); các khoản này "
                 "dành cho bước đầu tư sau khi quỹ đủ")
    lines.append("Tính sổ tiết kiệm có sẵn vào quỹ dự phòng: /duphong tinh <tên sổ>")
    return "\n".join(lines)
