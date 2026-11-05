"""Kế hoạch tài chính cho bot chi tiêu: lộ trình xây tài sản và chia lương mỗi tháng (/kehoach).

Lộ trình 5 bước, thứ tự thường gặp trong sách tài chính cá nhân:
  1. Ghi chép chi tiêu ít nhất 2 tuần (để biết mỗi tháng tiêu bao nhiêu)
  2. Quỹ dự phòng mốc đầu: 1 tháng chi thiết yếu
  3. Trả hết nợ có lãi (thẻ tín dụng, trả góp, vay tiêu dùng)
  4. Quỹ dự phòng đủ mục tiêu (mặc định 6 tháng chi thiết yếu)
  5. Đầu tư đều mỗi tháng: tiết kiệm, vàng, ETF, cổ phiếu
Nợ không lãi (người thân) trả đều theo hẹn, song song với mọi bước.

Chia lương: thu tháng này → trả nợ tới kỳ → chi tiêu (trung bình 90 ngày qua, không tính trả nợ; có ngân sách
tổng thì theo ngân sách) → quỹ dự phòng (mức mỗi tháng để kịp hạn, cộng tiền trước đây trả các khoản nợ đã xong)
→ phần còn lại. Thông tin tham khảo, không phải lời khuyên tài chính có giấy phép.
"""
import html
from datetime import date, timedelta

import duphong
import kho
import sochitieu as ct
import sono
import taisan as ts

NOT_ADVICE = "<i>Tham khảo, không phải lời khuyên tài chính</i>"
INVEST = (("tietkiem", "tiết kiệm"), ("vang", "vàng"), ("etf", "ETF"), ("cp", "cổ phiếu"))


def short(x):
    return ts.short(x) if abs(x) >= 1000 else "0đ"


def spending_estimate(day, group, debt_need):
    """(chi tiêu dự kiến tháng này không tính trả nợ, cách tính) — None nếu chưa có dữ liệu."""
    budgets = kho.get(ct.K_BUDGET, {}) or {}
    if budgets.get("tong"):  # ngân sách tổng tính mọi khoản chi, kể cả trả nợ
        return max(0, budgets["tong"] - debt_need), "theo ngân sách tổng, trừ phần trả nợ"
    items = [e for e in ct.between(day - timedelta(days=89), day)
             if e["nhom"] not in (ct.INCOME, group) and not e.get("no")]
    if not items:
        manual = duphong.config().get("chi")
        return (manual, "chi thiết yếu bạn đặt ở /duphong") if manual else (0, None)
    days = (day - date.fromisoformat(min(e["ngay"] for e in items))).days + 1
    average = sum(e["tien"] for e in items) / days * 30.4
    if days < duphong.MIN_DAYS:
        manual = duphong.config().get("chi")
        if manual:
            return manual, "chi thiết yếu bạn đặt ở /duphong"
        return average, f"mới có {days} ngày ghi chép, số còn thô"
    return average, f"trung bình {days} ngày qua, không tính trả nợ"


