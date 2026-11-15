"""Tài sản, mua bán cổ phiếu và khám sức khỏe tài chính cho bot chi tiêu.

- /taisan: khai báo tiền, tiết kiệm, cổ phiếu, quỹ mở, vàng, tiền số, ngoại tệ, tài sản khác, nợ; bot tự lấy
  giá và tính tài sản ròng. Vàng dùng chung ví vàng (/vivang) của bot bản tin.
- Nhắn "mua 1000 FPT giá 95" / "bán 500 FPT giá 120": cập nhật danh mục, tính thuế, lãi/lỗ, ghi lãi vào Thu nhập.
- /suckhoe: khám sức khỏe tài chính từ số liệu của chính bạn; AI chỉ viết nhận xét, không khuyên mua bán mã nào.
"""
import html
import re
import sys
from calendar import monthrange
from datetime import date, timedelta

from infrastructure import kho
from repositories import keys
from repositories.chitieu import ledger as ledger_repo
from domain.luong.salary import Salary
from repositories.taisan import assets as assets_repo
from repositories.luong import salary as salary_repo
from domain.common import dates
from domain.common.money import number  # noqa: F401
from infrastructure import clock
from domain.taisan.kinds import TYPES  # noqa: F401
from domain.taisan.rules import accrued  # noqa: F401
from domain.taisan.text import gold_amount, gold_name, qty_text, short  # noqa: F401
from services.taisan.accounts import (can_be_main, find_account, main_account, main_balance, main_flows,  # noqa: F401
                                      move_main, pick_main, pin_balance, same_name, set_main)
from domain.taisan.rules import find_item, removable  # noqa: F401
from domain.taisan.text import gain_line  # noqa: F401
from services.taisan.sales import (close_saving, collect_loan, realize, remove_named, sell_fund,  # noqa: F401
                                   sell_gold)
from domain.taisan.kinds import ALIASES, FX_CODES  # noqa: F401
from domain.taisan.rules import is_etf, money_and_name, stock_price  # noqa: F401
from domain.taisan.trade import BROKER_FEE, SELL_TAX, parse_trade  # noqa: F401
from services.taisan.declare import add_fx, add_gold, add_holding, add_saving, add_saving_item, add_simple  # noqa: F401
from services.taisan.flows import monthly_flows  # noqa: F401
from services.taisan.reminders import maturity_notes, salary_due  # noqa: F401
from services.taisan.trade import broker_cash, trade  # noqa: F401
from services.taisan.valuation import compare_line, history, pending_orders, snapshot, valuation  # noqa: F401
from services.taisan.prices import (SOURCES, coin_prices, fund_navs, fx_rates, gold_table, prices,  # noqa: F401
                                    stock_prices)
from domain.vang.gold import GoldLot, holdings_chi, sell_fifo
from repositories.vang import gold as gold_repo
import phantich as pt
import sochitieu as ct
from bantin import vn_num

BUTTONS = [[("📊 Biểu đồ", "ts:bd"), ("🩺 Khám sức khỏe", "ts:sk")],
           [("🗂 Sửa, xóa", "ts:ds"), ("🔄 Cập nhật giá", "ts:xem")],
           [("🏦 Tài khoản chính", "ts:chinh"), ("➕ Thêm", "y:them"), ct.BACK]]


def now_vn():
    return clock.now_vn()


def load():
    return assets_repo.load()


def save(data):
    assets_repo.save(data)


def new_id(data):
    return assets_repo.new_id(data)


# ---- Giá: xem services/taisan/prices.py ---------------------------------------------------


# ---- Định giá -------------------------------------------------------------------------

def add_months(d, months):
    return dates.add_months(d, months)


# ---- /taisan ---------------------------------------------------------------------------

