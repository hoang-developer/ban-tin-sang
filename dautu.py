"""Đầu tư quỹ mở hằng tháng theo Value Averaging cho bot chi tiêu (/dautu). Mặc định quỹ VMEEF trên Fmarket.

Cách làm (đã chạy thử trên NAV thật của VMEEF, VESAF, SSISCA, DCDS):
- Đường kế hoạch: tháng đầu = số góp (cộng giá trị quỹ có sẵn lúc bắt đầu), mỗi tháng sau = tháng trước × (1 + 1%)
  + số góp. Tháng tạm dừng thì không cộng số góp.
- Mỗi tháng góp 4tr vào "Quỹ chờ" (tiền gửi tiết kiệm, lãi là phụ). Hạn đặt lệnh: trước 14:40 phiên đóng sổ lệnh cuối
  cùng của tháng, để khớp NAV phiên đầu tháng sau.
- Số tiền mua = kế hoạch − giá trị quỹ đang có, không quá số tiền đang có (quỹ chờ + phần góp tháng này chưa để),
  làm tròn xuống 10.000đ, dưới 100.000đ thì tháng đó không mua. Không bao giờ bán (phí bán 1–2% trong 2 năm đầu).
- Quỹ dự phòng chưa tới mốc 1 tháng chi thiết yếu: bot khuyên tạm dừng góp, không chặn.
Bot không đặt lệnh, không chuyển tiền: bạn tự đặt trên Fmarket rồi bấm nút xác nhận; số ccq bot tính theo NAV phiên
khớp (phí mua 0%), sai thì sửa bằng /dautu ccq. Thông tin tham khảo, không phải lời khuyên đầu tư.
"""
import html
import re
import sys
from datetime import date, datetime, timedelta

import kho
import phantich as pt
import sochitieu as ct
import taisan as ts
from bantin import VN_TZ, vn_num

KEY = "chitieu:dautu"
# {"ma", "id", "ten", "bat_dau": "YYYY-MM", "goc": giá trị quỹ có sẵn lúc bắt đầu, "gop": {"YYYY-MM": số góp từ tháng đó},
#  "tang": 0.01, "nap": {"YYYY-MM": đã góp vào hệ thống trong tháng}, "ky": {"YYYY-MM": {"chot", "bo", "muc", "gt"}},
#  "lenh": [{"id", "ky", "tien", "dat", "phien", "trang_thai": "cho"|"khop", "nav", "ccq"}], "tat": bool, "top_luc"}
K_NAV = "chitieu:dautu:nav"  # {"ma", "luc", "nav": [[ngày ISO, NAV], ...]} (khoảng 400 phiên gần nhất)
K_INFO = "chitieu:dautu:thongtin"  # {"ma", "luc", "data": chi tiết quỹ của Fmarket (phiên giao dịch, top 10, phí)}
FMARKET = "https://api.fmarket.vn/res"
DEFAULT_FUND, DEFAULT_GOP, DEFAULT_TANG = "VMEEF", 4_000_000, 0.01
MIN_ORDER, STEP = 100_000, 10_000
WATCH = ("VIC", "VHM", "VRE", "VPL")  # nhóm Vingroup: báo nếu vào top 10 của quỹ
NOT_ADVICE = "<i>Tham khảo, không phải lời khuyên đầu tư</i>"
USAGE = ("📈 <b>Đầu tư quỹ mở hằng tháng (Value Averaging)</b>\n"
         "/dautu: tình trạng, tháng này nên mua bao nhiêu\n"
         "/dautu batdau 4tr VMEEF: bật (số góp mỗi tháng, mã quỹ trên Fmarket)\n"
         "/dautu dadat 3tr: vừa đặt lệnh mua xong · lệnh đặt hôm khác thì thêm ngày đặt: /dautu dadat 1tr 9/11 "
         "(đặt sau 14:40 thì thêm: sau 14h40); bot tự tính phiên khớp\n"
         "/dautu ccq 66,4: sửa số ccq của lệnh khớp gần nhất theo Fmarket\n"
         "/dautu nap 2tr · /dautu rut 1tr · /dautu quycho 12tr: thêm, rút, đặt lại số dư quỹ chờ\n"
         "/dautu gop 5tr: đổi số góp mỗi tháng · /dautu tang 1%: đổi mức tăng của kế hoạch\n"
         "/dautu bo: tạm dừng tháng này · /dautu lichsu: các lệnh · /dautu tat, /dautu bat\n"
         "/dautu baocao tat (hoặc bat): tin tối 20h về giá trị, lãi/lỗ các quỹ theo NAV\n"
         "<b>Quỹ chờ là quỹ trái phiếu</b> (vừa là phần trái phiếu của danh mục, vừa là tiền chờ): /dautu quycho VFF "
         "(về tiền gửi: /dautu quycho tien) · góp thêm mỗi tháng: /dautu vff 1tr · đã mua VFF: nhắn mua VFF 1tr · "
         "đã hoán đổi: /dautu doi 125,5 (số ccq VFF)\n"
         "<b>Khoản tiền lớn</b> (ví dụ tiền bán cổ phiếu) đã mua VFF: /dautu taicocau 15,5tr — phần cổ phiếu (80%) rải "
         "dần vào VMEEF trong 3 tháng (đổi: /dautu taicocau 15,5tr 6 thang 70%)")


# ---- Lưu trữ ---------------------------------------------------------------------------

def config():
    return kho.get(KEY, {}) or {}


def save(cfg):
    kho.put(KEY, cfg)


def active(cfg=None):
    cfg = config() if cfg is None else cfg
    return bool(cfg.get("ma")) and not cfg.get("tat")


def now_vn():
    return datetime.now(VN_TZ)


def ym_of(d):
    return f"{d.year}-{d.month:02d}"


def ym_add(ym, n):
    y, m = map(int, ym.split("-"))
    m += n - 1
    return f"{y + m // 12}-{m % 12 + 1:02d}"


def ym_text(ym):
    return f"{int(ym[5:])}/{ym[:4]}"


def months(start, end):
    """Các tháng từ start tới end (cả hai đầu), dạng 'YYYY-MM'."""
    out, ym = [], start
    while ym <= end:
        out.append(ym)
        ym = ym_add(ym, 1)
    return out


def money(x):
    return pt.short(x) if abs(x) >= 1000 else "0đ"


def units_text(x):
    return vn_num(x, 2).rstrip("0").rstrip(",") if x % 1 else vn_num(x, 0)


# ---- Dữ liệu quỹ trên Fmarket ----------------------------------------------------------

def find_fund(code):
    """(id, tên quỹ) trên Fmarket theo mã (VMEEF, VESAF, SSISCA...); None nếu không thấy."""
    body = {"types": ["NEW_FUND", "TRADING_FUND"], "issuerIds": [], "sortOrder": "DESC", "sortField": "navTo6Months",
            "page": 1, "pageSize": 100, "isIpo": False, "fundAssetTypes": [], "bondRemainPeriods": [],
            "searchField": code, "isBuyByReward": False, "thirdAppIds": []}
    for r in ts.http_json(f"{FMARKET}/products/filter", body)["data"]["rows"]:
        if (r.get("shortName") or "").upper() == code.upper():
            return r["id"], r.get("name") or code
    return None


def nav_history(cfg, fresh=False):
    """[(ngày, NAV)] khoảng 400 phiên gần nhất. Lưu trong kho 2 tiếng; nguồn lỗi thì dùng bản đã lưu."""
    key = f"{K_NAV}:{cfg['ma']}"
    store = kho.get(key, {}) or {}
    if store.get("ma") == cfg["ma"] and store.get("nav") and not fresh and \
            (now_vn() - datetime.fromisoformat(store["luc"])).total_seconds() < 2 * 3600:
        return [(date.fromisoformat(d), v) for d, v in store["nav"]]
    try:
        rows = ts.http_json(f"{FMARKET}/product/get-nav-history",
                            {"isAllData": 1, "productId": cfg["id"], "fromDate": None,
                             "toDate": now_vn().strftime("%Y%m%d")})["data"]
        navs = sorted((p["navDate"], float(p["nav"])) for p in rows if p.get("nav"))[-400:]
        if navs:
            kho.put(key, {"ma": cfg["ma"], "luc": now_vn().isoformat(timespec="minutes"), "nav": navs})
            return [(date.fromisoformat(d), v) for d, v in navs]
    except Exception as e:
        print(f"[lỗi] NAV {cfg['ma']}: {e!r}", file=sys.stderr)
    if store.get("ma") == cfg["ma"]:
        return [(date.fromisoformat(d), v) for d, v in store.get("nav", [])]
    return []


