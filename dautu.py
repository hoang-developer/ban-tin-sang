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
         "/dautu bo: tạm dừng tháng này · /dautu lichsu: các lệnh · /dautu tat, /dautu bat")


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
    store = kho.get(K_NAV, {}) or {}
    if store.get("ma") == cfg["ma"] and store.get("nav") and not fresh and \
            (now_vn() - datetime.fromisoformat(store["luc"])).total_seconds() < 2 * 3600:
        return [(date.fromisoformat(d), v) for d, v in store["nav"]]
    try:
        rows = ts.http_json(f"{FMARKET}/product/get-nav-history",
                            {"isAllData": 1, "productId": cfg["id"], "fromDate": None,
                             "toDate": now_vn().strftime("%Y%m%d")})["data"]
        navs = sorted((p["navDate"], float(p["nav"])) for p in rows if p.get("nav"))[-400:]
        if navs:
            kho.put(K_NAV, {"ma": cfg["ma"], "luc": now_vn().isoformat(timespec="minutes"), "nav": navs})
            return [(date.fromisoformat(d), v) for d, v in navs]
    except Exception as e:
        print(f"[lỗi] NAV {cfg['ma']}: {e!r}", file=sys.stderr)
    if store.get("ma") == cfg["ma"]:
        return [(date.fromisoformat(d), v) for d, v in store.get("nav", [])]
    return []


def fund_info(cfg, fresh=False):
    """Chi tiết quỹ của Fmarket (phiên giao dịch kế tiếp, top 10 mã, phí); lưu 1 tiếng, lỗi thì dùng bản cũ."""
    store = kho.get(K_INFO, {}) or {}
    if store.get("ma") == cfg["ma"] and not fresh and \
            (now_vn() - datetime.fromisoformat(store["luc"])).total_seconds() < 3600:
        return store["data"]
    try:
        d = ts.http_json(f"{FMARKET}/products/{cfg['id']}")["data"]
        keep = {"phien": d.get("productTradingSession"), "top": [
            {"ma": h.get("stockCode"), "nganh": h.get("industry"), "tyle": h.get("netAssetPercent")}
            for h in d.get("productTopHoldingList") or []],
            "top_luc": (d.get("productFund") or {}).get("updateAssetHoldingTime")}
        kho.put(K_INFO, {"ma": cfg["ma"], "luc": now_vn().isoformat(timespec="minutes"), "data": keep})
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


def holding(data, cfg):
    return next((it for it in data["items"] if it["loai"] == "quy" and it["ma"] == cfg["ma"]), None)


def gop_of(cfg, ym):
    if (cfg.get("ky", {}).get(ym) or {}).get("bo"):
        return 0
    steps = [(k, v) for k, v in cfg.get("gop", {}).items() if k <= ym]
    return max(steps)[1] if steps else 0


def target(cfg, ym):
    """Giá trị kế hoạch của kỳ ym."""
    value = None
    for m in months(cfg["bat_dau"], ym):
        value = cfg.get("goc", 0) + gop_of(cfg, m) if value is None else value * (1 + cfg.get("tang", DEFAULT_TANG)) + gop_of(cfg, m)
    return value or 0


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
                o["tien"] for o in cfg.get("lenh", []) if o["trang_thai"] == "cho")
        unpaid = max(0, gop_of(cfg, ym) - cfg.get("nap", {}).get(ym, 0))
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
    pending = sum(o["tien"] for o in cfg.get("lenh", []) if o["trang_thai"] == "cho")
    value = units * nav + pending if nav else pending + (units * hold["gia_von"] if hold and hold.get("gia_von") else 0)
    plan = target(cfg, ym)
    k = cfg.get("ky", {}).get(ym) or {}
    cash = next((it["tien"] for it in data["items"] if it["loai"] == "tien" and it.get("dautu")), 0)
    unpaid = 0 if k.get("bo") else max(0, gop_of(cfg, ym) - cfg.get("nap", {}).get(ym, 0))
    available = cash + unpaid
    need = plan - value
    buy = max(0, min(need, available)) // STEP * STEP
    buy = 0 if buy < MIN_ORDER else buy
    ordered = sum(o["tien"] for o in cfg.get("lenh", []) if o["ky"] == ym)
    invested = sum(o["tien"] for o in cfg.get("lenh", []))
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
            "short": need > available + STEP, "ordered": ordered, "invested": invested, "cost": cost,
            "contributed": sum(cfg.get("nap", {}).values()) + cfg.get("goc", 0),
            "drawdown": nav / peak - 1 if peak and nav else None,
            "month_change": nav / month_start[-1] - 1 if month_start and nav else None,
            "fund": fund, "below_milestone": bool(fund and fund["monthly"] and fund["covered"] < 1)}


# ---- Câu trả lời -----------------------------------------------------------------------