def numbers(day):
    """Số liệu chia lương tháng này (dùng chung cho /kehoach, tin ghi lương, màn hình tổng quan)."""
    ym = sono.month_of(day)
    data = ts.load()
    group = sono.debt_group()[0]
    month = ct.load(ym)
    income = sum(e["tien"] for e in month if e["nhom"] == ct.INCOME)
    basis = ""
    if not income:
        salary = kho.get(ts.K_SALARY) or {}
        if salary.get("tien"):
            income, basis = salary["tien"], "lương dự kiến, chưa ghi"
        else:
            _, average, days = ts.monthly_flows(day)
            if average and days >= 20:
                income, basis = average, "trung bình 3 tháng qua"
    debts = []  # (khoản nợ, phải trả kỳ này, đã trả kỳ này)
    for d in sono.debts(data):
        paid = sono.paid_in(d, ym)
        if sono.is_due(d, ym) and (d["tien"] > 0 or paid):
            debts.append((d, min(d["thang"], d["tien"] + paid), paid))
    debt_need = sum(need for _, need, _ in debts)
    debt_left = sum(sono.month_left(d, ym) for d, _, _ in debts)
    spent = sum(e["tien"] for e in month if e["nhom"] not in (ct.INCOME, group) and not e.get("no"))
    spend, spend_basis = spending_estimate(day, group, debt_need)
    fund = duphong.status(day)
    added = duphong.month_added(ym)
    freed, freed_names = sono.freed(data, ym)
    target = ideal = 0
    if fund["monthly"] and fund["missing"] > 0:
        base = fund["missing"] + added  # còn thiếu tính từ đầu tháng: nạp đủ mức tháng này thì không bị gợi ý thêm
        ideal = min(max(base / fund["months_left"], freed), base)
        ideal = int(round(ideal, -5)) or 100_000
        target = ideal
        if income:  # không gợi ý nạp quá phần thu còn lại sau trả nợ và chi tiêu
            room = int(round(income - debt_need - spend, -5))
            target = max(added, min(ideal, max(0, room)))
    left = income - debt_need - spend - target if income else None
    return {"ym": ym, "income": income, "income_basis": basis, "debts": debts, "debt_need": debt_need,
            "debt_left": debt_left, "spend": spend, "spend_basis": spend_basis, "spent": spent, "fund": fund,
            "fund_target": target, "fund_ideal": ideal, "fund_added": added, "fund_left": max(0, target - added),
            "freed": freed, "freed_names": freed_names, "left": left, "data": data}


def plan(day):
    if not kho.ready():
        return ct.NEED_STORE
    n = numbers(day)
    f = n["fund"]
    lines = [f"📋 <b>Chia lương tháng {day.month}/{day.year}</b>"]
    if n["income"]:
        lines.append(f"💰 Thu: <b>{short(n['income'])}</b>" + (f" ({n['income_basis']})" if n["income_basis"] else ""))
    else:
        lines.append("💰 Chưa có thu nhập tháng này: ghi «+ lương 19tr» hoặc đặt ngày lương: /luong 5 19tr")
    step = 1
    if n["debts"]:
        parts = []
        for d, need, paid in n["debts"]:
            mark = "✅" if not sono.month_left(d, n["ym"]) else "🟡" if paid else "⬜"
            parts.append(f"{html.escape(sono.short_name(d, 24))} {short(need)} {mark}")
        lines.append(f"{step}. 💳 Trả nợ: <b>{short(n['debt_need'])}</b> — " + " · ".join(parts))
        step += 1
    if n["spend_basis"]:
        lines.append(f"{step}. 🧾 Chi tiêu: <b>~{short(n['spend'])}</b> ({n['spend_basis']}) · đã chi {short(n['spent'])}")
        step += 1
    if n["fund_ideal"]:
        lines.append(f"{step}. 🛟 Quỹ dự phòng: <b>{short(n['fund_target'])}</b> · đã nạp {short(n['fund_added'])}")
        if n["fund_target"] < n["fund_ideal"]:
            lines.append(f"   Để kịp hạn {f['deadline']:%m/%Y} cần {short(n['fund_ideal'])}/tháng; tháng này phần thu còn "
                         "lại chỉ đủ mức trên (đổi hạn ở /duphong)")
        if n["freed"] and n["fund_target"] >= n["freed"]:
            lines.append(f"   🔁 gồm {short(n['freed'])} trước đây trả {html.escape(', '.join(n['freed_names']))} "
                         "(đã trả xong)")
        step += 1
    elif f["monthly"]:
        lines.append(f"{step}. 🛟 Quỹ dự phòng: đã đủ {f['months']} tháng chi ✅")
        step += 1
    else:
        lines.append(f"{step}. 🛟 Quỹ dự phòng: chưa tính được (cần {duphong.MIN_DAYS} ngày ghi chép, hoặc tự đặt "
                     "chi thiết yếu: /duphong chi 10tr)")
        step += 1
    if n["left"] is not None:
        lines.append(f"{step}. 💰 Còn lại: <b>{short(n['left'])}</b>")
        if n["left"] < 0:
            lines.append(f"⚠️ Thiếu {short(-n['left'])}: bớt chi tiêu, hoặc tháng này nạp quỹ ít hơn")
        elif n["fund_ideal"]:
            lines.append("💡 Cuối tháng còn dư thì dồn thêm vào quỹ dự phòng để xong sớm")
        elif f["monthly"]:
            lines.append("💡 Quỹ đã đủ: phần còn lại để đầu tư đều (tiết kiệm, vàng, ETF, cổ phiếu)")
    lines.append(NOT_ADVICE)
    rows = [[(f"✅ Trả {sono.short_name(d)} {sono.short(sono.month_left(d, n['ym']))}",
              f"no:tra:{d['id']}:{int(sono.month_left(d, n['ym']))}")]
            for d, _, _ in n["debts"] if sono.month_left(d, n["ym"])][:3]
    if n["fund_left"] >= 100_000:
        rows.append([(f"🛟 Nạp quỹ {short(n['fund_left'])}", f"dp:nap:{int(n['fund_left'])}")])
    rows.append([("🎯 Lộ trình", "kh:lt"), ct.BACK])
    return "\n".join(lines), rows


