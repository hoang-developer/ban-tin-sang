"""Kế hoạch tài chính: dựng tin Telegram (HTML) và nút từ số liệu của service. Không logic nghiệp vụ, không đọc kho."""
import html

import sochitieu as ct  # module cũ ở gốc: nút ⬅ Về
from domain.taisan import text as taisan_text
from domain.duphong.reserve import MIN_DAYS
from domain.kehoach.plan import INVEST, STEP_MIN
from domain.no.debt import is_due, month_left, ym_text
from presentation.no.debt import short_name
from presentation.no.debt import short as debt_short


def short(x):
    return taisan_text.short(x) if abs(x) >= 1000 else "0đ"


def mark(done, need):
    """✅ đủ · 🟡 một phần · ⬜ chưa."""
    return "✅" if need and done >= need * 0.98 else "🟡" if done else "⬜"


# ---- Mỗi ngày được tiêu --------------------------------------------------------------------

def room_text(per_day, today_left, bold=False, what="phần chi tiêu"):
    b = (lambda x: f"<b>{x}</b>") if bold else (lambda x: x)
    if per_day <= 0:
        return f"🔴 Hết {what} tháng này"
    if today_left >= 0:
        return f"🟢 Hôm nay còn {b(short(today_left))} · mức {short(per_day)}/ngày"
    return f"🔴 Hôm nay quá {b(short(-today_left))} · mức {short(per_day)}/ngày"


def spend_text(s, bold=False):
    """'🟢 Hôm nay còn 180k · mức 250k/ngày' hoặc '🔴 Hôm nay quá 50k · mức 250k/ngày'."""
    return room_text(s["per_day"], s["today_left"], bold, "ngân sách tổng" if s["basis"] == "tong" else "phần chi tiêu")


def basis_text(s):
    """Con số trên tính từ đâu."""
    if s["basis"] == "tong":
        return f"ngân sách tổng {short(s['limit'])}/tháng"
    head, *rest = s["parts"]
    return (f"thu {short(head[1])}" + "".join(f" − {k} {short(v)}" for k, v in rest if v)
            + f" = {short(s['limit'])} chi tiêu/tháng")


# ---- Các việc của kế hoạch ---------------------------------------------------------------------

def step_label(kind, debt, invest_fund):
    if kind == "no":
        return f"Trả {short_name(debt, 24)}"
    if kind == "dp":
        return "Nạp quỹ dự phòng"
    return f"Để vào quỹ chờ {invest_fund}"


def next_action_lines(items):
    """Tối đa 3 việc nên làm ngay (items: domain.kehoach.plan.urgent_items)."""
    out = []
    for item in items:
        kind = item[0]
        if kind == "no":
            _, d, left = item
            out.append(f"Trả {html.escape(d['ten'])} {short(left)}"
                       + (f" (hạn ngày {d['ngay_tra']})" if d.get("ngay_tra") else ""))
        elif kind == "dp":
            out.append(f"Nạp quỹ dự phòng {short(item[1])}")
        elif kind == "ghi_chep":
            out.append(f"Ghi chép đủ {MIN_DAYS} ngày ({item[1]}/{MIN_DAYS})")
        else:
            out.append(f"Xếp nhóm {item[1]} khoản chưa rõ: /chuaxep")
    return out[:3] or ["Không có việc gấp 👌"]


def main_note(main, left, total):
    """Dòng tài khoản chính trước khi làm: tiền đi từ đâu, còn bao nhiêu."""
    if not main:
        return "<i>Chưa chọn tài khoản chính: không trừ số dư tài khoản nào</i>"
    return (f"🏦 {html.escape(main['ten'])} {short(left)} → ~<b>{short(left - total)}</b>"
            + (" 🔴 không đủ" if left < total else ""))


def confirm_view(day, todo, invest_fund, main, balance):
    """(tin hỏi lại, nút) trước khi làm hết kế hoạch. todo: các việc còn lại; rỗng thì báo đã làm hết."""
    if not todo:
        return "✅ Kế hoạch tháng này đã làm hết rồi.", [[("📋 Chia lương", "kh:chia"), ct.BACK]]
    total = sum(x[2] for x in todo)
    icons = {"no": "💳", "dp": "🛟", "dt": "📈"}
    lines = [f"✅ <b>Làm hết kế hoạch tháng {day.month}?</b>"] + [
        f"{icons[kind]} {html.escape(step_label(kind, d, invest_fund))} <b>{short(amount)}</b>" for kind, d, amount, _ in todo]
    lines += [f"Σ <b>{short(total)}</b>", main_note(main, balance, total)]
    return "\n".join(lines), [[("✅ Làm ngay", "kh:het:ok"), ("↩️ Xem lại kế hoạch", "kh:chia")]]


