"""Hiểu mình tiêu thế nào: lệnh /dubao, /hoi, /bieudo, /nhanxet, dòng phụ sau khi ghi, cảnh báo tối.

Mọi con số do code tính từ sổ chi tiêu (services/phantich). AI, nếu bật, chỉ làm hai việc: hiểu câu hỏi thành bộ lọc
(khoảng ngày, nhóm, từ khóa) và viết nhận xét từ số liệu đã tính sẵn. AI lỗi hay hết lượt thì bot vẫn trả lời bằng cách
hiểu câu hỏi đơn giản hơn, hoặc chỉ đưa số liệu. Các hàm giữ tên và dạng giá trị trả về mà menu, trợ lý, tin sáng/tối,
chia lương, quỹ dự phòng đang gọi.
"""
import html
import re
import sys

from domain.chitieu import classify
from domain.chitieu.kinds import INCOME
from domain.common.format import short  # noqa: F401
from domain.phantich import numbers, query
from domain.phantich.numbers import (DAILY_DEFAULT, LARGE, SPIKE_MIN, SPIKE_RATIO, SURGE_MIN, SURGE_RATIO,  # noqa: F401
                                     UNUSUAL_MIN, UNUSUAL_RATIO, spending, total)
from domain.phantich.query import (KINDS, QUESTION_ENDS, QUESTION_WORDS, is_question, matches, month_of,  # noqa: F401
                                   month_range, periods_in, previous_span, same_period)
from infrastructure import ai, quickchart
from interface import common
from interface.chitieu.context import config, find_group, period, today
from presentation.kehoach import plan as kehoach_view
from presentation.phantich import view
from presentation.phantich.view import (HOI_HELP, PALETTE, approx, budget_line, dmy, habit_text, span_text,  # noqa: F401
                                        times, trend, weekday_lines)
from repositories.chitieu import budget as budget_repo
from services.phantich import analysis as service
from services.phantich.analysis import (about_spending, allowance, clean_spec, daily_forecast, daily_groups,  # noqa: F401
                                        daily_spent, forecast, habits, rule_spec, spendable, spike_limits, spec_for)
from services.phantich.analysis import ai_spec  # noqa: F401


def note_of(e):
    return view.note_of(e, config())


def daily_label(codes):
    return view.daily_label(codes, config())


def vnd_round(x):
    return view.vnd_round(x)


def chart_png(chart, width=800, height=500):
    """Vẽ biểu đồ Chart.js thành ảnh PNG bằng QuickChart."""
    return quickchart.chart_png(chart, width, height)


def spend_lines(day):
    """Dòng "mỗi ngày được tiêu" cho /dubao: con số chung và cách tính, hoặc cách để có con số đó."""
    s = spendable(day)
    if not s:
        return ["<i>Nhắn «+ lương 19tr» hoặc «ngân sách tổng 15tr» để biết mỗi ngày được tiêu bao nhiêu</i>"]
    return [kehoach_view.spend_text(s, bold=True), f"<i>{kehoach_view.basis_text(s)}</i>"]


@common.needs_store
def forecast_text(day):
    return view.forecast_view(forecast(day), day, lambda: spend_lines(day), config())


@common.needs_store
def daily_text(day):
    return view.daily_view(daily_forecast(day), day, lambda: spend_lines(day), config())


def dubao(args):
    """/dubao: chi tiêu hằng ngày; /dubao tatca: mọi khoản; /dubao nhom ...: chọn nhóm tính là hằng ngày."""
    from domain.common.text import plain
    word = plain(args[0]) if args else ""
    if word in ("tatca", "het", "tong"):
        return forecast_text(today())
    if word == "nhom":
        rest = " ".join(args[1:]).strip()
        if not rest:
            return (f"Đang tính là chi tiêu hằng ngày: {html.escape(daily_label(daily_groups()))}\n"
                    "Đổi: /dubao nhom ăn uống, đi chợ, đi lại · về mặc định: /dubao nhom macdinh")
        if plain(rest) in ("macdinh", "mac dinh"):
            service.reset_daily_groups()
            return f"✅ Về mặc định: {html.escape(daily_label(daily_groups()))}"
        codes, unknown = [], []
        for part in re.split(r"[,;]", rest):
            if part.strip():
                code = find_group(part)
                (codes if code and code != INCOME else unknown).append(code or part.strip())
        if unknown or not codes:
            return "Không thấy nhóm: " + html.escape(", ".join(unknown or [rest])) + ". Xem tên nhóm: /nhom"
        service.set_daily_groups(codes)
        return f"✅ Dự báo hằng ngày giờ tính: {html.escape(daily_label(daily_groups()))}\nXem: /dubao"
    return daily_text(today())