USAGE = ("💼 <b>Khai báo tài sản</b> (số tiền viết kiểu 25tr, 1tỷ2):\n"
         "• Tiền, tài khoản: /taisan tien VCB 25tr (cùng tên thì cập nhật số dư)\n"
         "• Tiết kiệm: /taisan tietkiem VCB 100tr 4,7% 6 thang 01/08/2026\n"
         "• Cổ phiếu: /taisan cp FPT 1000 95 (số lượng, giá vốn nghìn đồng)\n"
         "• ETF: /taisan etf E1VFVN30 1000 30 (ETF VN30 của Dragon Capital)\n"
         "• Quỹ mở: /taisan quy VCBF-FIF 1200 15000 (số ccq, giá vốn)\n"
         "• Vàng: /taisan vang sjc 1 luong 140 · /taisan vang nhan 2 chi\n"
         "• Tiền số: /taisan coin btc 0,05 · Ngoại tệ: /taisan usd 1000\n"
         "• Khác: /taisan khac xe máy 30tr\n"
         "• Nợ, trả dần mỗi tháng: /no chú Tư 100tr, trả 5tr/tháng (sổ nợ tự trừ khi trả)\n"
         "Mua bán cổ phiếu, ETF: nhắn <b>mua 1000 FPT giá 95</b>, <b>mua 500 E1VFVN30 giá 33,6</b>, <b>bán 500 FPT giá 120</b>\n"
         "Xem: /taisan · Sửa, xóa: /taisan xoa · Khám sức khỏe tài chính: /suckhoe")




def taisan(args):
    if not kho.ready():
        return ct.NEED_STORE
    word = ct.plain(args[0]) if args else ""
    if word in ("xoa", "sua"):
        return edit_list()
    if word in ("bieudo", "bd"):
        return chart_reply(ct.today())
    if word in ("huongdan", "help", "?"):
        return USAGE
    kind = ALIASES.get(word) or ("ngoaite" if word in FX_CODES else None)
    if not args:
        return overview(ct.today())
    if not kind:
        return USAGE
    data = load()
    rest = args[1:]
    if kind == "vang":
        result = add_gold(rest)
    elif kind == "tietkiem":
        result = add_saving(data, rest)
    elif kind in ("cp", "etf", "quy", "coin"):
        result = add_holding(data, kind, rest)
    elif kind == "ngoaite":
        result = add_fx(data, word, rest)
    else:
        result = add_simple(data, kind, rest)
    if not result:
        return USAGE
    if result.startswith("✅") and kind != "vang":
        save(data)
    return result + "\nXem tổng: /taisan"


def gain_text(gain, cost):
    """'🟢 +190k (+8%)' / '🔴 −146k (−10%)'."""
    pct = f" ({gain / cost * 100:+.0f}%)".replace("-", "−") if cost else ""
    return f"{'🟢 +' if gain >= 0 else '🔴 −'}{short(abs(gain))}{pct}"


def gold_lines(rows):
    """Vàng: mỗi loại một bảng chữ đều cột (<pre>): mỗi lần mua một dòng (ngày, số chỉ, giá mua một chỉ, lãi/lỗ),
    dòng Tổng (vốn trung bình), dòng Hôm nay (giá cửa hàng mua vào). Chấm màu ở cuối dòng để không lệch cột."""
    gold = gold_repo.load()
    lots = {}
    for _, rid, _, value, cost, _ in rows:
        g = gold[int(rid[1:])]
        lots.setdefault(g.kind, []).append((g, value, cost))

    def tr(x):
        return f"{x / 1e6:.2f}".replace(".", ",") + "tr"

    def signed(x):
        return ("+" if x >= 0 else "−") + short(abs(x))

    def pct(gain, cost):
        return f"{gain / cost * 100:+.0f}%".replace("-", "−")

    def row(when, chi, price, gain=None, cost=None):
        line = f"{when:<5} {qty_text(round(chi, 2)):>3} {price:>7}"
        if gain is not None:
            line += f" {signed(gain):>6} {pct(gain, cost):>4} {'🟢' if gain >= 0 else '🔴'}"
        return line

    out = []
    for kind, items in lots.items():
        table = [f"{'Ngày':<5} {'Chỉ':>3} {'Giá/chỉ':>7} {'Lãi/lỗ':>6} {'%':>4}"]
        for g, v, c in items:
            chi = g.chi
            when = f"{g.bought[8:]}/{g.bought[5:7]}" if g.bought else "—"
            table.append(row(when, chi, tr(c / chi), v - c, c) if c else row(when, chi, "?"))
        chi = sum(g.taels for g, _, _ in items) * 10
        value = sum(v for _, v, _ in items)
        priced = [(g, v, c) for g, v, c in items if c]
        if priced:
            cost = sum(c for _, _, c in priced)
            table.append(row("Tổng", chi, tr(cost / (sum(g.taels for g, _, _ in priced) * 10)),
                             sum(v for _, v, _ in priced) - cost, cost))
        if chi and value:
            table.append(f"{'Hôm nay':<9} {tr(value / chi):>7}")
        out.append(f"  {gold_name(kind)}\n<pre>" + "\n".join(table) + "</pre>")
    return out


