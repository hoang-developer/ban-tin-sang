"""Đối chiếu tài sản tháng: dựng tin Telegram (HTML) và nút từ kết quả của service. Không logic nghiệp vụ, không đọc kho."""
import html

from presentation.chitieu.view import BACK
from domain.taisan import text as taisan_text
from domain.doichieu.reconcile import UNITS, color, total_gap

NEED_RECONCILE_ROWS = [[("🔄 Đối chiếu", "dc:xem")]]


def short(x):
    return taisan_text.short(x) if abs(x) >= 1000 else f"{round(x)}đ"


def qty(x):
    return taisan_text.qty_text(round(x, 4))


def name(it):
    label = it.get("ten") or it.get("ma", "").upper()
    return html.escape(label) + (" (chính)" if it.get("chinh") else "") + (" 💳" if it["loai"] == "no" else "")


def amount_text(value, unit):
    return short(value) if unit == "đ" else f"{qty(value)} {unit}"


def screen_rows():
    return [[("🔄 Tiếp tục đối chiếu", "dc:xem")]]


def screen_view(day, state):
    """(tin, nút) của màn hình đối chiếu tháng: mỗi ngăn một dòng và một hàng nút."""
    if not state.entries:
        return ("🔄 Chưa có tài sản nào để đối chiếu. Nhắn kiểu «tài khoản VCB còn 30tr».",
                [[("➕ Thêm", "y:them"), BACK]])
    lines = [f"🔄 <b>Đối chiếu tài sản {day.month}/{day.year}</b>",
             "<i>Mở app ngân hàng, Fmarket… so từng dòng: khớp bấm ✅, lệch bấm ✏️ rồi nhắn số thật</i>"]
    rows, left = [], 0
    for (it, value, unit), rec, pending in state.entries:
        rid = str(it["id"])
        if rec:
            mark = "✅" if not rec["lech"] else (color(rec["lech"], rec.get("no")) + (" +" if rec["lech"] > 0 else " −")
                                                + amount_text(abs(rec["lech"]), rec["don_vi"]))
            lines.append(f"{mark} {name(it)}: {amount_text(rec['that'], unit)}")
            continue
        left += 1
        if pending:
            lines.append(f"⏳ {name(it)}: {amount_text(value, unit)} · còn lệnh chờ khớp, đối chiếu sau")
            continue
        lines.append(f"⬜ {name(it)}: bot tính {amount_text(value, unit)}")
        rows.append([(f"✏️ {(it.get('ten') or it.get('ma', '')).upper() if it['loai'] in UNITS else it.get('ten')}"[:28],
                      f"y:them:{'doi_chieu_sl' if unit != 'đ' else 'doi_chieu'}:{rid}"), ("✅ Khớp", f"dc:ok:{rid}")])
    total = total_gap(state.done)
    if state.done:
        lines.append(f"\nΣ lệch tiền: {('🟢 +' if total >= 0 else '🔴 −') + short(abs(total)) if total else '✅ 0đ'}"
                     + (f" · còn {left} ngăn" if left else " · 🎉 xong"))
    if left > 1:
        rows.append([("✅ Khớp hết phần còn lại", "dc:het")])
    return "\n".join(lines), rows + [[("💰 Tiền của tôi", "m:tien"), BACK]]


def set_value_view(r):
    """(câu báo, nút) sau khi ghi số thật của một ngăn."""
    if r.status == "khong_con":
        return "Ngăn này không còn trong tài sản", NEED_RECONCILE_ROWS
    if r.status == "cho_khop":
        return f"⏳ {name(r.item)} còn lệnh chờ khớp: khớp xong bot tự cộng ccq, đối chiếu sau nhé", NEED_RECONCILE_ROWS
    if r.status == "so_am":
        return "Số lượng không âm nhé", NEED_RECONCILE_ROWS
    head = f"{name(r.item)}: bot {amount_text(r.bot_value, r.unit)} → thật {amount_text(r.real, r.unit)}"
    if r.status == "khop":
        return f"✅ {head} · khớp", screen_rows()
    note = (f"{color(r.gap, r.item['loai'] == 'no')} {head} · lệch "
            f"{'+' if r.gap > 0 else '−'}{amount_text(abs(r.gap), r.unit)}")
    if r.item.get("chinh"):
        if r.gap < 0:  # số thật thấp hơn: thường là khoản chi quên ghi
            label = f"🧾 Ghi {short(-r.gap)} là chi chưa ghi"
            return note, [[(label, f"dc:ghi:{r.item['id']}"), ("Chỉ sửa số dư", "dc:xem")]]
        # Số thật cao hơn: bot đã trừ mọi khoản chi vào tài khoản này, nên khoản chi trả bằng tiền mặt hay thẻ cũng
        # làm số thật cao hơn. Hỏi trước, không mặc định ghi một khoản thu không có thật.
        ask = ("\nCó khoản chi bạn trả bằng tiền mặt hoặc thẻ không? Bot đã trừ nó vào tài khoản này nên số thật mới "
               "cao hơn. Nếu vậy chỉ cần sửa số dư; chỉ ghi là thu khi đúng là tiền mới về.")
        return note + ask, [[("✅ Chỉ sửa số dư (có chi tiền mặt/thẻ)", "dc:xem")],
                            [(f"💰 Ghi {short(r.gap)} là thu chưa ghi", f"dc:ghi:{r.item['id']}")]]
    return note, screen_rows()


def gap_booked_text(g):
    if g.status == "da_xu_ly":
        return "Khoản lệch này đã xử lý rồi"
    return (f"✅ Đã ghi {short(abs(g.gap))} là {'khoản chi' if g.gap < 0 else 'khoản thu'} chưa ghi "
            "(không trừ số dư lần nữa)")


def morning_view(day, count):
    """Ngày 15: một phần trong tin sáng."""
    return (f"🔄 Hôm nay đối chiếu tài sản tháng {day.month}: {count} ngăn, so với app ngân hàng, Fmarket",
            [[("🔄 Bắt đầu đối chiếu", "dc:xem")]])


def todo_view(day, count):
    """Việc cần làm ở 🏠 Hôm nay."""
    return f"🔄 Đối chiếu tài sản tháng {day.month}: còn {count} ngăn", ("🔄 Đối chiếu", "dc:xem")