def fund_info(cfg, fresh=False):
    """Chi tiết quỹ của Fmarket (phiên giao dịch kế tiếp, top 10 mã, phí); lưu 1 tiếng, lỗi thì dùng bản cũ."""
    key = f"{K_INFO}:{cfg['ma']}"
    store = kho.get(key, {}) or {}
    if store.get("ma") == cfg["ma"] and not fresh and \
            (now_vn() - datetime.fromisoformat(store["luc"])).total_seconds() < 3600:
        return store["data"]
    try:
        d = ts.http_json(f"{FMARKET}/products/{cfg['id']}")["data"]
        keep = {"phien": d.get("productTradingSession"), "top": [
            {"ma": h.get("stockCode"), "nganh": h.get("industry"), "tyle": h.get("netAssetPercent")}
            for h in d.get("productTopHoldingList") or []],
            "top_luc": (d.get("productFund") or {}).get("updateAssetHoldingTime")}
        kho.put(key, {"ma": cfg["ma"], "luc": now_vn().isoformat(timespec="minutes"), "data": keep})
        return keep
    except Exception as e:
        print(f"[lỗi] thông tin quỹ {cfg['ma']}: {e!r}", file=sys.stderr)
        return store.get("data") if store.get("ma") == cfg["ma"] else None


def weekdays_after(d, n):
    while n:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def session(cfg, now=None):
    """Phiên kế tiếp: {"phien": ngày khớp lệnh, "dong": lúc đóng sổ lệnh, "du_phong": True nếu tự đoán (không có
    dữ liệu Fmarket: thứ Hai–thứ Sáu, đóng sổ 14:40 ngày giao dịch trước, chưa tính ngày lễ)}."""
    now = now or now_vn()
    info = fund_info(cfg) or {}
    s = info.get("phien") or {}
    try:
        trading = datetime.strptime(s["tradingTimeString"], "%d/%m/%Y").date()
        closing = datetime.strptime(s["closedOrderBookTimeString"], "%H:%M %d/%m/%Y").replace(tzinfo=VN_TZ)
        if closing > now:
            return {"phien": trading, "dong": closing, "du_phong": False}
        if now - closing < timedelta(hours=1):  # vừa qua giờ đóng sổ, bản lưu chưa đổi: hỏi lại Fmarket
            s = (fund_info(cfg, fresh=True) or {}).get("phien") or {}
            trading = datetime.strptime(s["tradingTimeString"], "%d/%m/%Y").date()
            closing = datetime.strptime(s["closedOrderBookTimeString"], "%H:%M %d/%m/%Y").replace(tzinfo=VN_TZ)
            if closing > now:
                return {"phien": trading, "dong": closing, "du_phong": False}
    except (KeyError, TypeError, ValueError):
        pass
    day = now.date()
    if day.weekday() >= 5 or (now.hour, now.minute) >= (14, 40):
        day = weekdays_after(day, 1)
    return {"phien": weekdays_after(day, 1), "dong": datetime(day.year, day.month, day.day, 14, 40, tzinfo=VN_TZ),
            "du_phong": True}


def is_deadline(cfg, now=None):
    """Hôm nay là hạn đặt lệnh của tháng (phiên đóng sổ cuối cùng trong tháng, chưa qua 14:40)?"""
    now = now or now_vn()
    s = session(cfg, now)
    return s["dong"].date() == now.date() and ym_of(s["phien"]) != ym_of(now.date()), s


def current_period(cfg, now=None):
    """Kỳ đang mở: tháng của lần đóng sổ kế tiếp (qua hạn cuối tháng thì đã sang kỳ tháng sau)."""
    return ym_of(session(cfg, now)["dong"].date())


# ---- Quỹ chờ, danh mục -----------------------------------------------------------------

def wait_name(cfg):
    return f"Quỹ chờ {cfg['ma']}"


def wait_item(data, cfg):
    """Tài khoản tiền "Quỹ chờ <mã>" trong /taisan (tạo nếu chưa có)."""
    item = next((it for it in data["items"] if it["loai"] == "tien" and it.get("dautu")), None)
    if item is None:
        item = {"id": ts.new_id(data), "loai": "tien", "ten": wait_name(cfg), "tien": 0,
                "ngay": ct.today().isoformat(), "dautu": True}
        data["items"].append(item)
    return item


def holding(data, cfg, code=None):
    code = code or cfg["ma"]
    return next((it for it in data["items"] if it["loai"] == "quy" and it["ma"] == code), None)


def side(cfg):
    """Quỹ chờ là quỹ (ví dụ VFF: vừa là phần trái phiếu của danh mục, vừa là tiền chờ cho VA): {"ma", "id"} hoặc None
    nếu quỹ chờ là tiền gửi."""
    return cfg.get("cho") or None


def goes_main(cfg, o):
    """Lệnh làm tăng quỹ chính: mua quỹ chính, hoặc hoán đổi từ quỹ chờ sang."""
    return o.get("loai") == "doi" or o.get("quy", cfg["ma"]) == cfg["ma"]


def them_of(cfg, ym):
    """Số góp thêm mỗi tháng vào quỹ chờ (ngoài phần VA), 0 nếu tháng tạm dừng."""
    if not side(cfg) or (cfg.get("ky", {}).get(ym) or {}).get("bo"):
        return 0
    steps = [(k, v) for k, v in cfg.get("them", {}).items() if k <= ym]
    return max(steps)[1] if steps else 0


def total_of(cfg, ym):
    """Tổng tiền góp của tháng: phần VA + phần góp thêm vào quỹ chờ."""
    return gop_of(cfg, ym) + them_of(cfg, ym)


def gop_of(cfg, ym):
    if (cfg.get("ky", {}).get(ym) or {}).get("bo"):
        return 0
    steps = [(k, v) for k, v in cfg.get("gop", {}).items() if k <= ym]
    return max(steps)[1] if steps else 0


def extra_of(cfg, ym):
    """Phần cộng thêm vào kế hoạch quỹ chính trong tháng ym khi rải một khoản tiền lớn (/dautu taicocau)."""
    return cfg.get("ke_hoach_them", {}).get(ym, 0)


def target(cfg, ym):
    """Giá trị kế hoạch của kỳ ym."""
    value = None
    for m in months(cfg["bat_dau"], ym):
        add = gop_of(cfg, m) + extra_of(cfg, m)
        value = cfg.get("goc", 0) + add if value is None else value * (1 + cfg.get("tang", DEFAULT_TANG)) + add
    return value or 0


def contributed_of(cfg):
    """Tổng tiền đã góp: góp hằng tháng + khoản góp một lần (tái cơ cấu) + giá trị có sẵn lúc bắt đầu."""
    return sum(cfg.get("nap", {}).values()) + sum(cfg.get("ngoai", {}).values()) + cfg.get("goc", 0)


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
            data = ts.load()
            navs = nav_history(cfg)
            hold = holding(data, cfg)
            value = (hold["sl"] * navs[-1][1] if hold and navs else 0) + sum(
                o["tien"] for o in cfg.get("lenh", []) if o["trang_thai"] == "cho" and goes_main(cfg, o))
        unpaid = max(0, total_of(cfg, ym) - cfg.get("nap", {}).get(ym, 0))
        if unpaid:
            wait_item(data, cfg)["tien"] += unpaid
            cfg.setdefault("nap", {})[ym] = cfg.get("nap", {}).get(ym, 0) + unpaid
        k.update({"chot": True, "muc": round(target(cfg, ym)), "gt": round(value)})  # gt: giá trị lúc chốt (biểu đồ)
        changed = True
    if changed:
        if data:
            ts.save(data)
        save(cfg)
    return changed