def overview(day, fresh=False):
    v = valuation(day, fresh)
    if not v["rows"]:
        return USAGE
    lines = [f"💼 <b>Tài sản ròng: {ct.vnd(round(v['net']))}</b>{compare_line(day, v['net'])}",
             f"Tài sản {short(v['assets'])}" + (f" · nợ {short(v['debts'])}" if v["debts"] else "")]
    for kind, label in TYPES.items():
        rows = [r for r in v["rows"] if r[0] == kind]
        if not rows:
            continue
        value = sum(r[3] for r in rows)
        costs = [r for r in rows if r[4] is not None]
        head = f"\n{label}: <b>{short(value)}</b>"
        if kind != "no" and v["assets"]:
            head += f" ({value / v['assets'] * 100:.0f}%)"
        if costs and kind != "tietkiem":
            gain = sum(r[3] - r[4] for r in costs)
            base = sum(r[4] for r in costs)
            head += f" · {'🟢 lãi' if gain >= 0 else '🔴 lỗ'} {short(abs(gain))}" + (
                f" ({gain / base * 100:+.1f}%)".replace(".", ",").replace("-", "−") if base else "")
        elif kind == "tietkiem":
            head += f" · lãi tới nay {short(sum(r[3] - r[4] for r in rows))}"
        lines.append(head)
        if kind == "vang":  # vàng: gộp theo loại, giá theo chỉ, mỗi lần mua một dòng có giá mua
            lines += gold_lines(rows)
            continue
        for _, _, name, value, cost, detail in rows:
            if not value and not cost:
                continue  # đã bán hết, quỹ chờ trống: không hiện dòng 0đ
            line = f"  • {html.escape(name)}: {short(value)}"
            if detail:
                line += f" · {html.escape(detail)}"
            if cost and kind != "tietkiem" and "chưa có giá" not in detail:
                change = (value - cost) / cost * 100
                line += f" {'🟢' if change >= 0 else '🔴'}{change:+.0f}%".replace("-", "−")
            lines.append(line)
    realized = [x for x in v["lailo"] if x["ngay"][:4] == str(day.year)]
    if realized:
        total = sum(x["lai"] for x in realized)
        lines.append(f"\n💰 Lãi/lỗ đã chốt năm {day.year}: <b>{'+' if total >= 0 else '−'}{ct.vnd(round(abs(total)))}</b>"
                     f" ({len(realized)} lần bán)")
    lines += [f"<i>⚠️ {html.escape(n)}</i>" for n in v["notes"]]
    snapshot(day, v)
    return "\n".join(lines), BUTTONS


def edit_list():
    v = valuation(ct.today())
    if not v["rows"]:
        return USAGE
    lines = ["🗂 <b>Bấm ❌ để xóa</b> (sửa: khai báo lại cùng tên/mã là được cập nhật)"]
    buttons = []
    for i, (kind, rid, name, value, _, _) in enumerate([r for r in v["rows"] if not r[1].startswith("lenh")], 1):
        lines.append(f"{i}. {TYPES[kind].split()[0]} {html.escape(name)}: {short(value)}")
        buttons.append((f"❌ {i}", f"ts:x:{rid}"))
    return "\n".join(lines), [buttons[i:i + 5] for i in range(0, len(buttons), 5)] + [[("↩️ Xong", "ts:xem")]]


