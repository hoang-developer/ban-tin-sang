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
import sys
from datetime import date, timedelta

import duphong
import kho
import sochitieu as ct
import sono
import taisan as ts

NOT_ADVICE = "<i>Tham khảo, không phải lời khuyên tài chính</i>"
INVEST = (("tietkiem", "tiết kiệm"), ("vang", "vàng"), ("etf", "ETF"), ("quy", "quỹ mở"), ("cp", "cổ phiếu"))


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
    spending = [e for e in month if e["nhom"] not in (ct.INCOME, group) and not e.get("no")]
    spent = sum(e["tien"] for e in spending)
    spent_today = sum(e["tien"] for e in spending if e["ngay"] == day.isoformat())
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
    invest = invest_part(day)
    invest_need = invest["gop"] if invest else 0
    left = income - debt_need - spend - target - invest_need if income else None
    return {"ym": ym, "income": income, "income_basis": basis, "debts": debts, "debt_need": debt_need,
            "debt_left": debt_left, "spend": spend, "spend_basis": spend_basis, "spent": spent,
            "spent_today": spent_today, "group": group, "fund": fund,
            "fund_target": target, "fund_ideal": ideal, "fund_added": added, "fund_left": max(0, target - added),
            "freed": freed, "freed_names": freed_names, "left": left, "data": data, "invest": invest,
            "invest_left": max(0, invest_need - invest["added"]) if invest else 0}


def invest_part(day):
    """Phần đầu tư quỹ mở hằng tháng (/dautu) khi chia lương; None nếu chưa bật hoặc lỗi."""
    try:
        import dautu
        return dautu.salary_part(day)
    except Exception as e:
        print(f"[lỗi] phần đầu tư khi chia lương: {e!r}", file=sys.stderr)
        return None


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
    inv = n["invest"]
    if inv:
        if inv["gop"]:
            lines.append(f"{step}. 📈 Đầu tư {inv['ma']}: <b>{short(inv['gop'])}</b> vào quỹ chờ · đã để "
                         f"{short(inv['added'])}" + (" ✅" if not n["invest_left"] else ""))
        else:
            lines.append(f"{step}. 📈 Đầu tư {inv['ma']}: {inv['note']}")
        step += 1
    if n["left"] is not None:
        lines.append(f"{step}. 💰 Còn lại: <b>{short(n['left'])}</b>")
        if n["left"] < 0:
            lines.append(f"⚠️ Thiếu {short(-n['left'])}: bớt chi tiêu, hoặc tháng này nạp quỹ ít hơn")
        elif n["fund_ideal"]:
            lines.append("💡 Cuối tháng còn dư thì dồn thêm vào quỹ dự phòng để xong sớm")
        elif f["monthly"]:
            lines.append("💡 Quỹ đã đủ: phần còn lại để đầu tư đều (tiết kiệm, vàng, ETF, cổ phiếu)")
    s = spendable_safe(day, n)
    if s:
        lines.append(f"🧾 {spend_text(s, bold=True)}\n   <i>{basis_text(s)}</i>")
    main = ts.main_account(n["data"])
    if main:
        lines.append(f"🏦 {html.escape(main['ten'])} còn ~<b>{short(ts.main_balance(main, day))}</b>")
    else:
        lines.append("<i>💡 Chọn tài khoản chính (nơi lương về) để bot tự trừ khi trả nợ, nạp quỹ, góp đầu tư</i>")
    lines.append(NOT_ADVICE)
    todo = steps(n)
    rows = [[(f"✅ Làm hết theo kế hoạch ({short(sum(x[2] for x in todo))})", "kh:het")]] if len(todo) > 1 else []
    rows += [[(f"✅ Trả {sono.short_name(d)} {sono.short(sono.month_left(d, n['ym']))}",
              f"no:tra:{d['id']}:{int(sono.month_left(d, n['ym']))}")]
            for d, _, _ in n["debts"] if sono.month_left(d, n["ym"])][:3]
    if n["fund_left"] >= 100_000:
        rows.append([(f"🛟 Nạp quỹ {short(n['fund_left'])}", f"dp:nap:{int(n['fund_left'])}")])
    if n["invest_left"] >= 100_000:
        rows.append([(f"📈 Để {short(n['invest_left'])} vào quỹ chờ {n['invest']['ma']}", f"dt:nap:{int(n['invest_left'])}")])
    if not main:
        rows.append([("🏦 Chọn tài khoản chính", "ts:chon")])
    rows.append([("🎯 Lộ trình", "kh:lt"), ct.BACK])
    return "\n".join(lines), rows


