"""Ghi lệnh mua/hoán đổi quỹ, góp và rút tiền quỹ chờ, khớp lệnh theo NAV, sửa số ccq, tạm dừng kỳ.
Câu báo cho người dùng còn nằm trong module này (sẽ tách sang presentation ở bước dọn dẹp cuối)."""
import re
from datetime import date, timedelta

from domain.common.format import vn_num, vnd
from domain.common.text import plain
from domain.common.money import number
from domain.dautu.calendar import cutoff_day, read_date, ym_of, ym_text
from domain.dautu.plan import SWITCH_DAYS, goes_main, holding, side
from domain.dautu.text import money, units_text
from repositories.dautu import fund as fund_repo
from repositories.taisan import assets as assets_repo
from services.dautu import market
from services.taisan import accounts
from services.dautu.market import current_period, nav_history, next_trading, session
from services.dautu.status import close_periods, wait_item


def add_money(cfg, amount, ym, data=None, from_main=True, notes=None):
    """Góp thêm vào quỹ chờ (tính là góp của tháng ym). Có tài khoản chính thì tiền đi từ đó (dòng báo thêm vào
    notes nếu đưa vào); from_main=False: tiền có sẵn."""
    own = data is None
    data = data or assets_repo.load()
    item = wait_item(data, cfg)
    item["tien"] += amount
    item["ngay"] = market.now_vn().date().isoformat()
    cfg.setdefault("nap", {})[ym] = cfg.get("nap", {}).get(ym, 0) + amount
    moved = accounts.move_main(data, -amount, f"quỹ chờ {cfg['ma']}") if from_main else None
    if moved and notes is not None:
        notes.append(moved)
    if own:
        assets_repo.save(data)
    return item["tien"]


def take_money(cfg, amount, to_main=True, notes=None):
    """Rút tiền khỏi quỹ chờ (tối đa số đang có), về tài khoản chính nếu có. Trả (số đã rút, quỹ chờ còn)."""
    data = assets_repo.load()
    item = wait_item(data, cfg)
    taken = min(item["tien"], amount)
    item["tien"] -= taken
    moved = accounts.move_main(data, taken, f"rút quỹ chờ {cfg['ma']}") if to_main else None
    if moved and notes is not None:
        notes.append(moved)
    assets_repo.save(data)
    return taken, item["tien"]


def order_spec(cfg, text, now, fund=None):
    """Phần chữ ngoài số tiền của "/dautu dadat", "mua VMEEF": (ngày đặt, phiên khớp, kỳ) hoặc câu báo lỗi.
    Có ngày (9/11): lệnh đặt hôm đó, mặc định trước 14:40 ("sau 14h40" thì sang phiên sau). Không có ngày: vừa đặt
    xong, tính theo giờ hiện tại."""
    day = read_date(text, now.date())
    if day and day > now.date():
        return "Ngày đặt lệnh chưa tới. Gõ ngày bạn đã đặt trên Fmarket, ví dụ: /dautu dadat 1tr 9/11"
    late = bool(re.search(r"sau\s*14", plain(text))) or (day is None and (now.hour, now.minute) >= (14, 40))
    day = day or now.date()
    cutoff = next_trading(cfg, day, include=True)  # đặt cuối tuần, ngày lễ: sổ lệnh đóng ở ngày giao dịch kế tiếp
    if late and cutoff == day:
        cutoff = next_trading(cfg, cutoff)
    return day, next_trading(fund or cfg, cutoff), ym_of(cutoff)  # fund: quỹ chờ có lịch giao dịch riêng


def record_order(amount, trading_day=None, now=None, period=None, order_day=None, fund=None, quiet=False, lump=False,
                 from_main=True):
    """Đã đặt lệnh mua `amount`: trừ quỹ chờ (thiếu thì phần thiếu tính là góp thêm của tháng), ghi lệnh chờ khớp.
    period: kỳ của lệnh (nút bấm mang theo); không có thì suy từ ngày đóng sổ của phiên khớp. fund: mua quỹ chờ (VFF).
    Phần không lấy từ quỹ chờ (phần thiếu, khoản góp một lần) đi từ tài khoản chính nếu có (from_main=False: không)."""
    now = now or market.now_vn()
    order_day = order_day or now.date()
    cfg = fund_repo.load()
    close_periods(cfg, now)
    code = (fund or cfg)["ma"]
    sess = session(fund or cfg, now)
    trading = trading_day or sess["phien"]
    ym = period or (ym_of(cutoff_day(trading_day)) if trading_day else current_period(cfg, now))
    if ym < cfg["bat_dau"]:
        ym = cfg["bat_dau"]
    data = assets_repo.load()
    item = wait_item(data, cfg)
    outside = 0  # phần tiền không lấy từ quỹ chờ
    if lump:  # khoản góp một lần (tiền bán cổ phiếu...): không trừ vào tiền góp hằng tháng
        cfg.setdefault("ngoai", {})[ym] = cfg.get("ngoai", {}).get(ym, 0) + amount
        outside = amount
    elif item["tien"] < amount:
        extra = amount - item["tien"]
        cfg.setdefault("nap", {})[ym] = cfg.get("nap", {}).get(ym, 0) + extra
        item["tien"] = 0
        outside = extra
    else:
        item["tien"] -= amount
    moved = accounts.move_main(data, -outside, f"mua {code}", order_day) if from_main and outside else None
    order = {"id": max([o["id"] for o in cfg.get("lenh", [])] + [0]) + 1, "ky": ym, "tien": amount, "quy": code,
             "loai": "mua", "dat": order_day.isoformat(), "phien": trading.isoformat(), "trang_thai": "cho",
             **({"ngoai": True} if lump else {})}
    cfg.setdefault("lenh", []).append(order)
    assets_repo.save(data)
    fund_repo.save(cfg)
    note = (f"✅ Đã ghi lệnh mua {code} {vnd(amount)}: đặt {order_day:%d/%m} → khớp NAV phiên "
            f"<b>{trading:%d/%m}</b>." + ("" if side(cfg) else f" Quỹ chờ còn {money(item['tien'])}.")
            + (f"\n{moved}" if moved else ""))
    if quiet:
        return note
    matched = match_orders(now)
    if matched:
        return note + "\n" + matched[0]
    return note + " Tối ngày khớp (khoảng 17h có NAV) bot tính số ccq và cộng vào /taisan."