def remove(rid):
    if rid.startswith("v"):
        return gold_repo.remove_at(int(rid[1:]))
    data = load()
    kept = [it for it in data["items"] if str(it["id"]) != rid]
    if len(kept) == len(data["items"]):
        return False
    data["items"] = kept
    save(data)
    return True


def chart_reply(day):
    v = valuation(day)
    sums = {}
    for kind, _, _, value, _, _ in v["rows"]:
        if kind != "no" and value > 0:
            sums[kind] = sums.get(kind, 0) + value
    if not sums:
        return "Chưa có tài sản nào để vẽ. " + USAGE
    order = sorted(sums.items(), key=lambda x: -x[1])
    colors = {k: pt.PALETTE[i] for i, k in enumerate(TYPES)}
    pie = {"type": "doughnut", "data": {
        "labels": [f"{TYPES[k].split(' ', 1)[1]} {pt.short(x)} ({x / v['assets'] * 100:.0f}%)" for k, x in order],
        "datasets": [{"data": [round(x) for _, x in order], "backgroundColor": [colors[k] for k, _ in order]}]},
        "options": {"plugins": {"datalabels": {"display": False}, "legend": {"position": "right", "labels": {"font": {"size": 16}}},
                                "title": {"display": True, "font": {"size": 22},
                                          "text": f"Tài sản ròng {ct.vnd(round(v['net']))}"}}}}
    try:
        images = [pt.chart_png(pie)]
        past = history()
        if len(past) >= 2:
            line = {"type": "line", "data": {"labels": [f"{k[8:]}/{k[5:7]}" for k, _ in past],
                                             "datasets": [{"label": "Tài sản ròng (triệu đồng)", "fill": True,
                                                           "data": [round(x["rong"] / 1e6, 1) for _, x in past],
                                                           "borderColor": "#2f9e44", "backgroundColor": "#2f9e4433"}]},
                    "options": {"locale": "vi-VN", "plugins": {"datalabels": {"display": False}, "title": {
                        "display": True, "font": {"size": 20}, "text": "Tài sản ròng theo thời gian (triệu đồng)"}}}}
            images.append(pt.chart_png(line, 900, 450))
    except Exception as e:
        print(f"[lỗi] vẽ biểu đồ tài sản: {e!r}", file=sys.stderr)
        return "⚠️ Chưa vẽ được biểu đồ (dịch vụ vẽ không trả lời), thử lại sau"
    return {"photos": images, "caption": f"💼 <b>Tài sản ròng</b>: {ct.vnd(round(v['net']))}"}


# ---- Mua bán cổ phiếu bằng tin nhắn ----------------------------------------------------

# ---- Tài khoản chính: nơi lương về, tiền tiêu và tiền chuyển đi các ngăn khác ---------------
# Số dư = số dư thật lúc chốt + thu − chi ghi sổ sau lúc chốt (khoản có số thứ tự lớn hơn mốc, ngày từ ngày chốt)
# ± tiền chuyển qua lại với các ngăn khác (quỹ dự phòng, quỹ chờ đầu tư, sổ tiết kiệm, vàng, cổ phiếu...).
# Tính lại mỗi lần xem nên sửa, xóa khoản chi cũng tự đúng. Chưa chọn tài khoản chính thì mọi thứ như trước.

def main_line(day=None):
    """'🏦 VCB ~12,3tr' cho màn hình tổng quan; None nếu chưa chọn."""
    it = main_account()
    return f"🏦 {html.escape(it['ten'])} còn ~<b>{short(main_balance(it, day))}</b>" if it else None


