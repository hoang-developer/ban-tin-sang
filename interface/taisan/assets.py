"""Tài sản, mua bán cổ phiếu và khám sức khỏe tài chính cho bot chi tiêu: lệnh /taisan, /luong, /suckhoe, nút ts:.

- /taisan: khai báo tiền, tiết kiệm, cổ phiếu, quỹ mở, vàng, tiền số, ngoại tệ, tài sản khác, nợ; bot tự lấy
  giá và tính tài sản ròng. Vàng dùng chung ví vàng (/vivang) của bot bản tin.
- Nhắn "mua 1000 FPT giá 95" / "bán 500 FPT giá 120": cập nhật danh mục, tính thuế, lãi/lỗ, ghi lãi vào Thu nhập.
- /suckhoe: khám sức khỏe tài chính từ số liệu của chính bạn; AI chỉ viết nhận xét, không khuyên mua bán mã nào.

Các hàm ở đây giữ tên và dạng giá trị trả về mà các màn hình khác (menu, trợ lý, tin sáng/tối, chia lương, quỹ,
tiết kiệm) đang gọi: đọc lệnh, gọi service, nhờ presentation dựng tin.
"""
import html
import re
import sys

from domain.chitieu.kinds import INCOME
from domain.common.text import plain
from infrastructure import ai as ai_client
from interface.chitieu import bot as chitieu_bot
from domain.common.dates import add_months  # noqa: F401
from domain.common.format import vnd
from domain.common.money import number, parse_amount  # noqa: F401
from domain.common.text import plain
from domain.luong.salary import Salary
from domain.taisan.kinds import ALIASES, FX_CODES, TYPES  # noqa: F401
from domain.taisan.rules import accrued, find_item, is_etf, money_and_name, removable, stock_price  # noqa: F401
from domain.taisan.text import gain_line, gold_amount, gold_name, qty_text, short  # noqa: F401
from domain.taisan.trade import BROKER_FEE, SELL_TAX, parse_trade  # noqa: F401
from infrastructure import clock
from infrastructure import quickchart
from interface import common
from interface.no import debt as sono
from presentation.taisan import view as pview
from presentation.taisan.view import BUTTONS, USAGE, gain_text, gold_lines  # noqa: F401
from repositories.chitieu import ledger as ledger_repo
from repositories.luong import salary as salary_repo
from repositories.taisan import assets as assets_repo
from repositories.vang import gold as gold_repo
from services.taisan import declare, health as health_service
from services.taisan.accounts import (can_be_main, find_account, main_account, main_balance, main_flows,  # noqa: F401
                                      move_main, pick_main, pin_balance, same_name, set_main)
from services.taisan.declare import add_fx, add_gold, add_holding, add_saving, add_saving_item, add_simple  # noqa: F401
from services.taisan.flows import monthly_flows  # noqa: F401
from services.taisan.prices import (SOURCES, coin_prices, fund_navs, fx_rates, gold_table, prices,  # noqa: F401
                                    stock_prices)
from services.taisan.reminders import maturity_notes, salary_due  # noqa: F401
from services.taisan.sales import (remove_by_id, close_saving, collect_loan, realize, remove_named, sell_fund,  # noqa: F401
                                   sell_gold)
from services.taisan.trade import broker_cash, trade  # noqa: F401
from services.taisan.valuation import compare_line, history, pending_orders, snapshot, valuation  # noqa: F401


def now_vn():
    return clock.now_vn()


def today():
    return clock.now_vn().date()


def load():
    return assets_repo.load()


def save(data):
    assets_repo.save(data)


def new_id(data):
    return assets_repo.new_id(data)


@common.needs_store
def taisan(args):
    word = plain(args[0]) if args else ""
    if word in ("xoa", "sua"):
        return edit_list()
    if word in ("bieudo", "bd"):
        return chart_reply(today())
    if word in ("huongdan", "help", "?"):
        return pview.USAGE
    kind = ALIASES.get(word) or ("ngoaite" if word in FX_CODES else None)
    if not args:
        return overview(today())
    if not kind:
        return pview.USAGE
    data = assets_repo.load()
    rest = args[1:]
    if kind == "vang":
        result = declare.add_gold(rest)
    elif kind == "tietkiem":
        result = declare.add_saving(data, rest)
    elif kind in ("cp", "etf", "quy", "coin"):
        result = declare.add_holding(data, kind, rest)
    elif kind == "ngoaite":
        result = declare.add_fx(data, word, rest)
    else:
        result = declare.add_simple(data, kind, rest)
    if not result:
        return pview.USAGE
    if result.startswith("✅") and kind != "vang":
        assets_repo.save(data)
    return result + "\nXem tổng: /taisan"


def overview(day, fresh=False):
    v = valuation(day, fresh)
    if not v["rows"]:
        return pview.USAGE
    text, buttons = pview.overview_view(v, day, compare_line(day, v["net"]), gold_repo.load())
    snapshot(day, v)
    return text, buttons


def edit_list():
    v = valuation(today())
    return pview.edit_list_view(v)


def remove(rid):
    return remove_by_id(rid)