def unusual_lines(entries, day):
    """Khoản vừa ghi lớn bất thường so với mức thường của nhóm (trung vị 90 ngày, cần từ 5 khoản)."""
    return view.unusual_lines(service.unusual_data(entries, day), config())


def after_record(entries, day):
    """Dòng thêm dưới tin "Đã ghi": khoản lạ thường; đã đặt ngân sách hằng ngày (hoặc ngân sách các nhóm hằng ngày)
    thì hôm nay còn bao nhiêu theo chi tiêu hằng ngày, đã đặt ngân sách tổng thì theo con số chung. Không đặt ngân
    sách thì không thêm dòng (con số theo kế hoạch xem ở 🏠 Hôm nay)."""
    lines = unusual_lines(entries, day)
    codes = daily_groups()
    budgets = budget_repo.load()
    if any(e["nhom"] in codes for e in entries) and ("hangngay" in budgets or all(c in budgets for c in codes)):
        f = daily_forecast(day)
        if f["room"]:
            lines.append(kehoach_view.room_text(*f["room"], what="ngân sách hằng ngày").replace("Hôm nay", "Chi hằng ngày"))
            return lines
    if any(e["nhom"] != INCOME for e in entries) and budgets.get("tong"):  # có ngân sách tổng mới hiện
        s = spendable(day)
        if s:
            lines.append(kehoach_view.spend_text(s))
    return lines


def alerts(day):
    """Việc tối: nhóm tiêu tăng vọt 7 ngày qua, nhóm đang trên đà vượt ngân sách. Mỗi chuyện chỉ báo một lần mỗi tuần
    (đánh dấu trong kho)."""
    rises, overs = service.alerts_data(day)
    return view.alert_lines(rises, overs, config(), habits)


def by_group_lines(items, limit=8):
    return view.by_group_lines(items, config(), limit)


def run_query(spec, day):
    items, other = service.query_items(spec)
    return view.query_view(spec, items, other, config())


@common.needs_store
def hoi(question, day):
    """Trả lời câu hỏi về chi tiêu. AI (nếu bật) hiểu câu hỏi; AI lỗi thì hiểu theo cách đơn giản."""
    question = question.strip()
    if not question:
        return HOI_HELP
    return run_query(spec_for(question, day), day)


def color(code):
    return view.color(code, service.chart_colors_codes())


def charts(start, end, label):
    """[ảnh tròn theo nhóm, ảnh cột theo ngày] của khoản chi trong kỳ."""
    items = service.spending_between(start, end)
    pie, bars, whole = view.chart_configs(items, start, end, label, config(), service.chart_colors_codes())
    images = [chart_png(pie)]
    if bars:
        images.append(chart_png(bars, 900, 450))
    return images, whole


@common.needs_store
def chart_reply(kind, day):
    start, end, label, *_ = period(kind, day)
    if not service.spending_between(start, end):
        return f"Chưa có khoản chi nào trong {label} để vẽ biểu đồ"
    try:
        images, whole = charts(start, end, label)
    except Exception as e:
        print(f"[lỗi] vẽ biểu đồ: {e!r}", file=sys.stderr)
        return "⚠️ Chưa vẽ được biểu đồ (dịch vụ vẽ không trả lời), thử lại sau hoặc xem /thang"
    return {"photos": images, "caption": f"📈 <b>Chi tiêu {label}</b>: {view.vnd_round(whole)}"}


def facts(kind, day):
    """(tên kỳ, các dòng số liệu HTML) để người dùng đọc và để AI viết nhận xét."""
    data = service.facts_data(kind, day)
    return data["label"], view.facts_lines(data, config())


@common.needs_store
def commentary(kind, day):
    """Số liệu của kỳ + nhận xét của AI (3 điểm đáng chú ý, 1 gợi ý tiết kiệm có con số)."""
    label, lines = facts(kind, day)
    if not lines:
        return f"Chưa có khoản chi nào trong {label} để nhận xét"
    if not ai.key():
        return view.commentary_view(label, lines, [])
    plain_facts = re.sub(r"<[^>]+>", "", html.unescape("\n".join(lines)))
    return view.commentary_view(label, lines, service.commentary_notes(label, plain_facts))


vnd = view.vnd_round  # giữ tên cũ: làm tròn rồi hiện đồng