def status(cfg, now=None, fresh=False):
    """Số liệu kỳ đang mở: kế hoạch, giá trị, cần mua, có bao nhiêu, nên mua bao nhiêu..."""
    now = now or now_vn()
    close_periods(cfg, now)
    navs = nav_history(cfg, fresh)
    data = ts.load()
    ym = current_period(cfg, now)
    hold = holding(data, cfg)
    units = hold["sl"] if hold else 0
    nav_day, nav = navs[-1] if navs else (None, None)
    orders = cfg.get("lenh", [])
    pending = sum(o["tien"] for o in orders if o["trang_thai"] == "cho" and goes_main(cfg, o))
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
        import duphong
        fund = duphong.status(now.date())
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
            "fund": fund, "below_milestone": bool(fund and fund["monthly"] and fund["covered"] < 1)}


# ---- Câu trả lời -----------------------------------------------------------------------

def pct(x):
    return "0,0%" if abs(x) < 0.0005 else f"{x * 100:+.1f}%".replace(".", ",")


def gain_text(gain, cost):
    """'🟢 +22k (+0,6%)', '🔴 −22k (−0,6%)' hoặc '⚪ hòa vốn' (chênh dưới 1.000đ)."""
    if abs(gain) < 1000:
        return "⚪ hòa vốn"
    sign = "+" if gain > 0 else "−"
    return f"{'🟢' if gain > 0 else '🔴'} {sign}{money(abs(gain))}" + (f" ({pct(gain / cost).replace('-', '−')})"
                                                                     if cost else "")


def nav_line(cfg, s):
    if not s["nav"]:
        return f"Chưa lấy được NAV {cfg['ma']}"
    line = f"NAV {vn_num(s['nav'], 2)}đ ({s['nav_day']:%d/%m})"
    if s["month_change"] is not None:
        line += f" · tháng này {pct(s['month_change'])}"
    if s["drawdown"] is not None:
        line += f" · cách đỉnh 52 tuần {pct(s['drawdown'])}"
    return line


def decision_lines(cfg, s, final=True):
    """Các dòng "kế hoạch / đang có / nên mua" của kỳ đang mở. final=False (chưa tới hạn): chỉ là con số dự kiến."""
    lines = [f"Kế hoạch {ym_text(s['ym'])}: <b>{money(s['plan'])}</b> · đang có {money(s['value'])}"
             + (f" (gồm {money(s['pending'])} chờ khớp)" if s["pending"] else "")]
    if s["skip"]:
        lines.append("⏸ Tháng này tạm dừng góp" + (f": quỹ chờ còn {money(s['cash'])}, nếu muốn vẫn mua được tới "
                                                  f"{money(s['buy'])}" if s["buy"] else ""))
        return lines
    if not final:
        lines.append(f"📅 Nếu NAV giữ như hiện tại, cuối tháng mua khoảng <b>{money(s['buy'])}</b>" if s["buy"] else
                     "📅 Nếu NAV giữ như hiện tại, cuối tháng không mua (quỹ đang cao hơn kế hoạch)")
        lines.append("   Số chính xác bot tính và nhắc vào sáng ngày hạn đặt lệnh")
    elif s["side"]:
        lines += order_lines(cfg, s)
    elif s["buy"]:
        lines.append(f"👉 <b>Mua {ct.vnd(s['buy'])}</b>" + (
            f" (hết tiền đang có; còn thiếu {money(s['need'] - s['buy'])} so với kế hoạch, tháng sau tự bù)"
            if s["short"] else ""))
    elif s["need"] > 0:
        lines.append(f"👉 Không mua: cần thêm {money(s['need'])} nhưng chưa có tiền (quỹ chờ {money(s['cash'])})")
    else:
        lines.append(f"👉 <b>Tháng này không mua</b>: quỹ đang cao hơn kế hoạch {money(-s['need'])}; "
                     f"để {money(gop_of(cfg, s['ym']))} vào quỹ chờ (gửi tiết kiệm), chờ lúc quỹ giảm thì mua nhiều hơn")
    if s["side"]:
        lines.append(f"💰 Tiền góp chưa đặt lệnh {money(s['money_now'])} · {s['side']['ma']} đang có "
                     f"{money(s['side_value'] or 0)}")
    else:
        lines.append(f"💰 Tiền đang có: quỹ chờ {money(s['cash'])}"
                     + (f" + góp tháng này chưa để {money(s['unpaid'])}" if s["unpaid"] else ""))
    if s["below_milestone"]:
        f = s["fund"]
        lines.append(f"⚠️ Quỹ dự phòng mới đủ {vn_num(f['covered'], 1)} tháng chi (mốc đầu: 1 tháng, còn thiếu "
                     f"{money(f['monthly'] - f['balance'])}): nên ưu tiên nạp quỹ dự phòng, tạm dừng góp tháng này")
    return lines


def order_lines(cfg, s):
    """Các lệnh cần đặt trên Fmarket khi quỹ chờ là quỹ trái phiếu."""
    sd = s["side"]["ma"]
    steps = []
    if s["direct"]:
        steps.append(f"Mua {cfg['ma']} <b>{ct.vnd(s['direct'])}</b> (tiền góp)")
    if s["side_buy"]:
        steps.append(f"Mua {sd} <b>{ct.vnd(s['side_buy'])}</b>")
    if s["switch"]:
        steps.append(f"Hoán đổi <b>{units_text(s['switch_units'])} ccq {sd} → {cfg['ma']}</b> (≈ {money(s['switch'])}, "
                     "miễn phí hoán đổi)")
    if not steps:
        return ["👉 Tháng này không cần đặt lệnh"]
    head = (f"👉 {cfg['ma']} đang cao hơn kế hoạch {money(-s['need'])}: chưa mua thêm, tiền góp vào {sd}"
            if s["need"] <= 0 else f"👉 Mua thêm {cfg['ma']} {money(s['buy'])}" + (
                f" (hết tiền; còn thiếu {money(s['need'] - s['buy'])} so với kế hoạch, tháng sau tự bù)" if s["short"] else ""))
    return [head] + [f"   {i}. {t}" for i, t in enumerate(steps, 1)]


def summary_line(s):
    if s["side"]:  # cả danh mục: quỹ chính + quỹ chờ + tiền chưa đặt lệnh
        total = s["value"] + (s["side_value"] or 0) + s["cash"]
        gain = total - s["contributed"]
        share = s["value"] / total * 100 if total else 0
        return (f"Danh mục {money(total)}: cổ phiếu {money(s['value'])} ({share:.0f}%) · "
                f"{s['side']['ma']} {money(s['side_value'] or 0)} ({100 - share:.0f}%)"
                + (f" · đã góp {money(s['contributed'])}, lãi/lỗ {money(gain)} ({pct(gain / s['contributed'])})"
                   if s["contributed"] else ""))
    gain = s["value"] - s["invested"] if s["invested"] else 0
    line = f"Đã mua {money(s['invested'])}"
    if s["invested"] and s["nav"]:
        line += f" · lãi/lỗ {money(gain)} ({pct(gain / s['invested'])})"
    return line + f" · {units_text(s['units'])} ccq"