def record_switch(units, trading_day=None, now=None, period=None, order_day=None, quiet=False):
    """Đã đặt lệnh hoán đổi `units` ccq quỹ chờ (VFF) sang quỹ chính: ghi lệnh chờ khớp (không trừ tiền góp)."""
    now = now or market.now_vn()
    order_day = order_day or now.date()
    cfg = fund_repo.load()
    sd = side(cfg)
    if not sd:
        return "Quỹ chờ đang là tiền gửi, không có gì để hoán đổi. Đổi sang quỹ trái phiếu: /dautu quycho VFF"
    close_periods(cfg, now)
    trading = trading_day or session(sd, now)["phien"]
    ym = period or current_period(cfg, now)
    navs = nav_history(sd)
    estimate = round(units * navs[-1][1]) if navs else 0
    order = {"id": max([o["id"] for o in cfg.get("lenh", [])] + [0]) + 1, "ky": max(ym, cfg["bat_dau"]),
             "tien": estimate, "ccq_ra": units, "quy": sd["ma"], "loai": "doi", "dat": order_day.isoformat(),
             "phien": trading.isoformat(), "trang_thai": "cho"}
    cfg.setdefault("lenh", []).append(order)
    fund_repo.save(cfg)
    note = (f"✅ Đã ghi hoán đổi {units_text(units)} ccq {sd['ma']} → {cfg['ma']} (≈ {money(estimate)}): bán "
            f"{sd['ma']} phiên <b>{trading:%d/%m}</b>, tiền về mới mua {cfg['ma']} (~{SWITCH_DAYS} ngày). Xong bot hỏi "
            "ngày bán, ngày mua để cập nhật giá.")
    if quiet:
        return note
    matched = match_orders(now)
    return note + ("\n" + "\n".join(matched) if matched else "")


def record_plan(direct, side_buy, units, ym, main_day, side_day, now):
    """Bấm "Đã đặt các lệnh trên": ghi mua quỹ chính, mua quỹ chờ, hoán đổi trong một lần."""
    cfg = fund_repo.load()
    notes = []
    if direct:
        notes.append(record_order(direct, main_day, now, ym, quiet=True))
    if side_buy:
        notes.append(record_order(side_buy, side_day, now, ym, fund=side(cfg), quiet=True))
    if units:
        notes.append(record_switch(units, side_day, now, ym, quiet=True))
    matched = match_orders(now)
    return "\n".join(notes + matched) + ("" if matched else "\nTối ngày khớp (khoảng 17h có NAV) bot tính số ccq "
                                                            "và cập nhật /taisan.")


def match_orders(now=None):
    """Các câu báo lệnh vừa khớp (xem match_details)."""
    return [note for _, note in match_details(now)]