def main_text(day):
    it = main_account()
    if not it:
        return choose_main()
    income, spend = main_flows(it, day)
    moves = it.get("chuyen", [])
    out = sum(-x["tien"] for x in moves if x["tien"] < 0)
    back = sum(x["tien"] for x in moves if x["tien"] > 0)
    since = date.fromisoformat(it["moc_ngay"])
    lines = [f"🏦 <b>{html.escape(it['ten'])} ~{ct.vnd(round(main_balance(it, day)))}</b> (tài khoản chính)",
             f"📌 Chốt {since:%d/%m}: {ct.vnd(it['tien'])}",
             f"💰 Thu +{short(income) if income else '0đ'} · 💸 chi −{short(spend) if spend else '0đ'}"]
    if out or back:
        lines.append(f"🔁 Chuyển đi −{short(out)}" + (f" · về +{short(back)}" if back else ""))
        lines += [f"   {x['ngay'][8:]}/{x['ngay'][5:7]} {'−' if x['tien'] < 0 else '+'}{short(abs(x['tien']))} "
                  f"{html.escape(x['ghi'])}" for x in moves[-5:][::-1]]
    lines.append("<i>Lệch với app ngân hàng thì bấm cập nhật số dư thật</i>")
    return "\n".join(lines), [[("✏️ Cập nhật số dư thật", "y:them:tai_khoan:chinh")],
                              [("🔁 Đổi tài khoản chính", "ts:chon"), ("💼 Tài sản", "m:ts"), ct.BACK]]


def choose_main():
    data = load()
    options = [it for it in data["items"] if can_be_main(it)]
    lines = ["🏦 <b>Chọn tài khoản chính</b> (lương về, hay tiêu)",
             "Bot tự cộng thu, trừ chi, trừ tiền chuyển sang quỹ, đầu tư, tiết kiệm, trả nợ."]
    if not options:
        lines.append("Chưa có tài khoản: nhắn «tài khoản Techcombank còn 14tr» hoặc bấm nút.")
        return "\n".join(lines), [[("➕ Thêm tài khoản", "y:them:tai_khoan"), ct.BACK]]
    rows = [[(("✅ " if it.get("chinh") else "") + f"{it['ten']} ({short(main_balance(it) if it.get('chinh') else it['tien'])})",
              f"ts:chinh:{it['id']}")] for it in options[:6]]
    return "\n".join(lines), rows + [[("➕ Tài khoản khác", "y:them:tai_khoan"), ct.BACK]]


# ---- Bán, rút, thu về: xem services/taisan/sales.py ------------------------------------


# ---- Nhắc lương ------------------------------------------------------------------------

def luong(args):
    if not kho.ready():
        return ct.NEED_STORE
    usage = ("Nhắc ngày nhận lương: /luong 10 25tr (ngày 10 hằng tháng, 25 triệu)\nTới ngày, bot hỏi đã nhận chưa, "
             "bấm một nút là ghi vào Thu nhập. Bỏ nhắc: /luong xoa")
    if not args:
        s = salary_repo.load()
        return (f"💼 Đang nhắc lương ngày {s.day} hằng tháng, {ct.vnd(s.amount)}\n" + usage) if s else usage
    if ct.plain(args[0]) == "xoa":
        salary_repo.clear()
        return "Đã bỏ nhắc lương"
    found = ct.parse_amount(" ".join(args[1:])) if len(args) > 1 else None
    if not args[0].isdigit() or not 1 <= int(args[0]) <= 31 or not found:
        return usage
    salary_repo.save(Salary(int(args[0]), found[0]))
    return f"✅ Ngày {int(args[0])} hằng tháng bot sẽ hỏi đã nhận lương {ct.vnd(found[0])} chưa"


# ---- Khám sức khỏe tài chính -----------------------------------------------------------