def view(day=None, fresh=False):
    if not kho.ready():
        return ct.NEED_STORE
    cfg = config()
    if not cfg.get("ma"):
        return ("📈 <b>Đầu tư quỹ mở hằng tháng</b>\nChưa bật. Bật bằng: /dautu batdau 4tr VMEEF (góp 4 triệu mỗi "
                "tháng vào quỹ VMEEF). Mỗi cuối tháng bot tính nên mua bao nhiêu theo Value Averaging: quỹ giảm thì "
                "mua nhiều hơn, quỹ tăng nhanh thì mua ít hoặc để tiền chờ.\n\n" + USAGE)
    s = status(cfg, fresh=fresh)
    final, sess = is_deadline(cfg)
    extra = them_of(cfg, s["ym"])
    lines = [f"📈 <b>{cfg['ma']}: góp {money(gop_of(cfg, s['ym']) or cfg['gop'][max(cfg['gop'])])}/tháng</b>"
             + (f" + {money(extra)} {s['side']['ma']}" if extra else "")
             + (" (đang tắt: /dautu bat)" if cfg.get("tat") else ""),
             nav_line(cfg, s), *decision_lines(cfg, s, final),
             f"⏰ Hạn đặt lệnh tháng này: trước {deadline_text(cfg, s['ym'], sess)}",
             summary_line(s)]
    info = fund_info(cfg) or {}
    if info.get("top"):
        top = ", ".join(h["ma"] for h in info["top"])
        flagged = [h["ma"] for h in info["top"] if h["ma"] in WATCH]
        lines.append(f"Top 10 ({info.get('top_luc') or '—'}): {top}"
                     + (f"\n⚠️ Có cổ phiếu nhóm Vingroup: {', '.join(flagged)}" if flagged else ""))
    left = {k: v for k, v in cfg.get("ke_hoach_them", {}).items() if k >= s["ym"]}
    if left:
        lines.append(f"🔁 Đang rải thêm vào {cfg['ma']}: {money(sum(left.values()))} còn lại, tới tháng "
                     f"{ym_text(max(left))} (/dautu taicocau xoa để bỏ)")
    lines.append(NOT_ADVICE)
    return "\n".join(lines), buttons(cfg, s, sess, final)


def deadline_text(cfg, ym, sess):
    if ym_of(sess["dong"].date()) == ym and ym_of(sess["phien"]) != ym:
        return f"14:40 hôm nay {sess['dong']:%d/%m}" if sess["dong"].date() == ct.today() else f"14:40 {sess['dong']:%d/%m}"
    last = last_weekday(ym)
    return f"14:40 phiên cuối tháng (khoảng {last:%d/%m}, Fmarket báo chính xác vào hôm đó)"


def last_weekday(ym):
    d = date(int(ym[:4]), int(ym[5:]), 28) + timedelta(days=4)
    d = d.replace(day=1) - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def buttons(cfg, s, sess, final=True):
    rows = []
    phien = sess["phien"].strftime("%Y%m%d")
    if s["side"] and final and not s["skip"] and (s["direct"] or s["side_buy"] or s["switch"]):
        sp = session(s["side"])["phien"].strftime("%Y%m%d")
        rows.append([("✅ Đã đặt các lệnh trên", f"dt:dat2:{int(s['direct'])}:{int(s['side_buy'])}:"
                      f"{round(s['switch_units'] * 100)}:{s['ym']}:{phien}:{sp}")])
    elif s["buy"] and not s["skip"] and final:
        rows.append([(f"✅ Đã đặt lệnh {money(s['buy'])}", f"dt:dat:{int(s['buy'])}:{phien}:{s['ym']}")])
    if not s["skip"] and not s["ordered"]:
        rows.append([("⏸ Tạm dừng tháng này", f"dt:bo:{s['ym']}")])
    rows.append([("🔄 Cập nhật", "dt:xem"), ("📊 Biểu đồ", "dt:bd"), ("🧾 Lệnh", "dt:ls")])
    rows.append([("🎯 Kế hoạch", "kh:lt"), ct.BACK])
    return rows


def reminder(now, second=False):
    """Tin nhắc ngày hạn đặt lệnh (8:30, nhắc lại 13:00 nếu chưa bấm)."""
    cfg = config()
    s = status(cfg, now, fresh=True)
    if second and (not (s["buy"] or s["side_buy"]) or s["skip"] or s["ordered"]):
        return None
    sess = session(cfg, now)
    title = (f"📈 <b>{cfg['ma']}: hôm nay là hạn đặt lệnh tháng {int(s['ym'][5:])}</b>" if not second else
             f"⏰ <b>{cfg['ma']}: còn tới 14:40 để đặt lệnh tháng {int(s['ym'][5:])}</b>")
    when = f"Đặt trên Fmarket trước <b>14:40 {sess['dong']:%d/%m}</b> → {cfg['ma']} khớp NAV phiên {sess['phien']:%d/%m}"
    if s["side"]:
        when += f", {s['side']['ma']} phiên {session(s['side'], now)['phien']:%d/%m}"
    lines = [title, when, nav_line(cfg, s), *decision_lines(cfg, s), summary_line(s), NOT_ADVICE]
    return "\n".join(lines), buttons(cfg, s, sess)


def history_text():
    cfg = config()
    orders = cfg.get("lenh", [])
    if not orders:
        return "Chưa có lệnh nào. Đặt xong trên Fmarket thì bấm ✅ hoặc gõ /dautu dadat 3tr", [[("📈 Đầu tư", "dt:xem")]]
    lines = [f"🧾 <b>Các lệnh {cfg['ma']}</b>" + (f" và {side(cfg)['ma']}" if side(cfg) else "")]
    for o in orders[-15:]:
        when = f"đặt {o['dat'][8:]}/{o['dat'][5:7]} → phiên {o['phien'][8:]}/{o['phien'][5:7]}"
        code = o.get("quy", cfg["ma"])
        if o.get("loai") == "doi":
            lines.append(f"• {when}: hoán đổi {units_text(o['ccq_ra'])} ccq {code} → " + (
                f"{units_text(o['ccq'])} ccq {cfg['ma']} ({money(o['tien'])})" if o["trang_thai"] == "khop"
                else f"{cfg['ma']} · chờ khớp"))
            continue
        when = (f"{code} " if code != cfg["ma"] else "") + when
        if o["trang_thai"] == "khop":
            lines.append(f"• {when}: {money(o['tien'])} → {units_text(o['ccq'])} ccq, NAV {vn_num(o['nav'], 2)}")
        else:
            lines.append(f"• {when}: {money(o['tien'])} · chờ khớp")
    fixable = list(dict.fromkeys(o.get("quy", cfg["ma"]) for o in orders
                                 if o["trang_thai"] == "khop" and o.get("loai") != "doi"))
    return "\n".join(lines), [[fix_button(code)] for code in fixable[-2:]] + [[("📈 Đầu tư", "dt:xem"), ct.BACK]]


def chart_reply():
    cfg = config()
    rows = [(ym, k) for ym, k in sorted(cfg.get("ky", {}).items()) if k.get("chot") and "gt" in k]
    s = status(cfg)
    rows.append((s["ym"], {"muc": s["plan"], "gt": s["value"]}))
    chart = {"type": "line", "data": {"labels": [ym_text(ym) for ym, _ in rows], "datasets": [
        {"label": "Kế hoạch (triệu)", "data": [round(k["muc"] / 1e6, 2) for _, k in rows], "borderColor": "#868e96",
         "borderDash": [6, 4], "fill": False},
        {"label": f"Giá trị {cfg['ma']} (triệu)", "data": [round(k["gt"] / 1e6, 2) for _, k in rows],
         "borderColor": "#1971c2", "backgroundColor": "#1971c233", "fill": True}]},
        "options": {"plugins": {"datalabels": {"display": False}, "title": {
            "display": True, "font": {"size": 20}, "text": f"{cfg['ma']}: kế hoạch và thực tế (triệu đồng)"}}}}
    try:
        return {"photos": [pt.chart_png(chart, 900, 450)],
                "caption": f"📊 <b>{cfg['ma']}</b>: kế hoạch {money(s['plan'])} · đang có {money(s['value'])}"}
    except Exception as e:
        print(f"[lỗi] vẽ biểu đồ đầu tư: {e!r}", file=sys.stderr)
        return "⚠️ Chưa vẽ được biểu đồ (dịch vụ vẽ không trả lời), thử lại sau"


# ---- Ghi lệnh, góp tiền, khớp lệnh -----------------------------------------------------

def add_money(cfg, amount, ym, data=None):
    """Góp thêm vào quỹ chờ (tính là góp của tháng ym)."""
    own = data is None
    data = data or ts.load()
    item = wait_item(data, cfg)
    item["tien"] += amount
    item["ngay"] = ct.today().isoformat()
    cfg.setdefault("nap", {})[ym] = cfg.get("nap", {}).get(ym, 0) + amount
    if own:
        ts.save(data)
    return item["tien"]