def match_details(now=None):
    """Lệnh chờ khớp đã có NAV phiên khớp: tính số ccq, cập nhật /taisan. Trả [(mã quỹ vừa mua hoặc None nếu là hoán
    đổi, câu báo)].
    Lệnh mua: số ccq = tiền / NAV (phí mua 0%). Lệnh hoán đổi quỹ chờ → quỹ chính: giá trị = số ccq ra × NAV quỹ
    chờ, số ccq vào = giá trị / NAV quỹ chính cùng phiên (phí hoán đổi 0%)."""
    now = now or market.now_vn()
    cfg = fund_repo.load()
    due = [o for o in cfg.get("lenh", []) if o["trang_thai"] == "cho" and o["phien"] <= now.date().isoformat()]
    if not due:
        return []
    funds = {cfg["ma"]: cfg, **({side(cfg)["ma"]: side(cfg)} if side(cfg) else {})}
    navs = {}

    def nav_of(code, wanted):
        """(ngày khớp thật, NAV): phiên đầu tiên từ ngày wanted (nghỉ lễ thì phiên sau đó), None nếu chưa có NAV."""
        if code not in navs:
            navs[code] = dict(nav_history(funds[code]))
            if not any(d >= wanted for d in navs[code]):
                navs[code] = dict(nav_history(funds[code], fresh=True))
        found = sorted(d for d in navs[code] if wanted <= d <= wanted + timedelta(days=10))
        return (found[0], navs[code][found[0]]) if found else None

    def add_units(data, code, units, cost):
        hold = holding(data, cfg, code)
        if hold is None:
            hold = {"id": assets_repo.new_id(data), "loai": "quy", "ma": code, "sl": 0, "gia_von": None}
            data["items"].append(hold)
        total = hold["sl"] * (hold.get("gia_von") or 0) + cost
        hold["sl"] = round(hold["sl"] + units, 2)
        hold["gia_von"] = total / hold["sl"] if hold["sl"] > 0 else None
        return hold

    data = assets_repo.load()
    notes = []
    for o in due:
        code = o.get("quy", cfg["ma"])
        if code not in funds:
            continue
        got = nav_of(code, date.fromisoformat(o["phien"]))
        if not got:
            continue
        day, nav = got
        if o.get("loai") == "doi":  # bước 1: bán quỹ chờ; mua quỹ chính sau khi tiền về (người dùng báo ngày)
            value = o["ccq_ra"] * nav
            src = holding(data, cfg, code)
            if src:
                src["sl"] = round(max(0, src["sl"] - o["ccq_ra"]), 2)
            o.update({"trang_thai": "chuyen", "ban": day.isoformat(), "nav_ra": nav, "tien": round(value)})
            notes.append((None, f"✅ Đã bán {units_text(o['ccq_ra'])} ccq {code} phiên {day:%d/%m}: NAV "
                                f"{vn_num(nav, 2)}đ ≈ <b>{money(value)}</b> · 🔁 đang chuyển sang {cfg['ma']}"))
            continue
        ccq = round(o["tien"] / nav, 2)
        hold = add_units(data, code, ccq, o["tien"])
        o.update({"trang_thai": "khop", "phien": day.isoformat(), "nav": nav, "ccq": ccq})
        notes.append((code, f"✅ Lệnh {code} {vnd(o['tien'])} đã khớp phiên {day:%d/%m}: NAV {vn_num(nav, 2)}đ → "
                            f"<b>{units_text(ccq)} ccq</b>. Đang có {units_text(hold['sl'])} ccq, giá vốn "
                            f"{vn_num(hold['gia_von'], 0)}đ."))
    if notes:
        assets_repo.save(data)
        fund_repo.save(cfg)
    return notes


def fix_units(text):
    """/dautu ccq 66,43: sửa số ccq của lệnh khớp gần nhất vào quỹ chính; /dautu ccq 36,7 vff: lệnh mua quỹ chờ."""
    cfg = fund_repo.load()
    parts = text.split()
    sd = side(cfg)
    other = bool(sd) and any(plain(x) == sd["ma"].lower() for x in parts[1:])
    code = sd["ma"] if other else cfg["ma"]
    done = [o for o in cfg.get("lenh", []) if o["trang_thai"] == "khop"
            and (o.get("quy") == code and o.get("loai") != "doi" if other else goes_main(cfg, o))]
    try:
        new = number(parts[0] if parts else "")
    except ValueError:
        return "Gõ số ccq theo Fmarket, ví dụ: /dautu ccq 66,43" + (f" (lệnh {sd['ma']}: /dautu ccq 36,7 "
                                                                    f"{sd['ma'].lower()})" if sd else "")
    if not done or new <= 0:
        return "Chưa có lệnh nào đã khớp để sửa"
    o = done[-1]
    data = assets_repo.load()
    hold = holding(data, cfg, code)
    cost = hold["sl"] * (hold.get("gia_von") or 0)
    hold["sl"] = round(hold["sl"] - o["ccq"] + new, 2)
    hold["gia_von"] = cost / hold["sl"] if hold["sl"] else None
    o["ccq"], o["nav"] = new, o["tien"] / new
    assets_repo.save(data)
    fund_repo.save(cfg)
    return (f"✅ Đã sửa lệnh {code} phiên {o['phien'][8:]}/{o['phien'][5:7]}: {units_text(new)} ccq. Đang có "
            f"{units_text(hold['sl'])} ccq {code}")


def skip(ym):
    cfg = fund_repo.load()
    if ym != current_period(cfg):
        return "Kỳ này đã qua"
    if any(o["ky"] == ym for o in cfg.get("lenh", [])):
        return "Tháng này đã đặt lệnh, không tạm dừng được"
    cfg.setdefault("ky", {}).setdefault(ym, {})["bo"] = True
    fund_repo.save(cfg)
    return f"⏸ Tạm dừng góp tháng {ym_text(ym)}: kế hoạch không cộng thêm tháng này. Tháng sau bot tính tiếp"