def do_all_lines(r):
    """Các dòng báo sau khi làm hết kế hoạch (r: DoAllResult hoặc None nếu không còn việc)."""
    if r is None:
        return ["Kế hoạch tháng này đã làm hết rồi"]
    done = [f"{'✅' if x.ok else '⚠️ Chưa làm được:'} {html.escape(step_label(x.kind, x.debt, r.invest_fund))} {short(x.amount)}"
            for x in r.results]
    if r.main:
        done.append(f"🏦 {html.escape(r.main['ten'])} còn ~{short(r.main_balance)}")
    return done


# ---- Lộ trình ------------------------------------------------------------------------------------

def roadmap_steps_text(r, fund, invest):
    """5 dòng chữ của các bước lộ trình (r: Roadmap, fund: ReserveStatus, invest: phần đầu tư quỹ mở hoặc None)."""
    steps = ["📒 Ghi chép ≥ 2 tuần" + ("" if r.days >= MIN_DAYS else f" ({r.days}/{MIN_DAYS} ngày)"),
             "🛟 Quỹ dự phòng 1 tháng chi" + (f" ({short(fund.balance)}/{short(fund.monthly)})" if fund.monthly else "")]
    if r.bearing:
        steps.append(f"💳 Trả hết nợ có lãi: còn {short(sum(d['tien'] for d in r.bearing))} ("
                     + html.escape(", ".join(d["ten"] for d in r.bearing)) + ")"
                     + (f" · xong ~{ym_text(r.bearing_last)}" if r.bearing_last else ""))
    else:
        steps.append("💳 Trả hết nợ có lãi" + ("" if r.debts else " (không có nợ)"))
    steps.append(f"🛟 Quỹ dự phòng {fund.months} tháng chi"
                 + (f" ({short(fund.target)}): {fund.balance / fund.target * 100:.0f}%" if fund.target else ""))
    held = " · ".join(f"{label} {short(r.held[k])}" for k, label in INVEST if r.held.get(k))
    plan_text = (f"{invest['ma']} {short(invest['gop'])}/tháng (Value Averaging)" if invest and invest["gop"] else
                 f"{invest['ma']} ({invest['note']})" if invest else "tiết kiệm, vàng, ETF, quỹ mở, cổ phiếu")
    steps.append(f"📈 Đầu tư đều: {plan_text}" + (f"\n      đang có: {held}" if held else ""))
    return steps


def step_line(r, fund, invest):
    """'🎯 Bước 2/5: 🛟 Quỹ dự phòng mốc đầu…' cho màn hình Kế hoạch."""
    texts = roadmap_steps_text(r, fund, invest)
    return f"🎯 Bước {r.current + 1}/{len(texts)}: {texts[r.current].split(chr(10))[0]}"


def roadmap_view(day, n, r, actions):
    """(tin, nút) của màn hình lộ trình. actions: các việc nên làm ngay (urgent_items)."""
    texts = roadmap_steps_text(r, n["fund"], n["invest"])
    lines = ["🎯 <b>Lộ trình xây tài sản</b>"]
    for i, text in enumerate(texts):
        icon = "✅" if r.done[i] else "👉" if i == r.current else "⬜"
        lines.append(f"{icon} {i + 1}. {text}")
    if r.zero:
        ym = n["ym"]
        status = ["✅" if not month_left(d, ym) else "⬜" for d in r.zero if is_due(d, ym)]
        lines.append("🤝 Song song: nợ không lãi (" + html.escape(", ".join(d["ten"] for d in r.zero)) + ")"
                     + (f" · tháng {day.month} {''.join(status)}" if status else " · trả từ tháng sau"))
    lines.append("\n👉 <b>Việc nên làm</b>")
    lines += [f"• {a}" for a in next_action_lines(actions)]
    rows = [[("📋 Chia lương tháng này", "kh:chia")],
            [("🛟 Quỹ dự phòng", "dp:xem"), ("💳 Sổ nợ", "no:xem")],
            [("📈 Đầu tư", "dt:xem"), ("🩺 Khám sức khỏe", "ts:sk"), ct.BACK]]
    return "\n".join(lines), rows


# ---- Chia lương ------------------------------------------------------------------------------------