def cutoff_day(trading):
    """Ngày đóng sổ của phiên `trading`: ngày giao dịch liền trước (thứ Hai–thứ Sáu, chưa tính ngày lễ)."""
    d = trading - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def next_trading(cfg, d, include=False):
    """Ngày giao dịch đầu tiên sau d (include: tính cả d). Theo lịch NAV thật nếu có (bỏ ngày lễ), không thì
    thứ Hai–thứ Sáu."""
    navs = nav_history(cfg)
    known = [x for x, _ in navs if (x >= d if include else x > d)]
    if known:
        return known[0]
    days = {x.weekday() for x, _ in navs[-20:]} if len(navs) >= 5 else {0, 1, 2, 3, 4}
    x = d if include else d + timedelta(days=1)
    while x.weekday() not in days:
        x += timedelta(days=1)
    return x


def order_spec(cfg, text, now, fund=None):
    """Phần chữ ngoài số tiền của "/dautu dadat", "mua VMEEF": (ngày đặt, phiên khớp, kỳ) hoặc câu báo lỗi.
    Có ngày (9/11): lệnh đặt hôm đó, mặc định trước 14:40 ("sau 14h40" thì sang phiên sau). Không có ngày: vừa đặt
    xong, tính theo giờ hiện tại."""
    day = read_date(text, now.date())
    if day and day > now.date():
        return "Ngày đặt lệnh chưa tới. Gõ ngày bạn đã đặt trên Fmarket, ví dụ: /dautu dadat 1tr 9/11"
    late = bool(re.search(r"sau\s*14", ct.plain(text))) or (day is None and (now.hour, now.minute) >= (14, 40))
    day = day or now.date()
    cutoff = next_trading(cfg, day, include=True)  # đặt cuối tuần, ngày lễ: sổ lệnh đóng ở ngày giao dịch kế tiếp
    if late and cutoff == day:
        cutoff = next_trading(cfg, cutoff)
    return day, next_trading(fund or cfg, cutoff), ym_of(cutoff)  # fund: quỹ chờ có lịch giao dịch riêng


def record_order(amount, trading_day=None, now=None, period=None, order_day=None, fund=None, quiet=False, lump=False):
    """Đã đặt lệnh mua `amount`: trừ quỹ chờ (thiếu thì phần thiếu tính là góp thêm của tháng), ghi lệnh chờ khớp.
    period: kỳ của lệnh (nút bấm mang theo); không có thì suy từ ngày đóng sổ của phiên khớp. fund: mua quỹ chờ (VFF)."""
    now = now or now_vn()
    order_day = order_day or now.date()
    cfg = config()
    close_periods(cfg, now)
    code = (fund or cfg)["ma"]
    sess = session(fund or cfg, now)
    trading = trading_day or sess["phien"]
    ym = period or (ym_of(cutoff_day(trading_day)) if trading_day else current_period(cfg, now))
    if ym < cfg["bat_dau"]:
        ym = cfg["bat_dau"]
    data = ts.load()
    item = wait_item(data, cfg)
    if lump:  # khoản góp một lần (tiền bán cổ phiếu...): không trừ vào tiền góp hằng tháng
        cfg.setdefault("ngoai", {})[ym] = cfg.get("ngoai", {}).get(ym, 0) + amount
    elif item["tien"] < amount:
        extra = amount - item["tien"]
        cfg.setdefault("nap", {})[ym] = cfg.get("nap", {}).get(ym, 0) + extra
        item["tien"] = 0
    else:
        item["tien"] -= amount
    order = {"id": max([o["id"] for o in cfg.get("lenh", [])] + [0]) + 1, "ky": ym, "tien": amount, "quy": code,
             "loai": "mua", "dat": order_day.isoformat(), "phien": trading.isoformat(), "trang_thai": "cho",
             **({"ngoai": True} if lump else {})}
    cfg.setdefault("lenh", []).append(order)
    ts.save(data)
    save(cfg)
    note = (f"✅ Đã ghi lệnh mua {code} {ct.vnd(amount)}: đặt {order_day:%d/%m} → khớp NAV phiên "
            f"<b>{trading:%d/%m}</b>." + ("" if side(cfg) else f" Quỹ chờ còn {money(item['tien'])}."))
    if quiet:
        return note
    matched = match_orders(now)
    if matched:
        return note + "\n" + matched[0]
    return note + " Tối ngày khớp (khoảng 17h có NAV) bot tính số ccq và cộng vào /taisan."


def record_switch(units, trading_day=None, now=None, period=None, order_day=None, quiet=False):
    """Đã đặt lệnh hoán đổi `units` ccq quỹ chờ (VFF) sang quỹ chính: ghi lệnh chờ khớp (không trừ tiền góp)."""
    now = now or now_vn()
    order_day = order_day or now.date()
    cfg = config()
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
    save(cfg)
    note = (f"✅ Đã ghi lệnh hoán đổi {units_text(units)} ccq {sd['ma']} → {cfg['ma']} (≈ {money(estimate)}): "
            f"khớp NAV phiên <b>{trading:%d/%m}</b>.")
    if quiet:
        return note
    matched = match_orders(now)
    return note + ("\n" + "\n".join(matched) if matched else " Tối ngày khớp bot cập nhật số ccq hai quỹ.")


def record_plan(direct, side_buy, units, ym, main_day, side_day, now):
    """Bấm "Đã đặt các lệnh trên": ghi mua quỹ chính, mua quỹ chờ, hoán đổi trong một lần."""
    cfg = config()
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
    now = now or now_vn()
    cfg = config()
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
            hold = {"id": ts.new_id(data), "loai": "quy", "ma": code, "sl": 0, "gia_von": None}
            data["items"].append(hold)
        total = hold["sl"] * (hold.get("gia_von") or 0) + cost
        hold["sl"] = round(hold["sl"] + units, 2)
        hold["gia_von"] = total / hold["sl"] if hold["sl"] > 0 else None
        return hold

    data = ts.load()
    notes = []
    for o in due:
        code = o.get("quy", cfg["ma"])
        if code not in funds:
            continue
        got = nav_of(code, date.fromisoformat(o["phien"]))
        if not got:
            continue
        day, nav = got
        if o.get("loai") == "doi":
            main = nav_of(cfg["ma"], day)
            if not main or main[0] != day:
                continue
            value = o["ccq_ra"] * nav
            src = holding(data, cfg, code)
            if src:
                src["sl"] = round(max(0, src["sl"] - o["ccq_ra"]), 2)
            ccq = round(value / main[1], 2)
            hold = add_units(data, cfg["ma"], ccq, value)
            o.update({"trang_thai": "khop", "phien": day.isoformat(), "nav": main[1], "nav_ra": nav, "ccq": ccq,
                      "tien": round(value)})
            notes.append((None, f"✅ Hoán đổi {units_text(o['ccq_ra'])} ccq {code} (NAV {vn_num(nav, 2)}đ, ≈ "
                                f"{money(value)}) → <b>{units_text(ccq)} ccq {cfg['ma']}</b> phiên {day:%d/%m}. Đang có "
                                f"{units_text(hold['sl'])} ccq {cfg['ma']}."))
            continue
        ccq = round(o["tien"] / nav, 2)
        hold = add_units(data, code, ccq, o["tien"])
        o.update({"trang_thai": "khop", "phien": day.isoformat(), "nav": nav, "ccq": ccq})
        notes.append((code, f"✅ Lệnh {code} {ct.vnd(o['tien'])} đã khớp phiên {day:%d/%m}: NAV {vn_num(nav, 2)}đ → "
                            f"<b>{units_text(ccq)} ccq</b>. Đang có {units_text(hold['sl'])} ccq, giá vốn "
                            f"{vn_num(hold['gia_von'], 0)}đ."))
    if notes:
        ts.save(data)
        save(cfg)
    return notes


