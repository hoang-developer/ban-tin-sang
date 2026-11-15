"""Khám sức khỏe tài chính: chấm 5 mục từ số liệu của chính bạn (quỹ dự phòng, để dành, nợ, phân bổ, lỗ). Câu mô tả
còn nằm trong module này (tách sang presentation sau). Chấm nợ do nơi gọi đưa vào (debt_check) để không phụ thuộc lớp trên."""
import html
import sys

from domain.common.format import short, vn_num
from domain.taisan.kinds import TYPES
from repositories.taisan import assets as assets_repo
from services.taisan import flows, valuation


def health_checks(day, debt_check):
    """[(điểm 0–20 hoặc None nếu thiếu dữ liệu, dấu, dòng mô tả)] và dữ liệu thô cho AI."""
    v = valuation.valuation(day)
    spend, income, days = flows.monthly_flows(day)
    checks = []
    kinds = {}
    for kind, _, _, value, _, _ in v["rows"]:
        kinds[kind] = kinds.get(kind, 0) + value
    liquid = kinds.get("tien", 0) + kinds.get("tietkiem", 0)
    fund = None
    if any(it.get("duphong") for it in assets_repo.load()["items"]):  # đã lập quỹ dự phòng: dùng đúng số liệu của quỹ
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
        checks.append(debt_check(day, v, income if income and days >= 20 else None))  # nợ: chấm theo tiền trả mỗi tháng
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
        trend = valuation.compare_line(day, v["net"])
        score = 20 if not losers else 10
        checks.append((score, "✅" if not losers else "⚠️",
                       ("Lỗ ≥ 20%: " + ", ".join(losers) if losers else "Không khoản nào lỗ ≥ 20%")
                       + (f" · tài sản ròng{trend}" if trend else "")))
    else:
        checks.append((None, "❔", "Nợ, phân bổ: chưa khai báo tài sản"))
    return checks, v, (spend, income, days)