def pct(x):
    return f"{x * 100:+.1f}%".replace(".", ",")


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
    elif s["buy"]:
        lines.append(f"👉 <b>Mua {ct.vnd(s['buy'])}</b>" + (
            f" (hết tiền đang có; còn thiếu {money(s['need'] - s['buy'])} so với kế hoạch, tháng sau tự bù)"
            if s["short"] else ""))
    elif s["need"] > 0:
        lines.append(f"👉 Không mua: cần thêm {money(s['need'])} nhưng chưa có tiền (quỹ chờ {money(s['cash'])})")
    else:
        lines.append(f"👉 <b>Tháng này không mua</b>: quỹ đang cao hơn kế hoạch {money(-s['need'])}; "
                     f"để {money(gop_of(cfg, s['ym']))} vào quỹ chờ (gửi tiết kiệm), chờ lúc quỹ giảm thì mua nhiều hơn")
    lines.append(f"💰 Tiền đang có: quỹ chờ {money(s['cash'])}"
                 + (f" + góp tháng này chưa để {money(s['unpaid'])}" if s["unpaid"] else ""))
    if s["below_milestone"]:
        f = s["fund"]
        lines.append(f"⚠️ Quỹ dự phòng mới đủ {vn_num(f['covered'], 1)} tháng chi (mốc đầu: 1 tháng, còn thiếu "
                     f"{money(f['monthly'] - f['balance'])}): nên ưu tiên nạp quỹ dự phòng, tạm dừng góp tháng này")
    return lines