def fix_units(text):
    """/dautu ccq 66,43: sửa số ccq của lệnh khớp gần nhất vào quỹ chính; /dautu ccq 36,7 vff: lệnh mua quỹ chờ."""
    cfg = config()
    parts = text.split()
    sd = side(cfg)
    other = bool(sd) and any(ct.plain(x) == sd["ma"].lower() for x in parts[1:])
    code = sd["ma"] if other else cfg["ma"]
    done = [o for o in cfg.get("lenh", []) if o["trang_thai"] == "khop"
            and (o.get("quy") == code and o.get("loai") != "doi" if other else goes_main(cfg, o))]
    try:
        new = ts.number(parts[0] if parts else "")
    except ValueError:
        return "Gõ số ccq theo Fmarket, ví dụ: /dautu ccq 66,43" + (f" (lệnh {sd['ma']}: /dautu ccq 36,7 "
                                                                    f"{sd['ma'].lower()})" if sd else "")
    if not done or new <= 0:
        return "Chưa có lệnh nào đã khớp để sửa"
    o = done[-1]
    data = ts.load()
    hold = holding(data, cfg, code)
    cost = hold["sl"] * (hold.get("gia_von") or 0)
    hold["sl"] = round(hold["sl"] - o["ccq"] + new, 2)
    hold["gia_von"] = cost / hold["sl"] if hold["sl"] else None
    o["ccq"], o["nav"] = new, o["tien"] / new
    ts.save(data)
    save(cfg)
    return (f"✅ Đã sửa lệnh {code} phiên {o['phien'][8:]}/{o['phien'][5:7]}: {units_text(new)} ccq. Đang có "
            f"{units_text(hold['sl'])} ccq {code}")


DATE = re.compile(r"(?<![\d/])(\d{1,2})/(\d{1,2})(?:/(\d{4}))?(?![\d/])")


def read_date(text, day):
    """'9/11' -> ngày (năm nay; xa hơn 6 tháng tới thì là năm trước); None nếu không có ngày."""
    m = DATE.search(text)
    if not m:
        return None
    try:
        d = date(int(m[3] or day.year), int(m[2]), int(m[1]))
    except ValueError:
        return None
    if not m[3] and (d - day).days > 180:
        d = d.replace(year=d.year - 1)
    return d


def skip(ym):
    cfg = config()
    if ym != current_period(cfg):
        return "Kỳ này đã qua"
    if any(o["ky"] == ym for o in cfg.get("lenh", [])):
        return "Tháng này đã đặt lệnh, không tạm dừng được"
    cfg.setdefault("ky", {}).setdefault(ym, {})["bo"] = True
    save(cfg)
    return f"⏸ Tạm dừng góp tháng {ym_text(ym)}: kế hoạch không cộng thêm tháng này. Tháng sau bot tính tiếp"


# ---- Lệnh /dautu -----------------------------------------------------------------------

MONEY_WORDS = {"tr", "trieu", "k", "nghin", "ngan", "d", "dong", "thang"}


def start(args, switch=False):
    cfg = config()
    found = ct.parse_amount(" ".join(args))
    gop = found[0] if found else DEFAULT_GOP
    code = next((a.upper() for a in args if re.fullmatch(r"[A-Za-z][A-Za-z0-9-]{2,11}", a)
                 and ct.plain(a) not in MONEY_WORDS), cfg.get("ma") or DEFAULT_FUND)
    if cfg.get("ma") == code:
        cfg.pop("tat", None)
        if found:
            cfg.setdefault("gop", {})[current_period(cfg)] = gop
        save(cfg)
        return view()
    if cfg.get("ma") and cfg.get("lenh") and not switch:
        return (f"Đang đầu tư {cfg['ma']}. Đổi sang {html.escape(code)} thì kế hoạch bắt đầu lại từ đầu (lịch sử lệnh "
                f"{cfg['ma']} không tính nữa, ccq đã mua vẫn ở /taisan): /dautu doiquy {html.escape(code)} {money(gop)}")
    fund = find_fund(code)
    if not fund:
        return f"Không thấy quỹ {html.escape(code)} trên Fmarket (gõ đúng mã, ví dụ VMEEF, VESAF, SSISCA, DCDS)"
    ym = ym_of(ct.today())
    data = ts.load()
    hold = next((it for it in data["items"] if it["loai"] == "quy" and it["ma"] == code), None)
    base = 0
    if hold:  # đã có ccq từ trước: tính vào điểm xuất phát của kế hoạch
        price = ts.prices("quy", [code])[0].get(code)
        base = round(hold["sl"] * price) if price else round(hold["sl"] * (hold.get("gia_von") or 0))
    cfg = {"ma": code, "id": fund[0], "ten": fund[1], "bat_dau": ym, "goc": base, "gop": {ym: gop},
           "tang": DEFAULT_TANG, "nap": {}, "ky": {}, "lenh": []}
    save(cfg)
    wait_item(data, cfg)
    ts.save(data)
    lines = [f"✅ Đã bật đầu tư {code} ({html.escape(fund[1].title())}): góp {money(gop)}/tháng từ tháng {ym_text(ym)}."]
    if base:
        lines.append(f"Đã tính {units_text(hold['sl'])} ccq đang có ({money(base)}) vào điểm xuất phát.")
    lines.append("Đã mua trong tháng này (trước khi bật) thì ghi lại: /dautu dadat 1tr 9/11 (số tiền, ngày đặt lệnh; "
                 "bot tự tính phiên khớp).")
    if not kho.get(ts.K_SALARY):
        lines.append("Đặt ngày lương để bot nhắc để tiền vào quỹ chờ: /luong 5 số_tiền_lương")
    text, rows = view()
    return "\n".join(lines) + "\n\n" + text, rows


def dautu(args):
    if not kho.ready():
        return ct.NEED_STORE
    word = ct.plain(args[0]) if args else ""
    rest = " ".join(args[1:])
    if word in ("huongdan", "help", "?"):
        return USAGE
    cfg = config()
    if word in ("bat", "on") and cfg.get("ma"):
        cfg.pop("tat", None)
        save(cfg)
        return view()
    if word in ("batdau", "bat", "on", "doiquy"):
        return start(args[1:], switch=word == "doiquy")
    if not cfg.get("ma"):
        return view()
    if not word:
        return view(fresh=False)
    if word in ("tat", "off", "dung"):
        cfg["tat"] = True
        save(cfg)
        return f"Đã tắt nhắc đầu tư {cfg['ma']} (dữ liệu giữ nguyên). Bật lại: /dautu bat"
    if word in ("lichsu", "lenh"):
        return history_text()
    if word == "baocao":
        cfg["baocao_toi"] = ct.plain(rest) not in ("tat", "off", "khong")
        save(cfg)
        return ("✅ Tối các ngày có NAV mới (khoảng 20h) bot báo giá trị, lãi/lỗ các quỹ" if cfg["baocao_toi"]
                else "Đã tắt tin tối về lãi/lỗ các quỹ. Bật lại: /dautu baocao bat")
    if word in ("bieudo", "bd"):
        return chart_reply()
    if word in ("bo", "tamdung", "boqua"):
        return skip(current_period(cfg))
    if word == "ccq":
        return fix_units(rest)
    if word in ("tang", "muctang"):
        try:
            g = ts.number(rest.replace("%", "")) / 100
        except ValueError:
            g = 0
        if not 0.003 <= g <= 0.02:
            return "Mức tăng của kế hoạch mỗi tháng, từ 0,3% tới 2%: /dautu tang 1%"
        cfg["tang"] = g
        save(cfg)
        return view()
    found = ct.parse_amount(rest)
    if word in ("gop", "moithang"):
        if not found:
            return USAGE
        ym = current_period(cfg)
        cfg.setdefault("gop", {})[ym] = found[0]
        save(cfg)
        text, rows = view()
        return f"✅ Từ tháng {ym_text(ym)} góp {money(found[0])}/tháng\n\n" + text, rows
    if word in ("nap", "them", "de"):
        if not found:
            return USAGE
        left = add_money(cfg, found[0], current_period(cfg))
        save(cfg)
        return f"✅ Đã thêm {money(found[0])} vào quỹ chờ {cfg['ma']}: {money(left)}"
    if word == "rut":
        if not found:
            return USAGE
        data = ts.load()
        item = wait_item(data, cfg)
        item["tien"] = max(0, item["tien"] - found[0])
        ts.save(data)
        return f"Đã rút {money(found[0])} khỏi quỹ chờ, còn {money(item['tien'])}"
    sd = side(cfg)
    if word == "quycho" and not found:
        return set_side(cfg, rest)
    if sd and word in (sd["ma"].lower(), "gopthem"):
        if not found:
            return f"Góp thêm mỗi tháng vào {sd['ma']} (ngoài phần VA), ví dụ: /dautu {sd['ma'].lower()} 1tr"
        ym = current_period(cfg)
        cfg.setdefault("them", {})[ym] = found[0]
        save(cfg)
        text, rows = view()
        return f"✅ Từ tháng {ym_text(ym)} góp thêm {money(found[0])}/tháng vào {sd['ma']}\n\n" + text, rows
    if word in ("taicocau", "gopmotlan", "rai"):
        return restructure(cfg, rest, found, now_vn())
    if word in ("doi", "hoandoi"):
        try:
            units = ts.number(rest.split()[0]) if rest.split() else 0
        except ValueError:
            units = 0
        if units <= 0:
            return "Gõ số ccq đã hoán đổi, ví dụ: /dautu doi 125,5 (thêm ngày đặt nếu là lệnh cũ: /dautu doi 125,5 9/11)"
        now = now_vn()
        spec = order_spec(cfg, " ".join(rest.split()[1:]), now, sd)
        if isinstance(spec, str):
            return spec
        day, trading, ym = spec
        return record_switch(units, trading, now, ym, day)
    if word in ("quycho", "sodu"):
        if not found:
            return USAGE
        data = ts.load()
        wait_item(data, cfg)["tien"] = found[0]
        ts.save(data)
        return f"✅ Số dư quỹ chờ {cfg['ma']}: {money(found[0])}"
    if word in ("dadat", "mua", "datlenh"):
        if not found:
            return USAGE
        now = now_vn()
        other = rest[:found[1]] + " " + rest[found[2]:]
        fund = sd if sd and sd["ma"].lower() in ct.plain(other).split() else None
        spec = order_spec(cfg, other, now, fund)
        if isinstance(spec, str):
            return spec
        day, trading, ym = spec
        return record_order(found[0], trading, now, ym, day, fund=fund)
    return USAGE