def chart_reply(day):
    v = valuation(day)
    pie = pview.pie_chart(v)
    if pie is None:
        return "Chưa có tài sản nào để vẽ. " + pview.USAGE
    try:
        images = [quickchart.chart_png(pie)]
        past = history()
        if len(past) >= 2:
            images.append(quickchart.chart_png(pview.line_chart(past), 900, 450))
    except Exception as e:
        print(f"[lỗi] vẽ biểu đồ tài sản: {e!r}", file=sys.stderr)
        return "⚠️ Chưa vẽ được biểu đồ (dịch vụ vẽ không trả lời), thử lại sau"
    return {"photos": images, "caption": pview.chart_caption(v)}


def main_line(day=None):
    """'🏦 VCB ~12,3tr' cho màn hình tổng quan; None nếu chưa chọn."""
    it = main_account()
    return pview.main_line_text(it, main_balance(it, day)) if it else None


def main_text(day):
    it = main_account()
    if not it:
        return choose_main()
    income, spend = main_flows(it, day)
    return pview.main_view(it, income, spend, main_balance(it, day))


def choose_main():
    data = assets_repo.load()
    options = [(it, main_balance(it) if it.get("chinh") else it["tien"]) for it in data["items"] if can_be_main(it)]
    return pview.choose_main_view(options)


def health_checks(day):
    """[(điểm 0–20 hoặc None nếu thiếu dữ liệu, dấu, dòng mô tả)] và dữ liệu thô cho AI."""
    return health_service.health_checks(day, sono.health_check)


@common.needs_store
def luong(args):
    usage = ("Nhắc ngày nhận lương: /luong 10 25tr (ngày 10 hằng tháng, 25 triệu)\nTới ngày, bot hỏi đã nhận chưa, "
             "bấm một nút là ghi vào Thu nhập. Bỏ nhắc: /luong xoa")
    if not args:
        s = salary_repo.load()
        return (f"💼 Đang nhắc lương ngày {s.day} hằng tháng, {vnd(s.amount)}\n" + usage) if s else usage
    if plain(args[0]) == "xoa":
        salary_repo.clear()
        return "Đã bỏ nhắc lương"
    found = parse_amount(" ".join(args[1:])) if len(args) > 1 else None
    if not args[0].isdigit() or not 1 <= int(args[0]) <= 31 or not found:
        return usage
    salary_repo.save(Salary(int(args[0]), found[0]))
    return f"✅ Ngày {int(args[0])} hằng tháng bot sẽ hỏi đã nhận lương {vnd(found[0])} chưa"


@common.needs_store
def health(day):
    checks, v, (spend, income, days) = health_checks(day)
    scored = [c for c in checks if c[0] is not None]
    if not scored:
        return "🩺 Chưa đủ dữ liệu để khám. " + pview.USAGE
    score = round(sum(c[0] for c in scored) / (20 * len(scored)) * 100)
    label = "Tốt" if score >= 80 else "Khá" if score >= 60 else "Cần chú ý" if score >= 40 else "Yếu"
    color = {"✅": "🟢", "⚠️": "🟡", "🚨": "🔴"}
    lines = [f"🩺 <b>Sức khỏe tài chính {score}/100</b> ({label})"] + [f"{color.get(mark, mark)} {text}"
                                                                        for _, mark, text in checks]
    if v["rows"]:
        lines.insert(1, f"Tài sản ròng {short(v['net'])}" + (f" · nợ {short(v['debts'])}" if v["debts"] else ""))
    advice = []
    if ai_client.key():
        facts = re.sub(r"<[^>]+>", "", html.unescape("\n".join(lines)))
        system = ("Bạn là trợ lý khám sức khỏe tài chính cá nhân, viết tiếng Việt có dấu, ngắn gọn, xưng \"bạn\". "
                  "Chỉ dựa vào số liệu được cho, không bịa số. Không khuyên mua hay bán mã cổ phiếu, quỹ, tiền số cụ "
                  "thể nào và không dự đoán giá. Trả lời không markdown: 2 dòng bắt đầu bằng \"• \" là nhận xét quan "
                  "trọng nhất; 2–3 dòng bắt đầu bằng \"✅ \" là việc nên làm cụ thể có con số (ví dụ để dành thêm "
                  "3tr/tháng thì sau 8 tháng đủ quỹ dự phòng 6 tháng).")
        try:
            answer, _ = ai_client.chat(system, facts)
            for raw in answer.splitlines():
                raw = raw.strip()
                if raw.startswith(("•", "✅")) and len(advice) < 5:
                    advice.append(html.escape(raw))
        except Exception as e:
            print(f"[lỗi] AI khám sức khỏe: {e!r}", file=sys.stderr)
    if advice:
        lines += ["", "💡 <b>Việc nên làm</b>"] + advice
    return "\n".join(lines)


def on_button(arg, message, now):
    """Nút "ts:...": (thông báo nhỏ, việc tiếp theo) như interface/chitieu/bot.on_button."""
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
        return None, ("send", lambda: pview.USAGE)
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
                 "tien": amount, "ghichu": f"lương tháng {day.month}", "nhom": INCOME}
        ledger_repo.save(entry)
        done = f"✅ Đã ghi lương tháng {day.month}: {vnd(amount)} vào 💰 Thu nhập"
        hint = chitieu_bot.salary_fund_hint([entry], day)  # gợi ý chia lương: trả nợ, chi tiêu, quỹ dự phòng
        return "Đã ghi lương", ("edit", lambda: (done + "\n" + hint[0], [hint[1]]) if hint else done)
    if arg == "chua":
        return "Mai bot hỏi lại", ("edit", lambda: "Chưa nhận lương: mai bot hỏi lại (tối đa 3 ngày)")
    return None, None