def salary_hint(entries, day):
    """Vừa ghi lương: (dòng gợi ý chia lương, hàng nút); None nếu không có lương hoặc chưa có gì để chia."""
    salary = [e for e in entries if e["nhom"] == ct.INCOME and "luong" in ct.plain(e.get("ghichu") or "")]
    if not salary or not kho.ready():
        return None
    n = numbers(day)
    parts = ([f"trả nợ {short(n['debt_left'])}"] if n["debt_left"] else []) + (
        [f"chi tiêu ~{short(n['spend'])}"] if n["spend_basis"] else []) + (
        [f"quỹ dự phòng {short(n['fund_left'])}"] if n["fund_left"] else [])
    if not n["debt_left"] and not n["fund_left"]:
        return None
    line = "📋 Lương về! Gợi ý chia: " + " → ".join(parts) + (
        f" → còn {short(n['left'])}" if n["left"] is not None else "")
    row = [("📋 Chia lương", "kh:chia")]
    if n["fund_left"] >= 100_000:
        row.append((f"🛟 Để {short(n['fund_left'])} vào quỹ", f"dp:nap:{int(n['fund_left'])}"))
    return line, row


def next_actions(day, n=None):
    """Tối đa 3 việc nên làm ngay, theo thứ tự ưu tiên."""
    n = n or numbers(day)
    out = []
    for d, _, _ in n["debts"]:
        left = sono.month_left(d, n["ym"])
        if left:
            out.append(f"Trả {html.escape(d['ten'])} {short(left)}"
                       + (f" (hạn ngày {d['ngay_tra']})" if d.get("ngay_tra") else ""))
    month_income = any(e["nhom"] == ct.INCOME for e in ct.load(n["ym"]))
    topped = n["fund_added"] and n["fund_left"] < 0.3 * n["fund_target"]  # đã nạp gần đủ: số lệch nhỏ do trung bình chi đổi
    if n["fund_left"] >= 100_000 and month_income and not topped:
        out.append(f"Nạp quỹ dự phòng {short(n['fund_left'])} tháng này")
    if not n["fund"]["monthly"]:
        out.append(f"Ghi chép đủ {duphong.MIN_DAYS} ngày để bot tính quỹ dự phòng (đang có {n['fund']['days']} ngày)")
    pending = sum(ct.pending(e) for e in ct.load(n["ym"]))
    if pending:
        out.append(f"Xếp nhóm {pending} khoản chưa rõ: /chuaxep")
    return out[:3] or ["Không có việc gấp, cứ ghi chép đều nhé ✨"]


def invest_summary(day):
    """'tiết kiệm 50tr · vàng 20tr · ETF 30tr · cổ phiếu 122tr' (không tính phần gắn vào quỹ dự phòng)."""
    fund_ids = {str(it["id"]) for it in ts.load()["items"] if it.get("duphong")}
    sums = {}
    for kind, rid, _, value, _, _ in ts.valuation(day)["rows"]:
        if rid not in fund_ids:
            sums[kind] = sums.get(kind, 0) + value
    return " · ".join(f"{label} {short(sums[k])}" for k, label in INVEST if sums.get(k))