def health_checks(day):
    """[(điểm 0–20 hoặc None nếu thiếu dữ liệu, dấu, dòng mô tả)] và dữ liệu thô cho AI."""
    v = valuation(day)
    spend, income, days = monthly_flows(day)
    checks = []
    kinds = {}
    for kind, _, _, value, _, _ in v["rows"]:
        kinds[kind] = kinds.get(kind, 0) + value
    liquid = kinds.get("tien", 0) + kinds.get("tietkiem", 0)
    fund = None
    if any(it.get("duphong") for it in load()["items"]):  # đã lập quỹ dự phòng: dùng đúng số liệu của quỹ
        try:
            from services.duphong import reserve as reserve_service
            fund = reserve_service.status(day)
        except Exception as e:
            print(f"[lỗi] quỹ dự phòng trong khám sức khỏe: {e!r}", file=sys.stderr)
    if fund and fund.monthly:
        months = fund.covered
        score = 20 if months >= 6 else 15 if months >= 3 else 8 if months >= 1 else 0
        checks.append((score, "✅" if months >= 3 else "⚠️" if months >= 1 else "🚨",
                       f"Quỹ dự phòng {vn_num(months, 1)}/{fund.months} tháng chi ({short(fund.balance)})"))
    elif spend and v["rows"] and days >= 14:  # ít ngày quá thì một khoản lớn làm sai cả tháng
        months = liquid / spend
        score = 20 if months >= 6 else 15 if months >= 3 else 8 if months >= 1 else 0
        checks.append((score, "✅" if months >= 3 else "⚠️" if months >= 1 else "🚨",
                       f"Quỹ dự phòng ~{vn_num(months, 1)} tháng chi (tiền + tiết kiệm {short(liquid)}) · nên 3–6"))
    else:
        checks.append((None, "❔", "Quỹ dự phòng: cần khai báo tiền và ghi chi ≥ 2 tuần"))
    if income and days >= 20:
        rate = (income - spend) / income * 100
        score = 20 if rate >= 30 else 16 if rate >= 20 else 10 if rate >= 10 else 5 if rate >= 0 else 0
        checks.append((score, "✅" if rate >= 20 else "⚠️" if rate >= 0 else "🚨",
                       f"Để dành {rate:.0f}% thu (thu {short(income)}, chi {short(spend)}/tháng) · nên ≥ 20%"))
    else:
        checks.append((None, "❔", "Để dành: cần ghi thu nhập và ≥ 20 ngày dữ liệu"))
    if v["assets"]:
        from interface.no import debt as sono  # nợ: chấm theo tiền trả mỗi tháng so với thu nhập, tách nợ không lãi
        checks.append(sono.health_check(day, v, income if income and days >= 20 else None))
        warnings = []
        for kind, _, name, value, _, _ in v["rows"]:
            if kind in ("cp", "quy", "coin") and value / v["assets"] > 0.2:
                warnings.append(f"{html.escape(name)} chiếm {value / v['assets'] * 100:.0f}% tài sản")
        if kinds.get("coin", 0) / v["assets"] > 0.1:
            warnings.append(f"tiền số chiếm {kinds['coin'] / v['assets'] * 100:.0f}% (biến động rất mạnh)")
        top = max(((k, x) for k, x in kinds.items() if k != "no"), key=lambda x: x[1], default=None)
        if top and top[1] / v["assets"] > 0.7 and len(v["rows"]) > 1:
            warnings.append(f"{TYPES[top[0]].split(' ', 1)[1].lower()} chiếm {top[1] / v['assets'] * 100:.0f}% tài sản")
        score = 20 if not warnings else 12 if len(warnings) == 1 else 5
        checks.append((score, "✅" if not warnings else "⚠️", "Phân bổ: " + ("ổn"
                                                                          if not warnings else "; ".join(warnings))))
        losers = [f"{html.escape(name)} {(value - cost) / cost * 100:.0f}%" for kind, _, name, value, cost, _ in v["rows"]
                  if kind in ("cp", "etf", "quy", "coin", "vang") and cost and value and (value - cost) / cost <= -0.2]
        trend = compare_line(day, v["net"])
        score = 20 if not losers else 10
        checks.append((score, "✅" if not losers else "⚠️",
                       ("Lỗ ≥ 20%: " + ", ".join(losers) if losers else "Không khoản nào lỗ ≥ 20%")
                       + (f" · tài sản ròng{trend}" if trend else "")))
    else:
        checks.append((None, "❔", "Nợ, phân bổ: chưa khai báo tài sản"))
    return checks, v, (spend, income, days)


