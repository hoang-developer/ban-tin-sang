"""Phân tích chi tiêu: đọc sổ rồi tính dự báo tháng, dự báo hằng ngày, khoản lạ thường, cảnh báo tối (có đánh dấu đã báo),
hiểu và trả lời câu hỏi (AI hiểu câu, lỗi thì hiểu theo luật), số liệu vẽ biểu đồ và viết nhận xét.
Mọi con số do code tính; AI chỉ hiểu câu hỏi thành bộ lọc và viết nhận xét từ số liệu đã tính."""
import re
import sys
from datetime import timedelta

from domain.chitieu import classify
from domain.chitieu.kinds import INCOME, OTHER
from domain.common.dates import WEEKDAYS
from domain.phantich import numbers, query
from infrastructure import ai
from repositories.chitieu import analysis as analysis_repo
from repositories.chitieu import budget as budget_repo
from repositories.chitieu import groups as groups_repo
from repositories.chitieu import ledger as ledger_repo
from services.kehoach import plan as kehoach_service

spending, total, spike_limits, allowance = numbers.spending, numbers.total, numbers.spike_limits, numbers.allowance


def forecast(day):
    """Số liệu dự báo tháng của ngày day (dict), dùng cho /dubao, dòng sau khi ghi và cảnh báo tối."""
    items = spending(ledger_repo.between(numbers.forecast_start(day), day))
    return numbers.forecast_numbers(day, items, budget_repo.load())


def daily_groups():
    """Các nhóm tính là chi tiêu hằng ngày: người dùng chọn, mặc định ăn uống, đi chợ/siêu thị, đi lại."""
    return numbers.daily_codes(analysis_repo.daily_groups(), groups_repo.config())


def daily_forecast(day):
    """Dự báo tháng chỉ cho chi tiêu hằng ngày, bỏ khoản đột biến."""
    codes = daily_groups()
    items = spending(ledger_repo.between(numbers.daily_start(day), day))
    return numbers.daily_numbers(day, items, codes, budget_repo.load())


def daily_spent(day):
    """Đã chi hằng ngày (bỏ khoản đột biến) tháng này: cho dòng ngân sách "hằng ngày" ở sổ chi tiêu."""
    return daily_forecast(day)["spent"]


def spendable(day):
    """Mỗi ngày được tiêu (một con số chung, xem kehoach.spendable); None nếu chưa tính được."""
    return kehoach_service.spendable_safe(day)


def set_daily_groups(codes):
    analysis_repo.save_daily_groups(list(dict.fromkeys(codes)))


def reset_daily_groups():
    analysis_repo.reset_daily_groups()


def unusual_data(entries, day):
    """Khoản vừa ghi lớn bất thường so với mức thường của nhóm (trung vị 90 ngày): [(khoản, mức thường)]."""
    if not any(e["nhom"] not in (INCOME, OTHER) and e["tien"] >= numbers.UNUSUAL_MIN for e in entries):
        return []
    ids = {e["id"] for e in entries}
    history = [e for e in spending(ledger_repo.between(day - timedelta(days=90), day)) if e["id"] not in ids]
    return numbers.unusual(entries, history)


def alerts_data(day):
    """Việc tối: ({nhóm tăng vọt 7 ngày qua}, {nhóm đang trên đà vượt ngân sách}); mỗi chuyện chỉ báo một lần mỗi tuần
    (đánh dấu trong kho). Trả ([(mã, 7 ngày qua, mức thường, khoản)], [(mã, số liệu ngân sách)], dự báo)."""
    items = spending(ledger_repo.between(day - timedelta(days=34), day))
    rises = [r for r in numbers.surges(items, day, list(classify.groups(groups_repo.config())))
             if analysis_repo.claim_rise(r[0])]
    f = forecast(day)
    overs = []
    for code, b in f["budgets"].items():
        if b["spent"] < b["limit"] < b["projected"] and f["history"] >= 7 \
                and analysis_repo.claim_budget(code, f"{day:%Y-%m}"):
            overs.append((code, b))
    return rises, overs


def habits(items):
    """Gộp khoản cùng nội dung (bỏ số, ngày): [(nội dung, số lần, tổng tiền)] nhiều tiền nhất trước."""
    cfg = groups_repo.config()
    return numbers.habits(items, lambda code: classify.bare(classify.name(code, cfg)))


# ---- Hỏi bằng câu thường ---------------------------------------------------------------