def restructure(cfg, rest, found, now):
    """/dautu taicocau 15,5tr [3 thang] [80%] [ngày đặt]: đã mua quỹ chờ bằng một khoản tiền lớn (ví dụ tiền bán cổ
    phiếu); phần cổ phiếu (mặc định 80%) được cộng dần vào kế hoạch quỹ chính trong N tháng (mặc định 3), mỗi cuối
    tháng hoán đổi từ quỹ chờ theo VA. /dautu taicocau xoa: bỏ phần rải còn lại."""
    sd = side(cfg)
    if ct.plain(rest).split()[:1] == ["xoa"]:
        ym = current_period(cfg, now)
        left = {k: v for k, v in cfg.get("ke_hoach_them", {}).items() if k >= ym}
        cfg["ke_hoach_them"] = {k: v for k, v in cfg.get("ke_hoach_them", {}).items() if k < ym}
        save(cfg)
        return f"Đã bỏ phần rải còn lại ({money(sum(left.values()))}); tiền vẫn ở {sd['ma'] if sd else 'quỹ chờ'}"
    if not sd:
        return "Cần quỹ chờ là quỹ trái phiếu trước: /dautu quycho VFF"
    if not found:
        return ("Ghi khoản tiền lớn đã mua VFF và rải dần vào VMEEF: /dautu taicocau 15,5tr (mặc định rải phần cổ phiếu "
                "80% trong 3 tháng; đổi: /dautu taicocau 15,5tr 6 thang 70%)")
    amount = found[0]
    other = rest[:found[1]] + " " + rest[found[2]:]
    plain = ct.plain(other)
    n = int(m[1]) if (m := re.search(r"(\d{1,2})\s*thang", plain)) else 3
    share = int(m[1]) if (m := re.search(r"(\d{1,3})\s*%", other)) else 80
    if not 1 <= n <= 24 or not 0 <= share <= 100:
        return "Số tháng từ 1 tới 24, tỉ lệ cổ phiếu từ 0% tới 100%, ví dụ: /dautu taicocau 15,5tr 3 thang 80%"
    date_text = re.sub(r"\d{1,2}\s*(thang|tháng)|\d{1,3}\s*%", " ", other)
    spec = order_spec(cfg, date_text, now, sd)
    if isinstance(spec, str):
        return spec
    day, trading, ym = spec
    note = record_order(amount, trading, now, ym, day, fund=sd, quiet=True, lump=True)
    cfg = config()
    equity = round(amount * share / 100, -4)
    per = (equity / n) // 10_000 * 10_000
    start = current_period(cfg, now)
    plan = cfg.setdefault("ke_hoach_them", {})
    for i in range(n):
        m_ = ym_add(start, i)
        plan[m_] = plan.get(m_, 0) + (per if i < n - 1 else equity - per * (n - 1))
    save(cfg)
    steps = []
    for i in range(n):
        m_ = ym_add(start, i)
        part = per if i < n - 1 else equity - per * (n - 1)
        steps.append(f"• Hạn cuối tháng {int(m_[5:])}/{m_[:4]} (khoảng {last_weekday(m_):%d/%m}): thêm ~{money(part)}")
    return "\n".join([note,
                      f"🔁 Rải {money(equity)} ({share}%) từ {sd['ma']} vào {cfg['ma']} trong {n} tháng, "
                      f"{money(amount - equity)} giữ lại ở {sd['ma']}:", *steps,
                      f"Ngày hạn bot nhắc như thường lệ, tin nhắc gộp sẵn phần này vào lệnh hoán đổi {sd['ma']} → "
                      f"{cfg['ma']}. VA vẫn chỉnh: {cfg['ma']} giảm thì hoán đổi nhiều hơn, tăng nhanh thì ít hơn. "
                      "Bỏ phần còn lại: /dautu taicocau xoa"])


def set_side(cfg, text):
    """/dautu quycho VFF: quỹ chờ là quỹ trái phiếu (hoán đổi miễn phí sang quỹ chính); /dautu quycho tien: tiền gửi."""
    word = ct.plain(text).strip()
    if word in ("tien", "tietkiem", "guitien"):
        cfg.pop("cho", None)
        save(cfg)
        return "✅ Quỹ chờ là tiền gửi tiết kiệm như trước"
    code = text.strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9-]{2,11}", code) or code == cfg["ma"]:
        return "Gõ mã quỹ trái phiếu trên Fmarket, ví dụ: /dautu quycho VFF (về tiền gửi: /dautu quycho tien)"
    fund = find_fund(code)
    if not fund:
        return f"Không thấy quỹ {html.escape(code)} trên Fmarket"
    cfg["cho"] = {"ma": code, "id": fund[0]}
    save(cfg)
    sess = session(cfg["cho"])
    text, rows = view()
    return (f"✅ Quỹ chờ là {code} ({html.escape(fund[1].title())}). Tiền góp mua {cfg['ma']} trước, phần VA chưa mua "
            f"thì vào {code}; tháng cần mua nhiều hơn tiền góp thì hoán đổi từ {code} (miễn phí). {code} vừa là phần "
            f"trái phiếu của danh mục, vừa là tiền chờ.\nPhiên {code} kế tiếp: {sess['phien']:%d/%m} (đóng sổ "
            f"{sess['dong']:%H:%M %d/%m}). Góp thêm mỗi tháng vào {code}: /dautu {code.lower()} 1tr\n\n" + text), rows


def from_text(text, now):
    """Tin "mua VMEEF 3tr" (lệnh đặt hôm khác thì thêm ngày đặt: "mua VMEEF 1tr 9/11"): ghi lệnh; None nếu không
    phải."""
    t = ct.plain(text).split()
    if len(t) < 3 or t[0] != "mua":
        return None
    cfg = config()
    sd = side(cfg)
    codes = [cfg["ma"].lower()] + ([sd["ma"].lower()] if sd else []) if active(cfg) else []
    code = next((c for c in t[1:3] if c in codes), None)
    if not code:
        return None
    found = ct.parse_amount(text)
    if not found:
        return None
    fund = sd if sd and code == sd["ma"].lower() else None
    spec = order_spec(cfg, text[:found[1]] + " " + text[found[2]:], now, fund)
    if isinstance(spec, str):
        return spec
    day, trading, ym = spec
    return record_order(found[0], trading, now, ym, day, fund=fund)