def summary_line(s):
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
    lines = [f"📈 <b>{cfg['ma']}: góp {money(gop_of(cfg, s['ym']) or cfg['gop'][max(cfg['gop'])])}/tháng</b>"
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
    if s["buy"] and not s["skip"] and final:
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
    if second and (not s["buy"] or s["skip"] or s["ordered"]):
        return None
    sess = session(cfg, now)
    title = (f"📈 <b>{cfg['ma']}: hôm nay là hạn đặt lệnh tháng {int(s['ym'][5:])}</b>" if not second else
             f"⏰ <b>{cfg['ma']}: còn tới 14:40 để đặt lệnh tháng {int(s['ym'][5:])}</b>")
    lines = [title, f"Đặt trên Fmarket trước <b>14:40 {sess['dong']:%d/%m}</b> → khớp NAV phiên {sess['phien']:%d/%m}",
             nav_line(cfg, s), *decision_lines(cfg, s), summary_line(s), NOT_ADVICE]
    return "\n".join(lines), buttons(cfg, s, sess)


def history_text():
    cfg = config()
    orders = cfg.get("lenh", [])
    if not orders:
        return "Chưa có lệnh nào. Đặt xong trên Fmarket thì bấm ✅ hoặc gõ /dautu dadat 3tr", [[("📈 Đầu tư", "dt:xem")]]
    lines = [f"🧾 <b>Các lệnh {cfg['ma']}</b>"]
    for o in orders[-15:]:
        when = f"đặt {o['dat'][8:]}/{o['dat'][5:7]} → phiên {o['phien'][8:]}/{o['phien'][5:7]}"
        if o["trang_thai"] == "khop":
            lines.append(f"• {when}: {money(o['tien'])} → {units_text(o['ccq'])} ccq, NAV {vn_num(o['nav'], 2)}")
        else:
            lines.append(f"• {when}: {money(o['tien'])} · chờ khớp")
    return "\n".join(lines), [[("📈 Đầu tư", "dt:xem"), ct.BACK]]


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
    known = [x for x, _ in nav_history(cfg) if (x >= d if include else x > d)]
    if known:
        return known[0]
    x = d if include else d + timedelta(days=1)
    while x.weekday() >= 5:
        x += timedelta(days=1)
    return x


def order_spec(cfg, text, now):
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
    return day, next_trading(cfg, cutoff), ym_of(cutoff)


def record_order(amount, trading_day=None, now=None, period=None, order_day=None):
    """Đã đặt lệnh mua `amount`: trừ quỹ chờ (thiếu thì phần thiếu tính là góp thêm của tháng), ghi lệnh chờ khớp.
    period: kỳ của lệnh (nút bấm mang theo); không có thì suy từ ngày đóng sổ của phiên khớp."""
    now = now or now_vn()
    order_day = order_day or now.date()
    cfg = config()
    close_periods(cfg, now)
    sess = session(cfg, now)
    trading = trading_day or sess["phien"]
    ym = period or (ym_of(cutoff_day(trading_day)) if trading_day else current_period(cfg, now))
    if ym < cfg["bat_dau"]:
        ym = cfg["bat_dau"]
    data = ts.load()
    item = wait_item(data, cfg)
    if item["tien"] < amount:
        extra = amount - item["tien"]
        cfg.setdefault("nap", {})[ym] = cfg.get("nap", {}).get(ym, 0) + extra
        item["tien"] = 0
    else:
        item["tien"] -= amount
    order = {"id": max([o["id"] for o in cfg.get("lenh", [])] + [0]) + 1, "ky": ym, "tien": amount,
             "dat": order_day.isoformat(), "phien": trading.isoformat(), "trang_thai": "cho"}
    cfg.setdefault("lenh", []).append(order)
    ts.save(data)
    save(cfg)
    matched = match_orders(now)
    note = (f"✅ Đã ghi lệnh mua {cfg['ma']} {ct.vnd(amount)}: đặt {order_day:%d/%m} → khớp NAV phiên "
            f"<b>{trading:%d/%m}</b>. Quỹ chờ còn {money(item['tien'])}.")
    if matched:
        return note + "\n" + matched[0]
    return note + " Tối ngày khớp (khoảng 17h có NAV) bot tính số ccq và cộng vào /taisan."


def match_orders(now=None):
    """Lệnh chờ khớp đã có NAV phiên khớp: tính số ccq, cộng vào /taisan. Trả các câu báo."""
    now = now or now_vn()
    cfg = config()
    due = [o for o in cfg.get("lenh", []) if o["trang_thai"] == "cho" and o["phien"] <= now.date().isoformat()]
    if not due:
        return []
    navs = dict(nav_history(cfg))
    if any(date.fromisoformat(o["phien"]) not in navs for o in due):
        navs = dict(nav_history(cfg, fresh=True))
    data = ts.load()
    notes = []
    for o in due:
        wanted = date.fromisoformat(o["phien"])
        found = sorted(d for d in navs if wanted <= d <= wanted + timedelta(days=10))  # nghỉ lễ: phiên sau đó
        if not found:
            continue
        nav = navs[found[0]]
        o["phien"] = found[0].isoformat()
        ccq = round(o["tien"] / nav, 2)
        hold = holding(data, cfg)
        if hold is None:
            hold = {"id": ts.new_id(data), "loai": "quy", "ma": cfg["ma"], "sl": 0, "gia_von": None}
            data["items"].append(hold)
        cost = hold["sl"] * (hold.get("gia_von") or 0) + o["tien"]
        hold["sl"] = round(hold["sl"] + ccq, 2)
        hold["gia_von"] = cost / hold["sl"]
        o.update({"trang_thai": "khop", "nav": nav, "ccq": ccq})
        notes.append(f"✅ Lệnh {cfg['ma']} {ct.vnd(o['tien'])} đã khớp phiên {o['phien'][8:]}/{o['phien'][5:7]}: "
                     f"NAV {vn_num(nav, 2)}đ → <b>{units_text(ccq)} ccq</b>. Đang có {units_text(hold['sl'])} ccq, "
                     f"giá vốn {vn_num(hold['gia_von'], 0)}đ.\nSố ccq trên Fmarket khác thì sửa: /dautu ccq số_ccq")
    if notes:
        ts.save(data)
        save(cfg)
    return notes


def fix_units(text):
    cfg = config()
    done = [o for o in cfg.get("lenh", []) if o["trang_thai"] == "khop"]
    try:
        new = ts.number(text)
    except ValueError:
        return "Gõ số ccq theo Fmarket, ví dụ: /dautu ccq 66,43"
    if not done or new <= 0:
        return "Chưa có lệnh nào đã khớp để sửa"
    o = done[-1]
    data = ts.load()
    hold = holding(data, cfg)
    cost = hold["sl"] * (hold.get("gia_von") or 0)
    hold["sl"] = round(hold["sl"] - o["ccq"] + new, 2)
    hold["gia_von"] = cost / hold["sl"] if hold["sl"] else None
    o["ccq"], o["nav"] = new, o["tien"] / new
    ts.save(data)
    save(cfg)
    return f"✅ Đã sửa lệnh phiên {o['phien'][8:]}/{o['phien'][5:7]}: {units_text(new)} ccq. Đang có {units_text(hold['sl'])} ccq"


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
        spec = order_spec(cfg, rest[:found[1]] + " " + rest[found[2]:], now)
        if isinstance(spec, str):
            return spec
        day, trading, ym = spec
        return record_order(found[0], trading, now, ym, day)
    return USAGE


def from_text(text, now):
    """Tin "mua VMEEF 3tr" (lệnh đặt hôm khác thì thêm ngày đặt: "mua VMEEF 1tr 9/11"): ghi lệnh; None nếu không
    phải."""
    t = ct.plain(text).split()
    if len(t) < 3 or t[0] != "mua":
        return None
    cfg = config()
    if not active(cfg) or cfg["ma"].lower() not in t[1:3]:
        return None
    found = ct.parse_amount(text)
    if not found:
        return None
    spec = order_spec(cfg, text[:found[1]] + " " + text[found[2]:], now)
    if isinstance(spec, str):
        return spec
    day, trading, ym = spec
    return record_order(found[0], trading, now, ym, day)


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
    gop = gop_of(cfg, ym)
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
    return (f"💹 {cfg['ma']} {vn_num(v1, 2)}đ ({when}, {pct(v1 / v0 - 1)}) · cách đỉnh 52 tuần {pct(v1 / peak - 1)}")


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


def match_job(now):
    """Sau 17h: lệnh đã có NAV thì tính ccq. Trả các câu báo."""
    if (now.hour, now.minute) < (17, 0) or not active():
        return []
    return match_orders(now)