def health(day):
    if not kho.ready():
        return ct.NEED_STORE
    checks, v, (spend, income, days) = health_checks(day)
    scored = [c for c in checks if c[0] is not None]
    if not scored:
        return "🩺 Chưa đủ dữ liệu để khám. " + USAGE
    score = round(sum(c[0] for c in scored) / (20 * len(scored)) * 100)
    label = "Tốt" if score >= 80 else "Khá" if score >= 60 else "Cần chú ý" if score >= 40 else "Yếu"
    color = {"✅": "🟢", "⚠️": "🟡", "🚨": "🔴"}
    lines = [f"🩺 <b>Sức khỏe tài chính {score}/100</b> ({label})"] + [f"{color.get(mark, mark)} {text}"
                                                                        for _, mark, text in checks]
    if v["rows"]:
        lines.insert(1, f"Tài sản ròng {short(v['net'])}" + (f" · nợ {short(v['debts'])}" if v["debts"] else ""))
    advice = []
    if ct.ai_key():
        facts = re.sub(r"<[^>]+>", "", html.unescape("\n".join(lines)))
        system = ("Bạn là trợ lý khám sức khỏe tài chính cá nhân, viết tiếng Việt có dấu, ngắn gọn, xưng \"bạn\". "
                  "Chỉ dựa vào số liệu được cho, không bịa số. Không khuyên mua hay bán mã cổ phiếu, quỹ, tiền số cụ "
                  "thể nào và không dự đoán giá. Trả lời không markdown: 2 dòng bắt đầu bằng \"• \" là nhận xét quan "
                  "trọng nhất; 2–3 dòng bắt đầu bằng \"✅ \" là việc nên làm cụ thể có con số (ví dụ để dành thêm "
                  "3tr/tháng thì sau 8 tháng đủ quỹ dự phòng 6 tháng).")
        try:
            answer, _ = ct.ai_chat(system, facts)
            for raw in answer.splitlines():
                raw = raw.strip()
                if raw.startswith(("•", "✅")) and len(advice) < 5:
                    advice.append(html.escape(raw))
        except Exception as e:
            print(f"[lỗi] AI khám sức khỏe: {e!r}", file=sys.stderr)
    if advice:
        lines += ["", "💡 <b>Việc nên làm</b>"] + advice
    return "\n".join(lines)


# ---- Nút bấm ---------------------------------------------------------------------------

def on_button(arg, message, now):
    """Nút "ts:...": (thông báo nhỏ, việc tiếp theo) như sochitieu.on_button."""
    day = now.date()
    if arg == "xem":
        return "Đang cập nhật giá…", ("edit", lambda: overview(day, fresh=True))
    if arg == "bd":
        return "Đang vẽ biểu đồ…", ("send", lambda: chart_reply(day))
    if arg == "sk":
        return "Đang khám, chờ chút…", ("send", lambda: health(day))
    if arg == "ds":
        return None, ("edit", edit_list)
    if arg == "hd":
        return None, ("send", lambda: USAGE)
    if arg == "chinh":
        return None, ("edit", lambda: main_text(day))
    if arg == "chon":
        return None, ("edit", choose_main)
    if arg.startswith("chinh:"):
        it = pick_main(arg[6:])
        if not it:
            return "Tài khoản này không còn", ("edit", choose_main)
        return f"Đã chọn {it['ten']}"[:190], ("edit", lambda: main_text(day))
    if arg.startswith("x:"):
        gone = remove(arg[2:])
        return ("Đã xóa" if gone else "Mục này đã xóa rồi"), ("edit", edit_list)
    if arg.startswith("luong:"):
        amount = int(arg[6:])
        entry = {"id": ledger_repo.next_id(), "ngay": day.isoformat(), "gio": now.strftime("%H:%M"),
                 "tien": amount, "ghichu": f"lương tháng {day.month}", "nhom": ct.INCOME}
        ct.save(entry)
        done = f"✅ Đã ghi lương tháng {day.month}: {ct.vnd(amount)} vào 💰 Thu nhập"
        hint = ct.salary_fund_hint([entry], day)  # gợi ý chia lương: trả nợ, chi tiêu, quỹ dự phòng
        return "Đã ghi lương", ("edit", lambda: (done + "\n" + hint[0], [hint[1]]) if hint else done)
    if arg == "chua":
        return "Mai bot hỏi lại", ("edit", lambda: "Chưa nhận lương: mai bot hỏi lại (tối đa 3 ngày)")
    return None, None
