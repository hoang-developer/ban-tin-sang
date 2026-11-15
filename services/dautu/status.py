"""Tình trạng kỳ đầu tư quỹ đang mở: chốt kỳ đã qua, tính kế hoạch/giá trị/số nên mua (dict `status`)."""
import sys

from domain.dautu.plan import (STEP, MIN_ORDER, contributed_of, goes_main, holding, pending_main, side, target,
                               total_of, wait_name)
from domain.dautu.calendar import months, ym_add
from repositories.dautu import fund as fund_repo
from repositories.taisan import assets as assets_repo
from services.dautu import market
from services.dautu.market import current_period, nav_history


def wait_item(data, cfg):
    """Tài khoản tiền "Quỹ chờ <mã>" trong /taisan (tạo nếu chưa có)."""
    item = next((it for it in data["items"] if it["loai"] == "tien" and it.get("dautu")), None)
    if item is None:
        item = {"id": assets_repo.new_id(data), "loai": "tien", "ten": wait_name(cfg), "tien": 0,
                "ngay": market.now_vn().date().isoformat(), "dautu": True}
        data["items"].append(item)
    return item


def close_periods(cfg, now=None):
    """Chốt các kỳ đã qua hạn: góp của tháng (phần chưa để) được tính vào quỹ chờ, trừ tháng tạm dừng.
    Trả True nếu có thay đổi (đã lưu)."""
    current = current_period(cfg, now)
    changed = False
    data = value = None
    for ym in months(cfg["bat_dau"], ym_add(current, -1)):
        k = cfg.setdefault("ky", {}).setdefault(ym, {})
        if k.get("chot"):
            continue
        if data is None:
            data = assets_repo.load()
            navs = nav_history(cfg)
            hold = holding(data, cfg)
            value = (hold["sl"] * navs[-1][1] if hold and navs else 0) + sum(
                o["tien"] for o in cfg.get("lenh", []) if pending_main(cfg, o))
        unpaid = max(0, total_of(cfg, ym) - cfg.get("nap", {}).get(ym, 0))
        if unpaid:
            wait_item(data, cfg)["tien"] += unpaid
            cfg.setdefault("nap", {})[ym] = cfg.get("nap", {}).get(ym, 0) + unpaid
        k.update({"chot": True, "muc": round(target(cfg, ym)), "gt": round(value)})  # gt: giá trị lúc chốt (biểu đồ)
        changed = True
    if changed:
        if data:
            assets_repo.save(data)
        fund_repo.save(cfg)
    return changed


def status(cfg, now=None, fresh=False):
    """Số liệu kỳ đang mở: kế hoạch, giá trị, cần mua, có bao nhiêu, nên mua bao nhiêu..."""
    now = now or market.now_vn()
    close_periods(cfg, now)
    navs = nav_history(cfg, fresh)
    data = assets_repo.load()
    ym = current_period(cfg, now)
    hold = holding(data, cfg)
    units = hold["sl"] if hold else 0
    nav_day, nav = navs[-1] if navs else (None, None)
    orders = cfg.get("lenh", [])
    pending = sum(o["tien"] for o in orders if pending_main(cfg, o))
    value = units * nav + pending if nav else pending + (units * hold["gia_von"] if hold and hold.get("gia_von") else 0)
    plan = target(cfg, ym)
    k = cfg.get("ky", {}).get(ym) or {}
    cash = next((it["tien"] for it in data["items"] if it["loai"] == "tien" and it.get("dautu")), 0)
    unpaid = 0 if k.get("bo") else max(0, total_of(cfg, ym) - cfg.get("nap", {}).get(ym, 0))
    money_now = cash + unpaid  # tiền mặt dùng được ngay (chưa đặt lệnh)
    sd = side(cfg)
    side_value = side_nav = side_day = None
    if sd:
        snavs = nav_history(sd, fresh)
        side_day, side_nav = snavs[-1] if snavs else (None, None)
        sh = holding(data, cfg, sd["ma"])
        side_units = (sh["sl"] if sh else 0) - sum(o["ccq_ra"] for o in orders if o["trang_thai"] == "cho"
                                                    and o.get("loai") == "doi")
        side_value = max(0.0, side_units) * (side_nav or 0) + sum(
            o["tien"] for o in orders if o["trang_thai"] == "cho" and o.get("quy") == sd["ma"] and o.get("loai") != "doi")
    available = money_now + (side_value or 0)
    need = plan - value
    buy = max(0, min(need, available)) // STEP * STEP
    buy = 0 if buy < MIN_ORDER else buy
    direct = min(buy, money_now) // STEP * STEP  # mua thẳng bằng tiền góp trước
    switch = buy - direct
    if sd and switch and switch < MIN_ORDER:  # phần thiếu quá nhỏ: khỏi hoán đổi
        buy, switch = direct, 0
    if not sd:
        direct, switch = buy, 0
    side_buy = (money_now - direct) // STEP * STEP if sd and not k.get("bo") else 0
    side_buy = side_buy if side_buy >= MIN_ORDER else 0
    switch_units = (int(switch / side_nav * 100) + 1) / 100 if switch and side_nav else 0
    ordered = sum(o["tien"] for o in orders if o["ky"] == ym)
    invested = sum(o["tien"] for o in orders if goes_main(cfg, o))
    cost = units * hold["gia_von"] if hold and hold.get("gia_von") else 0
    year_ago = [v for d, v in navs if nav_day and (nav_day - d).days <= 365]
    peak = max(year_ago) if year_ago else None
    month_start = [v for d, v in navs if nav_day and d < nav_day.replace(day=1)]
    fund = None
    try:
        from services.duphong import reserve as reserve_service
        fund = reserve_service.status(now.date())
    except Exception as e:
        print(f"[lỗi] quỹ dự phòng trong /dautu: {e!r}", file=sys.stderr)
    return {"ym": ym, "plan": plan, "value": value, "units": units, "nav": nav, "nav_day": nav_day, "pending": pending,
            "cash": cash, "unpaid": unpaid, "available": available, "need": need, "buy": buy, "skip": k.get("bo"),
            "direct": direct, "switch": switch, "switch_units": switch_units, "side_buy": side_buy, "side": sd,
            "side_value": side_value, "side_nav": side_nav, "side_day": side_day, "money_now": money_now,
            "short": need > available + STEP, "ordered": ordered, "invested": invested, "cost": cost,
            "contributed": contributed_of(cfg),
            "drawdown": nav / peak - 1 if peak and nav else None,
            "month_change": nav / month_start[-1] - 1 if month_start and nav else None,
            "fund": fund, "below_milestone": bool(fund and fund.monthly and fund.covered < 1)}