def on_button(arg, message, now):
    """Nút "dt:...": (thông báo nhỏ, việc tiếp theo)."""
    kind, _, value = arg.partition(":")
    if kind == "xem":
        return "Đang lấy NAV…", ("edit", lambda: view(fresh=True))
    if kind == "dat":
        amount, day, period = (value.split(":") + ["", ""])[:3]
        cfg = config()
        trading = datetime.strptime(day, "%Y%m%d").date() if day else None
        if any(o["tien"] == int(amount) and o["phien"] == (trading.isoformat() if trading else "")
               for o in cfg.get("lenh", [])):
            return "Lệnh này đã ghi rồi", None
        note = record_order(int(amount), trading, now, period or None)
        return "Đã ghi lệnh", ("edit", lambda: (note, [[("📈 Đầu tư", "dt:xem"), ("🧾 Lệnh", "dt:ls")]]))
    if kind == "dat2":
        direct, side_buy, units, ym, main_day, side_day = value.split(":")
        cfg = config()
        if any(o["ky"] == ym and o["dat"] == now.date().isoformat() for o in cfg.get("lenh", [])):
            return "Các lệnh này đã ghi rồi", None
        note = record_plan(int(direct), int(side_buy), int(units) / 100, ym,
                           datetime.strptime(main_day, "%Y%m%d").date(), datetime.strptime(side_day, "%Y%m%d").date(), now)
        return "Đã ghi các lệnh", ("edit", lambda: (note, [[("📈 Đầu tư", "dt:xem"), ("🧾 Lệnh", "dt:ls")]]))
    if kind == "bo":
        note = skip(value)
        return note[:190], ("edit", lambda: view())
    if kind == "nap" and value.isdigit():
        cfg = config()
        left = add_money(cfg, int(value), current_period(cfg))
        save(cfg)
        toast = f"Đã để {money(int(value))} vào quỹ chờ ({money(left)})"
        if (message.get("text") or "").startswith("📋"):  # nút trên tin chia lương: vẽ lại tin đó
            import kehoach
            return toast, ("edit", lambda: kehoach.plan(now.date()))
        rows = [[b for b in row if not b[1].startswith("dt:nap")] for row in ct.keyboard_rows(message)]
        return toast, ("buttons", lambda: [r for r in rows if r])
    if kind == "bd":
        return "Đang vẽ biểu đồ…", ("send", chart_reply)
    if kind == "ls":
        return None, ("edit", history_text)
    return None, None


# ---- Dùng ở chỗ khác: chia lương, bản tin tối, việc theo giờ ---------------------------

def salary_part(day):
    """Phần đầu tư trong gợi ý chia lương: (số nên để tháng này, đã để, ghi chú) hoặc None nếu chưa bật."""
    cfg = config()
    if not active(cfg):
        return None
    ym = ym_of(day)
    gop = total_of(cfg, ym)
    added = cfg.get("nap", {}).get(ym, 0)
    note = ""
    try:
        import duphong
        f = duphong.status(day)
        if f["monthly"] and f["covered"] < 1:
            return {"ma": cfg["ma"], "gop": 0, "added": added, "note": "tạm dừng: ưu tiên quỹ dự phòng tới mốc 1 tháng chi"}
    except Exception as e:
        print(f"[lỗi] quỹ dự phòng khi chia lương: {e!r}", file=sys.stderr)
    if (cfg.get("ky", {}).get(ym) or {}).get("bo"):
        gop, note = 0, "tháng này tạm dừng"
    return {"ma": cfg["ma"], "gop": gop, "added": added, "note": note}


def evening_line(day):
    """Dòng NAV quỹ cho bản tin tối của bot bản tin; None nếu chưa bật."""
    cfg = config()
    if not active(cfg):
        return None
    navs = nav_history(cfg, fresh=True)
    if len(navs) < 2:
        return None
    (_, v0), (d1, v1) = navs[-2], navs[-1]
    peak = max(v for d, v in navs if (d1 - d).days <= 365)
    when = "hôm nay" if d1 == day else f"{d1:%d/%m}"
    line = f"💹 {cfg['ma']} {vn_num(v1, 2)}đ ({when}, {pct(v1 / v0 - 1)}) · cách đỉnh 52 tuần {pct(v1 / peak - 1)}"
    sd = side(cfg)
    if sd:
        snavs = nav_history(sd)
        if len(snavs) >= 2:
            year = [v for d, v in snavs if (snavs[-1][0] - d).days <= 365]
            line += f" · {sd['ma']} {vn_num(snavs[-1][1], 2)}đ ({pct(snavs[-1][1] / year[0] - 1)} 12 tháng)"
    return line


def holdings_alert(cfg):
    """Fmarket vừa cập nhật danh mục: tin báo nếu có cổ phiếu trong WATCH; None nếu không có gì mới."""
    info = fund_info(cfg, fresh=True) or {}
    when = info.get("top_luc")
    if not when or when == cfg.get("top_luc"):
        return None
    cfg["top_luc"] = when
    save(cfg)
    flagged = [h for h in info.get("top", []) if h["ma"] in WATCH]
    if not flagged:
        return None
    return (f"⚠️ <b>{cfg['ma']}</b> vừa cập nhật danh mục ({when}): top 10 có "
            + ", ".join(f"{h['ma']} {vn_num(h['tyle'] or 0, 1)}%" for h in flagged) + ". Xem: /dautu")


def daily_report(now):
    """Tin tối (từ 20h, ngày có NAV mới), ngắn gọn: mỗi quỹ đang giữ một dòng (giá trị theo NAV, lãi/lỗ so với tiền
    gốc), một dòng tổng. None nếu tắt, chưa có gì, hoặc hôm nay không có NAV mới (cuối tuần, ngày lễ)."""
    cfg = config()
    if not active(cfg) or cfg.get("baocao_toi") is False:
        return None
    data = ts.load()
    lines, fresh_today = [], False
    total_value = total_cost = 0.0
    for f in [cfg] + ([side(cfg)] if side(cfg) else []):
        hold = holding(data, cfg, f["ma"])
        navs = nav_history(f, fresh=True) if hold and hold["sl"] > 0 else []
        if not navs:
            continue
        day, nav = navs[-1]
        fresh_today |= day == now.date()
        value, cost = hold["sl"] * nav, hold["sl"] * (hold.get("gia_von") or nav)
        total_value += value
        total_cost += cost
        lines.append(f"{f['ma']} <b>{money(value)}</b> · {gain_text(value - cost, cost)}")
    if not lines or not fresh_today:
        return None
    if len(lines) > 1:
        lines.append(f"Tổng <b>{money(total_value)}</b> · {gain_text(total_value - total_cost, total_cost)}")
    pending = sum(o["tien"] for o in cfg.get("lenh", []) if o["trang_thai"] == "cho")
    if pending:
        lines.append(f"⏳ {money(pending)} đang chờ khớp")
    return f"📊 <b>Quỹ tối {now:%d/%m}</b> (so với tiền gốc)\n" + "\n".join(lines), [[("📈 Chi tiết", "dt:xem")]]


def fix_button(code):
    return (f"✏️ Fmarket báo số ccq {code} khác", f"y:them:sua_ccq:{code}")


def match_job(now):
    """Sau 17h: lệnh đã có NAV thì tính ccq. Trả các tin báo [(câu báo, nút)]; lệnh mua có nút sửa số ccq."""
    if (now.hour, now.minute) < (17, 0) or not active():
        return []
    return [(note, ([[fix_button(code)]] if code else []) + [[("📈 Đầu tư", "dt:xem"), ("🧾 Lệnh", "dt:ls")]])
            for code, note in match_details(now)]