def salary_hint(entries, day):
    """Vừa ghi lương: (dòng gợi ý chia lương, hàng nút); None nếu không có lương hoặc chưa có gì để chia."""
    salary = [e for e in entries if e["nhom"] == ct.INCOME and "luong" in ct.plain(e.get("ghichu") or "")]
    if not salary or not kho.ready():
        return None
    n = numbers(day)
    inv = n["invest"]
    parts = ([f"trả nợ {short(n['debt_left'])}"] if n["debt_left"] else []) + (
        [f"chi tiêu ~{short(n['spend'])}"] if n["spend_basis"] else []) + (
        [f"quỹ dự phòng {short(n['fund_left'])}"] if n["fund_left"] else []) + (
        [f"quỹ chờ {inv['ma']} {short(n['invest_left'])}"] if n["invest_left"] else []) + (
        [f"{inv['ma']} {inv['note']}"] if inv and not inv["gop"] and inv["note"] else [])
    if not n["debt_left"] and not n["fund_left"] and not n["invest_left"]:
        return None
    line = "📋 Lương về! Gợi ý chia: " + " → ".join(parts) + (
        f" → còn {short(n['left'])}" if n["left"] is not None else "")
    row = [("📋 Xem kế hoạch", "kh:chia")]
    todo = steps(n)
    if len(todo) > 1:
        row.append(("✅ Làm hết theo kế hoạch", "kh:het"))
    elif todo and todo[0][0] == "dp":
        row.append((f"🛟 Để {short(n['fund_left'])} vào quỹ", f"dp:nap:{int(n['fund_left'])}"))
    elif todo and todo[0][0] == "dt":
        row.append((f"📈 {short(n['invest_left'])} → {inv['ma']}", f"dt:nap:{int(n['invest_left'])}"))
    elif todo:
        row.append(("✅ Làm theo kế hoạch", "kh:het"))
    return line, row


# ---- Mỗi ngày được tiêu: một con số dùng chung ---------------------------------------------

def spendable(day, n=None):
    """Mỗi ngày được tiêu bao nhiêu, dùng chung cho tin sau khi ghi, /dubao, tổng quan và chia lương. Có ngân sách
    tổng thì theo ngân sách (tính mọi khoản chi), không thì theo kế hoạch chia lương: thu − trả nợ − quỹ dự phòng − đầu
    tư là phần để chi tiêu cả tháng (không tính trả nợ). Trừ phần đã chi trước hôm nay và khoản lớn sắp tới (tháng trước
    có, tháng này chưa thấy), chia đều cho hôm nay và các ngày còn lại. None nếu chưa tính được (chưa có thu nhập)."""
    import phantich as pt
    f = pt.forecast(day)
    budgets = kho.get(ct.K_BUDGET, {}) or {}
    if budgets.get("tong"):
        per_day, today_left = pt.allowance(f)
        return {"per_day": per_day, "today_left": today_left, "limit": budgets["tong"], "spent": f["spent"],
                "basis": "tong", "parts": None}
    n = n or numbers(day)
    if not n["income"]:
        return None
    invest = n["invest"]["gop"] if n["invest"] else 0
    limit = n["income"] - n["debt_need"] - n["fund_target"] - invest
    upcoming = sum(e["tien"] for e in f["upcoming"] if e["nhom"] != n["group"] and not e.get("no"))
    room = limit - (n["spent"] - n["spent_today"]) - upcoming
    per_day = room / (f["left"] + 1)
    parts = [("thu", n["income"]), ("trả nợ", n["debt_need"]), ("quỹ dự phòng", n["fund_target"]),
             ("đầu tư", invest)]
    return {"per_day": per_day, "today_left": per_day - n["spent_today"], "limit": limit, "spent": n["spent"],
            "basis": "plan", "parts": parts}


def spend_text(s, bold=False):
    """'Hôm nay còn được tiêu 180.000đ (mỗi ngày tối đa 250k)' hoặc báo đã quá."""
    b = (lambda x: f"<b>{x}</b>") if bold else (lambda x: x)
    if s["per_day"] <= 0:
        return "Đã tiêu hết " + ("ngân sách tổng" if s["basis"] == "tong" else "phần dành cho chi tiêu") + " tháng này"
    if s["today_left"] >= 0:
        return f"Hôm nay còn được tiêu {b(approx(s['today_left']))} (mỗi ngày tối đa {short(s['per_day'])})"
    return f"Hôm nay đã tiêu quá {b(approx(-s['today_left']))} so với mức mỗi ngày {short(s['per_day'])}"


def basis_text(s):
    """Con số trên tính từ đâu."""
    if s["basis"] == "tong":
        return f"theo ngân sách tổng {short(s['limit'])}/tháng"
    head, *rest = s["parts"]
    return (f"theo kế hoạch chia lương: thu {short(head[1])}" + "".join(f" − {k} {short(v)}" for k, v in rest if v)
            + f" = {short(s['limit'])} cho chi tiêu cả tháng")


def approx(x):
    return ct.vnd(round(x / 1000) * 1000)


def spendable_safe(day, n=None):
    try:
        return spendable(day, n)
    except Exception as e:
        print(f"[lỗi] mỗi ngày được tiêu: {e!r}", file=sys.stderr)
        return None


# ---- Làm hết theo kế hoạch: trả nợ tới kỳ, nạp quỹ dự phòng, để tiền vào quỹ chờ đầu tư -------------