def plan_view(day, n, s, step, main, balance, todo):
    """(tin, nút) của màn hình chia lương. step: dòng bước lộ trình (hoặc None); s: mỗi ngày được tiêu (hoặc None);
    main/balance: tài khoản chính và số dư; todo: các việc còn lại."""
    f = n["fund"]
    head = f"📋 <b>Chia lương {day.month}/{day.year}</b>"
    if n["income"]:
        head += f" · 💰 <b>{short(n['income'])}</b>" + (f" ({n['income_basis']})" if n["income_basis"] else "")
    lines = [head]
    if step:
        lines.append(step)
    if not n["income"]:
        lines.append("💰 Chưa có thu nhập: nhắn «+ lương 19tr», hoặc «lương về ngày 5, khoảng 19tr»")
    if n["debts"]:
        names = " · ".join(f"{html.escape(short_name(d, 24))} {mark(paid, need)}" for d, need, paid in n["debts"])
        lines.append(f"💳 Trả nợ <b>{short(n['debt_need'])}</b>: {names}")
    if n["spend_basis"]:
        lines.append(f"🧾 Chi tiêu ~<b>{short(n['spend'])}</b> ({n['spend_basis']}) · đã chi {short(n['spent'])}")
    if n["fund_ideal"]:
        lines.append(f"🛟 Quỹ dự phòng <b>{short(n['fund_target'])}</b> {mark(n['fund_added'], n['fund_target'])}"
                     + (f" đã nạp {short(n['fund_added'])}" if n["fund_added"] else ""))
        if n["fund_target"] < n["fund_ideal"]:
            lines.append(f"   ⏳ Kịp hạn {f.deadline:%m/%Y} cần {short(n['fund_ideal'])}/tháng (đổi hạn: /duphong)")
        if n["freed"] and n["fund_target"] >= n["freed"]:
            lines.append(f"   🔁 gồm {short(n['freed'])} trước trả {html.escape(', '.join(n['freed_names']))} ✅")
    elif f.monthly:
        lines.append(f"🛟 Quỹ dự phòng đủ {f.months} tháng chi ✅")
    else:
        lines.append(f"🛟 Quỹ dự phòng: cần {MIN_DAYS} ngày ghi chép (hoặc /duphong chi 10tr)")
    inv = n["invest"]
    if inv:
        if inv["gop"]:
            lines.append(f"📈 {inv['ma']} <b>{short(inv['gop'])}</b> {mark(inv['added'], inv['gop'])}"
                         + (f" đã để {short(inv['added'])}" if inv["added"] else ""))
        else:
            lines.append(f"📈 {inv['ma']}: {inv['note']}")
    if n["left"] is not None:
        lines.append(f"{'🟢 Còn' if n['left'] >= 0 else '🔴 Thiếu'} <b>{short(abs(n['left']))}</b>")
    if s:
        lines.append(f"{spend_text(s, bold=True)}\n   <i>{basis_text(s)}</i>")
    if main:
        lines.append(f"🏦 {html.escape(main['ten'])} ~<b>{short(balance)}</b>")
    rows = [[(f"✅ Làm hết theo kế hoạch ({short(sum(x[2] for x in todo))})", "kh:het")]] if len(todo) > 1 else []
    rows += [[(f"✅ Trả {short_name(d)} {debt_short(month_left(d, n['ym']))}",
              f"no:tra:{d['id']}:{int(month_left(d, n['ym']))}")]
            for d, _, _ in n["debts"] if month_left(d, n["ym"])][:3]
    if n["fund_left"] >= STEP_MIN:
        rows.append([(f"🛟 Nạp quỹ {short(n['fund_left'])}", f"dp:nap:{int(n['fund_left'])}")])
    if n["invest_left"] >= STEP_MIN:
        rows.append([(f"📈 Để {short(n['invest_left'])} vào quỹ chờ {n['invest']['ma']}", f"dt:nap:{int(n['invest_left'])}")])
    if not main:
        rows.append([("🏦 Chọn tài khoản chính", "ts:chon")])
    rows.append([("🎯 Lộ trình", "kh:lt"), ct.BACK])
    return "\n".join(lines), rows


def salary_hint_view(n, todo):
    """(dòng gợi ý chia lương, hàng nút) sau khi ghi lương."""
    inv = n["invest"]
    parts = ([f"trả nợ {short(n['debt_left'])}"] if n["debt_left"] else []) + (
        [f"chi tiêu ~{short(n['spend'])}"] if n["spend_basis"] else []) + (
        [f"quỹ dự phòng {short(n['fund_left'])}"] if n["fund_left"] else []) + (
        [f"quỹ chờ {inv['ma']} {short(n['invest_left'])}"] if n["invest_left"] else []) + (
        [f"{inv['ma']} {inv['note']}"] if inv and not inv["gop"] and inv["note"] else [])
    line = "📋 Lương về! " + " → ".join(parts) + (
        (f" → 🟢 còn {short(n['left'])}" if n["left"] >= 0 else f" → 🔴 thiếu {short(-n['left'])}")
        if n["left"] is not None else "")
    row = [("📋 Xem kế hoạch", "kh:chia")]
    if len(todo) > 1:
        row.append(("✅ Làm hết theo kế hoạch", "kh:het"))
    elif todo and todo[0][0] == "dp":
        row.append((f"🛟 Để {short(n['fund_left'])} vào quỹ", f"dp:nap:{int(n['fund_left'])}"))
    elif todo and todo[0][0] == "dt":
        row.append((f"📈 {short(n['invest_left'])} → {inv['ma']}", f"dt:nap:{int(n['invest_left'])}"))
    elif todo:
        row.append(("✅ Làm theo kế hoạch", "kh:het"))
    return line, row