def roadmap(day):
    if not kho.ready():
        return ct.NEED_STORE
    n = numbers(day)
    f, data = n["fund"], n["data"]
    _, _, days = ts.monthly_flows(day)
    debts = sono.active(data)
    bearing = [d for d in debts if sono.has_interest(d)]
    zero = [d for d in debts if not sono.has_interest(d)]
    steps = []
    steps.append((days >= duphong.MIN_DAYS, "📒 Ghi chép chi tiêu ít nhất 2 tuần"
                  + ("" if days >= duphong.MIN_DAYS else f" (đang có {days} ngày)")))
    first = f["monthly"] and f["covered"] >= 1
    steps.append((first, "🛟 Quỹ dự phòng mốc đầu: 1 tháng chi thiết yếu"
                  + (f" ({short(f['monthly'])}) · đang có {short(f['balance'])}" if f["monthly"] else "")))
    if bearing:
        ends = [sono.schedule(d, day) for d in bearing]
        last = max(s[1] for s in ends) if all(ends) else None
        text = (f"💳 Trả hết nợ có lãi: còn {short(sum(d['tien'] for d in bearing))} ("
                + html.escape(", ".join(d["ten"] for d in bearing)) + ")"
                + (f", xong khoảng {sono.ym_text(last)}" if last else ""))
    else:
        text = "💳 Trả hết nợ có lãi" + ("" if debts else " (không có nợ)")
    steps.append((not bearing, text))
    full = f["monthly"] and not f["missing"]
    steps.append((full, f"🛟 Quỹ dự phòng đủ {f['months']} tháng chi"
                  + (f" ({short(f['target'])}): {f['balance'] / f['target'] * 100:.0f}%" if f["target"] else "")))
    held = invest_summary(day)
    steps.append((False, "📈 Đầu tư đều mỗi tháng: tiết kiệm, vàng, ETF, cổ phiếu"
                  + (f"\n      đang có: {held}" if held else "")))
    current = next((i for i, (done, _) in enumerate(steps) if not done), len(steps) - 1)
    lines = ["🎯 <b>Lộ trình xây tài sản</b>"]
    for i, (done, text) in enumerate(steps):
        mark = "✅" if done else "👉" if i == current else "⬜"
        lines.append(f"{mark} {i + 1}. {text}")
    if zero:
        ym = n["ym"]
        status = ["✅" if not sono.month_left(d, ym) else "⬜" for d in zero if sono.is_due(d, ym)]
        lines.append("🤝 Song song: trả đều nợ không lãi (" + html.escape(", ".join(d["ten"] for d in zero)) + ")"
                     + (f" · tháng {day.month} {''.join(status)}" if status else " · kỳ trả đầu tháng sau"))
    lines.append("\n👉 <b>Việc nên làm bây giờ</b>")
    lines += [f"• {a}" for a in next_actions(day, n)]
    lines.append(NOT_ADVICE)
    rows = [[("📋 Chia lương tháng này", "kh:chia")],
            [("🛟 Quỹ dự phòng", "dp:xem"), ("💳 Sổ nợ", "no:xem")],
            [("🩺 Khám sức khỏe", "ts:sk"), ct.BACK]]
    return "\n".join(lines), rows


def kehoach(args):
    if not kho.ready():
        return ct.NEED_STORE
    word = ct.plain(args[0]) if args else ""
    if word in ("chia", "luong", "chialuong", "thang"):
        return plan(ct.today())
    return roadmap(ct.today())


def on_button(arg, message, now):
    """Nút "kh:...": lt (lộ trình), chia (chia lương)."""
    day = now.date()
    if arg == "lt":
        return None, ("edit", lambda: roadmap(day))
    if arg == "chia":
        if (message.get("text") or "").startswith(("🎯", "📋", "🏠")):
            return None, ("edit", lambda: plan(day))
        return None, ("send", lambda: plan(day))
    return None, None