def ai_spec(question, day):
    """Nhờ AI hiểu câu hỏi thành bộ lọc JSON; số liệu vẫn do code tính."""
    cfg = groups_repo.config()
    groups = "\n".join(f"{code}: {classify.bare(label)}" for code, (label, _, _) in classify.groups(cfg).items()
                       if code != INCOME)
    system = (
        f"Hôm nay là {WEEKDAYS[day.weekday()]} {day:%d/%m/%Y}. Chuyển câu hỏi về sổ chi tiêu cá nhân thành một "
        "dòng JSON, không giải thích:\n"
        '{"kieu": "tong" | "nhom" | "lon_nhat" | "liet_ke" | "so_sanh" | "theo_ngay", "tu": "YYYY-MM-DD", '
        '"den": "YYYY-MM-DD", "tu2": "YYYY-MM-DD", "den2": "YYYY-MM-DD", "nhom": [mã nhóm], '
        '"tu_khoa": [chữ trong ghi chú], "thu": true/false}\n'
        "- tong: tổng tiền; nhom: chia theo nhóm (tiêu vào đâu, nhóm nào nhiều nhất); lon_nhat: các khoản lớn "
        "nhất; liet_ke: liệt kê từng khoản (mấy lần, những khoản nào); so_sanh: so kỳ tu–den với kỳ tu2–den2 "
        "(thường là kỳ trước đó); theo_ngay: theo từng ngày (ngày nào tiêu nhiều).\n"
        "- Tuần tính từ thứ Hai. \"Tháng này\" là từ ngày 1 tới hôm nay, \"tháng trước\" là cả tháng trước. "
        "Không nói thời gian thì là tháng này. tu2/den2 chỉ dùng cho so_sanh.\n"
        "- nhom: chỉ điền khi hỏi cả một nhóm. Món cụ thể (cà phê, xăng, trà sữa, Grab...) thì để vào tu_khoa, "
        "kèm các cách viết hay gặp (vd [\"cà phê\", \"cafe\", \"coffee\"]).\n"
        "- thu: true nếu hỏi tiền thu vào (lương, thu nhập).\nCác nhóm (mã: tên):\n" + groups)
    text, _ = ai.chat(system, question)
    raw = ai.first_json(text)
    if not isinstance(raw, dict):
        raise RuntimeError(f"AI trả lời không đúng dạng: {text[:100]!r}")
    return query.clean_spec(raw, day, cfg)


def spec_for(question, day):
    """Bộ lọc của câu hỏi: AI (nếu bật) hiểu câu hỏi; AI lỗi thì hiểu theo luật đơn giản."""
    spec = None
    if ai.key():
        try:
            spec = ai_spec(question, day)
        except Exception as e:
            print(f"[lỗi] AI hiểu câu hỏi: {e!r}", file=sys.stderr)
    return spec or query.rule_spec(question, day, groups_repo.config(), groups_repo.learned())


def rule_spec(question, day):
    return query.rule_spec(question, day, groups_repo.config(), groups_repo.learned())


def clean_spec(raw, day):
    return query.clean_spec(raw, day, groups_repo.config())


def query_items(spec):
    """(các khoản khớp bộ lọc trong kỳ, các khoản khớp trong kỳ đem so hoặc None nếu không phải câu so sánh)."""
    items = [e for e in ledger_repo.between(spec["tu"], spec["den"]) if query.matches(e, spec)]
    other = None
    if spec["kieu"] == "so_sanh":
        other = [e for e in ledger_repo.between(spec["tu2"], spec["den2"]) if query.matches(e, spec)]
    return items, other


# ---- Biểu đồ và nhận xét ---------------------------------------------------------------

def spending_between(start, end):
    return spending(ledger_repo.between(start, end))


def chart_colors_codes():
    """Thứ tự mã nhóm để tô màu biểu đồ: nhóm có sẵn rồi nhóm tự tạo."""
    from domain.chitieu.categories import CATEGORIES
    return list(CATEGORIES) + list(groups_repo.config().get("moi", []))


def facts_data(kind, day):
    """Số liệu để dựng các dòng số liệu của một kỳ: dict hoặc None nếu kỳ chưa có khoản chi."""
    from domain.chitieu import period as periods
    start, end, label, prev_start, prev_end, prev_label = periods.period(kind, day)
    items = ledger_repo.between(start, end)
    spend = spending(items)
    if not spend:
        return {"label": label, "empty": True}
    prev = spending(ledger_repo.between(prev_start, prev_end))
    olds = []
    if start.day == 1 and kind != "thang":  # cả tháng: so trung bình 3 tháng trước
        d = start
        for _ in range(3):
            d = (d - timedelta(days=1)).replace(day=1)
            month = spending(ledger_repo.between(d, query.month_range(d.year, d.month, day)[1]))
            if month:
                olds.append(total(month))
    return {"label": label, "empty": False, "kind": kind, "start": start, "end": end, "prev_label": prev_label,
            "items": items, "spend": spend, "prev": prev, "olds": olds}


def commentary_notes(label, facts_text):
    """Nhờ AI nhận xét từ số liệu đã tính: [3 điểm đáng chú ý, 1 gợi ý]; AI lỗi thì []."""
    system = ("Bạn là trợ lý tài chính cá nhân, viết tiếng Việt có dấu, ngắn gọn, thân thiện, xưng \"bạn\". "
              "Chỉ dùng số liệu được cho, không bịa thêm số. Trả lời đúng 4 dòng, không markdown: 3 dòng đầu mỗi "
              "dòng bắt đầu bằng \"• \" là 3 điểm đáng chú ý nhất (mỗi dòng dưới 25 chữ); dòng cuối bắt đầu bằng "
              "\"💡 \" là 1 gợi ý tiết kiệm cụ thể có con số, làm được theo đúng số lần trong số liệu (vd trà "
              "sữa 9 lần/tháng thì bớt một nửa để dành thêm khoảng 250k/tháng).")
    try:
        answer, _ = ai.chat(system, f"Số liệu chi tiêu {label}:\n{facts_text}")
        lines_ai = [line.strip() for line in answer.splitlines()]
        bullets = ["• " + re.sub(r"^([-*•]|\d+[.)])\s*", "", x) for x in lines_ai
                   if re.match(r"([-*•]|\d+[.)])\s*\S", x)][:3]  # model có khi đánh dấu "-" hay "1."
        tips = [x for x in lines_ai if x.startswith("💡")][:1]
        return bullets + tips
    except Exception as e:
        print(f"[lỗi] AI nhận xét: {e!r}", file=sys.stderr)
        return []
