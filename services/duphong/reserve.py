"""Quỹ dự phòng: các việc người dùng làm (xem tình trạng, nạp, rút, tính tài sản vào quỹ, đổi cấu hình).

Chi thiết yếu mỗi tháng tính từ sổ chi tiêu 90 ngày qua: ăn uống, đi chợ, đi lại (bỏ khoản đột biến), nhà cửa và hóa đơn,
sức khỏe, học tập, gia đình. Nhà, hóa đơn, học tính theo tháng (không nhân theo ngày). Không tính mua sắm, giải trí, quà,
tiền trả nợ (nợ đã có kế hoạch trả riêng ở /no)... Tự đặt được: /duphong chi 12tr.
Số dư quỹ là các tài sản trong /taisan được gắn vào quỹ. Trả kết quả có cấu trúc (domain.duphong.reserve), không trả chữ.
"""
from datetime import date, timedelta

from domain.chitieu import classify
from domain.phantich import numbers as phantich_numbers
from services.phantich import analysis as phantich_service
from repositories.chitieu import ledger as ledger_repo
from services.chitieu import groups as chitieu_groups
from repositories.taisan import assets as assets_repo
from services.taisan import accounts, flows
from services.taisan import valuation as valuation_service
from domain.duphong import reserve as rules
from domain.duphong.reserve import Change, Toggle
from repositories.duphong import reserve as reserve_repo


def essential_groups():
    return [c for c in rules.ESSENTIAL if c in chitieu_groups.groups()]


def essential(day):
    """(chi thiết yếu/tháng, {nhóm: chi/tháng}, số ngày dữ liệu). Nhóm hằng ngày bỏ khoản đột biến; tiền nhà, hóa
    đơn... tính đủ vì tháng nào cũng có. Tiền trả nợ không tính (đã có kế hoạch trả nợ riêng)."""
    codes = essential_groups()
    items = [e for e in phantich_numbers.spending(ledger_repo.between(day - timedelta(days=89), day))
             if e["nhom"] in codes and not classify.is_debt_payment(e["ghichu"])]  # trả nợ, đóng thẻ không phải chi thiết yếu
    if not items:
        return 0, {}, 0
    daily = [c for c in phantich_service.daily_groups() if c in codes] + [c for c in ("khoe", "giadinh") if c in codes]
    limits = phantich_numbers.spike_limits(items, daily)
    kept = [e for e in items if e["nhom"] not in limits or e["tien"] < limits[e["nhom"]]]
    days = (day - date.fromisoformat(min(e["ngay"] for e in items))).days + 1
    by_group = {}
    for e in kept:
        by_group[e["nhom"]] = by_group.get(e["nhom"], 0) + e["tien"]
    bill_months = {c: len({e["ngay"][:7] for e in kept if e["nhom"] == c}) for c in rules.MONTHLY_BILLS}
    monthly = rules.monthly_amounts(by_group, set(rules.MONTHLY_BILLS), days, bill_months)
    by_group = dict(sorted(monthly.items(), key=lambda x: -x[1]))
    return sum(by_group.values()), by_group, days


def fund_rows(day):
    """Các tài sản tính vào quỹ: [(tên, giá trị)] theo giá/lãi hiện tại."""
    data = assets_repo.load()
    ids = {str(it["id"]) for it in data["items"] if it.get("duphong")}
    if not ids:
        return []
    return [(name, value) for kind, rid, name, value, _, _ in valuation_service.valuation(day)["rows"] if rid in ids]


def status(day):
    """ReserveStatus của quỹ tại ngày day."""
    essentials = essential(day)
    rows = fund_rows(day)
    labels = {c: chitieu_groups.name(c) for c in essentials[1]}
    other = any(not accounts.same_name(n, rules.FUND_NAME) for n, _ in rows)
    return rules.build_status(reserve_repo.load(), day, essentials, rows, flows.monthly_flows(day), labels, other)


def fund_item(data):
    item = next((it for it in data["items"] if it["loai"] == "tien" and accounts.same_name(it["ten"], rules.FUND_NAME)), None)
    if item is None:
        item = {"id": assets_repo.new_id(data), "loai": "tien", "ten": rules.FUND_NAME, "tien": 0, "ngay": chitieu_groups.today().isoformat(),
                "duphong": True}
        data["items"].append(item)
    item["duphong"] = True
    return item


def change(amount, day, from_main=True):
    """Thêm (amount > 0) hoặc rút (amount < 0) tiền ở tài khoản "Quỹ dự phòng". Có tài khoản chính thì tiền đi từ đó
    (rút thì về đó); from_main=False: tiền có sẵn, không trừ tài khoản nào."""
    data = assets_repo.load()
    item = fund_item(data)
    before = status(day)
    old = item["tien"]
    item["tien"] = max(0, item["tien"] + amount)
    item["ngay"] = day.isoformat()
    moved = accounts.move_main(data, old - item["tien"], "quỹ dự phòng", day) if from_main else None
    assets_repo.save(data)
    reserve_repo.save(rules.record_deposit(reserve_repo.load(), day, item["tien"] - old))  # số thật đã đổi (rút quá số dư thì bị chặn ở 0)
    after = status(day)
    return Change(amount, before, after, moved, rules.milestone(before, after) if amount >= 0 else None)


KINDS = ("tien", "tietkiem", "quy")


def toggle(name):
    """Tính (hoặc bỏ) tài sản tên name vào quỹ dự phòng."""
    data = assets_repo.load()
    target = next((it for it in data["items"] if it["loai"] in KINDS
                   and accounts.same_name(it.get("ten") or it.get("ma", ""), name)), None)
    if not target:
        return Toggle(name, False, available=[it.get("ten") or it.get("ma") for it in data["items"] if it["loai"] in KINDS])
    target["duphong"] = not target.get("duphong")
    assets_repo.save(data)
    return Toggle(name, True, label=target.get("ten") or target.get("ma"), enabled=target["duphong"])


def savings_books():
    """[(tên sổ, lãi %/năm, đã tính vào quỹ)] các sổ tiết kiệm đã khai báo."""
    return [(it["ten"], it["lai"], bool(it.get("duphong"))) for it in assets_repo.load()["items"] if it["loai"] == "tietkiem"]


def set_months(n):
    reserve_repo.save({**reserve_repo.load(), "thang": n})


def set_deadline(n, day):
    reserve_repo.save({**reserve_repo.load(), "han": n, "bat_dau": day.isoformat()})


def set_monthly(amount):
    reserve_repo.save({**reserve_repo.load(), "chi": amount})


def clear_monthly():
    cfg = reserve_repo.load()
    cfg.pop("chi", None)
    reserve_repo.save(cfg)