def steps(n):
    """Các việc còn lại của kế hoạch tháng: [(loại, nhãn, số tiền, mã khoản nợ)]."""
    out = [("no", f"Trả {sono.short_name(d, 24)}", sono.month_left(d, n["ym"]), d["id"])
           for d, _, _ in n["debts"] if sono.month_left(d, n["ym"])]
    if n["fund_left"] >= 100_000:
        out.append(("dp", "Nạp quỹ dự phòng", n["fund_left"], None))
    if n["invest_left"] >= 100_000:
        out.append(("dt", f"Để vào quỹ chờ {n['invest']['ma']}", n["invest_left"], None))
    return out


def main_note(total):
    """Dòng tài khoản chính trước khi làm: tiền đi từ đâu, còn bao nhiêu."""
    main = ts.main_account()
    if not main:
        return ("<i>Chưa chọn tài khoản chính nên bot chỉ ghi vào từng ngăn, không trừ số dư tài khoản nào. Chọn ở "
                "💼 Tài sản → 🏦 Tài khoản chính.</i>")
    left = ts.main_balance(main)
    return (f"🏦 Tiền đi từ <b>{html.escape(main['ten'])}</b>: {short(left)} → còn ~<b>{short(left - total)}</b>"
            + (" ⚠️ không đủ" if left < total else ""))


def confirm_all(day):
    if not kho.ready():
        return ct.NEED_STORE
    n = numbers(day)
    todo = steps(n)
    if not todo:
        return "✅ Kế hoạch tháng này đã làm hết rồi.", [[("📋 Chia lương", "kh:chia"), ct.BACK]]
    total = sum(x[2] for x in todo)
    lines = [f"✅ <b>Làm hết theo kế hoạch tháng {day.month}</b>"] + [
        f"• {html.escape(label)}: <b>{short(amount)}</b>" for _, label, amount, _ in todo]
    lines += [f"Tổng: <b>{short(total)}</b>", main_note(total),
              "<i>Trả nợ được ghi là khoản chi nhóm Trả nợ; nạp quỹ, góp đầu tư là để dành, không tính là chi.</i>"]
    return "\n".join(lines), [[("✅ Làm ngay", "kh:het:ok"), ("↩️ Xem lại kế hoạch", "kh:chia")]]


def do_all(now):
    """Làm các việc còn lại của kế hoạch (tính lại lúc bấm, nên bấm hai lần không làm hai lần)."""
    day = now.date()
    n = numbers(day)
    todo = steps(n)
    if not todo:
        return ["Kế hoạch tháng này đã làm hết rồi"]
    done = []
    for kind, label, amount, ref in todo:
        try:
            if kind == "no":
                e, _ = sono.pay(ref, amount, now)
                ok = e is not None
            elif kind == "dp":
                duphong.change(amount, day)
                ok = True
            else:
                import dautu
                cfg = dautu.config()
                dautu.add_money(cfg, amount, dautu.current_period(cfg))
                dautu.save(cfg)
                ok = True
        except Exception as e:
            print(f"[lỗi] làm theo kế hoạch ({kind}): {e!r}", file=sys.stderr)
            ok = False
        done.append(f"{'✅' if ok else '⚠️ Chưa làm được:'} {html.escape(label)} {short(amount)}")
    main = ts.main_account()
    if main:
        done.append(f"🏦 {html.escape(main['ten'])} còn ~{short(ts.main_balance(main))}")
    return done


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
    inv = n["invest"]
    plan_text = (f"{inv['ma']} {short(inv['gop'])}/tháng, mua theo Value Averaging (/dautu)" if inv and inv["gop"] else
                 f"{inv['ma']} ({inv['note']})" if inv else "tiết kiệm, vàng, ETF, quỹ mở, cổ phiếu (/dautu)")
    steps.append((False, f"📈 Đầu tư đều mỗi tháng: {plan_text}" + (f"\n      đang có: {held}" if held else "")))
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
            [("📈 Đầu tư", "dt:xem"), ("🩺 Khám sức khỏe", "ts:sk"), ct.BACK]]
    return "\n".join(lines), rows


def kehoach(args):
    if not kho.ready():
        return ct.NEED_STORE
    word = ct.plain(args[0]) if args else ""
    if word in ("chia", "luong", "chialuong", "thang"):
        return plan(ct.today())
    return roadmap(ct.today())


def on_button(arg, message, now):
    """Nút "kh:...": lt (lộ trình), chia (chia lương), het (làm hết theo kế hoạch: hỏi lại, het:ok làm)."""
    day = now.date()
    if arg == "lt":
        return None, ("edit", lambda: roadmap(day))
    if arg == "het":
        if (message.get("text") or "").startswith("📋"):
            return None, ("edit", lambda: confirm_all(day))
        return None, ("send", lambda: confirm_all(day))
    if arg == "het:ok":
        done = do_all(now)

        def result():
            text, rows = plan(day)
            return "\n".join(done) + "\n\n" + text, rows
        return "Đã làm theo kế hoạch", ("edit", result)
    if arg == "chia":
        if (message.get("text") or "").startswith(("🎯", "📋", "🏠")):
            return None, ("edit", lambda: plan(day))
        return None, ("send", lambda: plan(day))
    return None, None
