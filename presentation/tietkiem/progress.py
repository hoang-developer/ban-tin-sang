"""Tiết kiệm từ khi dùng bot: dựng tin Telegram (HTML) và nút từ kết quả của service. Không logic nghiệp vụ, không đọc kho."""
from datetime import timedelta

from domain.common.format import short as format_short
from presentation.chitieu.view import BACK

USAGE = ("💚 /tietkiem: chi lặt vặt so với trước khi dùng bot, chuỗi ngày ghi chép, đã để dành thật\n"
         "/tietkiem khongtieu: hôm nay không tiêu gì (giữ chuỗi; ghi bù hôm qua: /tietkiem khongtieu hôm qua)\n"
         "/tietkiem moc 300k: đổi mốc chi lặt vặt mỗi ngày · /tietkiem batdau 04/11: ngày bắt đầu tính\n"
         "/tietkiem nhac tat (hoặc bat): nhắc 21h khi hôm đó chưa ghi gì")


def money(x):
    return format_short(x) if abs(x) >= 1000 else "0đ"


def saved_text(x):
    return f"đã bớt ~{money(x)}" if x >= 0 else f"đang chi hơn mốc {money(-x)}"


def milestone_lines(m, p):
    """Các dòng 🎉 cho mốc vừa đạt (m: Milestones)."""
    out = [f"🎉 Ghi chép {n} ngày liên tiếp! Kỷ lục: {p.best} ngày" for n in m.streak]
    out += [f"🎉 Từ {p.start:%d/%m} đã chi lặt vặt ít hơn trước {money(mark)}! Chuyển vào quỹ để thành "
            "tiền để dành thật: /tietkiem" for mark in m.saved]
    return out


def after_record_lines(p, m, brief=False):
    """Dòng thêm dưới tin "Đã ghi": chuỗi, hôm nay so với mốc, đã bớt; kèm chúc mừng khi chạm mốc.
    brief: tin đã có dòng "hôm nay còn được tiêu" (con số chung) nên không hiện thêm mốc mỗi ngày cho đỡ rối."""
    line = (f"🔥 {p.streak} ngày" + ("" if brief else f" · hôm nay {money(p.spent_today)}/{money(p.base)}")
            + (f" · từ {p.start:%d/%m} {saved_text(p.saved)}" if p.days else ""))
    return [line] + milestone_lines(m, p)


def home_line(p):
    """Dòng màn hình tổng quan (/menu)."""
    return (f"💚 Từ {p.start:%d/%m} {saved_text(p.saved)}"
            + (f" · để dành thật {money(p.real_total)}" if p.real_total else "") + f" · 🔥 {p.streak} ngày")


def buttons(p, day, invest_fund=None):
    rows = []
    quick = []
    if not p.today_logged:
        quick.append(("🙅 Hôm nay không tiêu", f"tk:khong:{day.isoformat()}"))
    yesterday = day - timedelta(days=1)
    if not p.yesterday_logged and yesterday >= p.start:
        quick.append(("↩️ Hôm qua không tiêu", f"tk:khong:{yesterday.isoformat()}"))
    if quick:
        rows.append(quick)
    if p.movable:
        move = []
        if invest_fund:
            move.append((f"📈 {money(p.movable)} → quỹ chờ {invest_fund}", f"tk:chuyen:dt:{p.movable}"))
        move.append((f"🛟 {money(p.movable)} → quỹ dự phòng", f"tk:chuyen:dp:{p.movable}"))
        rows.append(move)
    rows.append([("🔄 Cập nhật", "tk:xem"), BACK])
    return rows


def view_text(p, day, invest_fund=None):
    """(tin, nút) của màn hình /tietkiem. invest_fund: mã quỹ chờ đang bật (hiện nút chuyển vào quỹ chờ), hoặc None."""
    base, start = p.base, p.start
    lines = [f"💚 <b>Tiết kiệm từ {start:%d/%m/%Y}</b> · mốc chi lặt vặt <b>{money(base)}/ngày</b>"]
    if p.days:
        diff = (p.avg - base) / base * 100 if base else 0
        lines.append(f"{'🟢' if p.saved >= 0 else '🔴'} <b>{saved_text(p.saved).capitalize()}</b> · "
                     f"{p.days} ngày, TB {money(p.avg)}/ngày ({diff:+.0f}%)")
        if p.month_days and p.month_days != p.days:
            lines.append(f"   Tháng {day.month}: {saved_text(p.month_saved)} ({p.month_days} ngày)")
    else:
        lines.append("Chưa có ngày nào trọn vẹn: hết ngày bot mới cộng số đã bớt")
    today_mark = "⬜" if not p.today_logged else "🟢" if p.spent_today <= base else "🔴"
    lines.append(f"{today_mark} Hôm nay {money(p.spent_today)}/{money(base)}")
    lines.append(f"🔥 {p.streak} ngày · 🏆 kỷ lục {p.best} · ghi {p.days}/{p.elapsed} ngày")
    if p.weeks:
        lines.append("📅 " + " · ".join(f"{m:%d/%m} {money(avg)}/ngày" for m, avg, _ in p.weeks))
    r = p.real
    parts = [f"{label} {money(r[k])}" for k, label in (("duphong", "quỹ dự phòng"), ("dautu", "góp đầu tư"),
                                                       ("tra_no", "trả nợ")) if r[k]]
    lines.append(f"✅ <b>Để dành thật {money(p.real_total)}</b>" + (f" ({' · '.join(parts)})" if parts else ""))
    if p.movable:
        lines.append(f"💡 {money(p.movable)} đã bớt chưa chuyển đi")
    return "\n".join(lines), buttons(p, day, invest_fund)


def no_spend_text(r):
    if r.status == "ngoai_pham_vi":
        return "Chỉ đánh dấu được hôm nay hoặc hôm qua"
    if r.status == "da_co_chi":
        return f"{r.when.capitalize()} đã có khoản chi, ngày đó đã được tính rồi"
    return "\n".join([f"✅ Đã ghi {r.when} không tiêu gì · 🔥 {r.progress.streak} ngày"]
                     + milestone_lines(r.milestones, r.progress))


def reminder_view(p, day):
    """(tin nhắc 21h, nút) khi hôm nay chưa ghi gì."""
    goal = (f"giữ chuỗi 🔥 {p.streak} ngày" if p.streak else "bắt đầu chuỗi ngày ghi chép mới") + (
        f" · tháng này {saved_text(p.month_saved)}" if p.month_days else "")
    text = f"📝 Hôm nay chưa ghi khoản chi nào: ghi nốt để {goal}"
    return text, [[("🙅 Hôm nay không tiêu", f"tk:khong:{day.isoformat()}"), ("💚 Tiết kiệm", "tk:xem")]]


def period_text(info):
    """Dòng thêm vào tổng kết tuần/tháng: số đã bớt trong kỳ và cộng dồn."""
    p = info.progress
    head = (f"Tuần này {saved_text(info.week_saved)} so với trước ({info.week_days} ngày có ghi)"
            if info.week_saved is not None else None)
    return "💚 " + " · ".join(x for x in (head, f"từ {p.start:%d/%m} {saved_text(p.saved)}", f"🔥 {p.streak} ngày") if x)


def invest_move_note(m, amount):
    """Câu báo sau khi chuyển phần đã bớt vào quỹ chờ đầu tư."""
    return f"Đã chuyển {money(amount)} vào quỹ chờ {m.fund} ({money(m.left)})" + "".join(f" · {x[2:]}" for x in m.notes)
