"""Đầu tư quỹ mở hằng tháng theo Value Averaging (Mặc định quỹ VMEEF trên Fmarket): lệnh /dautu, nút dt:, tin nhắn
"mua VMEEF 3tr", màn hình và tin nhắc. Đọc lệnh, gọi service, nhờ presentation dựng tin.

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

Các hàm ở đây giữ tên và dạng giá trị trả về mà các màn hình khác (menu, trợ lý, tin sáng/tối, chia lương) đang gọi.
"""
import html
import re
import sys
from datetime import datetime, timedelta

import sochitieu as ct  # module cũ ở gốc: đọc số tiền, ngày hôm nay
from domain.common.money import number
from domain.dautu.calendar import months, ym_add, ym_of, ym_text  # noqa: F401
from domain.dautu.plan import (DEFAULT_FUND, DEFAULT_GOP, DEFAULT_TANG, MIN_ORDER, STEP, WATCH,  # noqa: F401
                               gop_of, holding, is_active, side, them_of, total_of)
from domain.dautu.text import money, units_text
from infrastructure import quickchart
from interface import common
from interface.kehoach import plan as kehoach
from presentation.dautu import view as pview
from presentation.dautu.view import USAGE, fix_button, last_weekday
from repositories.dautu import fund as fund_repo
from repositories.luong import salary as salary_repo
from repositories.taisan import assets as assets_repo
from services.dautu import market
from services.dautu.market import (current_period, find_fund, fund_info, is_deadline, nav_history,  # noqa: F401
                                   next_trading, session)
from services.dautu.orders import (add_money, fix_units, match_details, match_orders, order_spec,  # noqa: F401
                                   record_order, record_plan, record_switch, skip, take_money)
from services.taisan.prices import prices as asset_prices
from services.dautu.reports import daily_report, evening_line, holdings_alert, salary_part  # noqa: F401
from services.dautu.status import close_periods, status, wait_item  # noqa: F401
from services.dautu.switch import finish_switch, nav_on, open_switches, switch_calc, switch_preview, switch_prompts  # noqa: F401

# {"ma", "id", "ten", "bat_dau": "YYYY-MM", "goc": giá trị quỹ có sẵn lúc bắt đầu, "gop": {"YYYY-MM": số góp từ tháng đó},
#  "tang": 0.01, "nap": {"YYYY-MM": đã góp vào hệ thống trong tháng}, "ky": {"YYYY-MM": {"chot", "bo", "muc", "gt"}},
#  "lenh": [{"id", "ky", "tien", "dat", "phien", "trang_thai": "cho"|"khop", "nav", "ccq"}], "tat": bool, "top_luc"}


def config():
    return fund_repo.load()


def save(cfg):
    fund_repo.save(cfg)


def active(cfg=None):
    return is_active(config() if cfg is None else cfg)


@common.needs_store
def view(day=None, fresh=False):
    cfg = config()
    if not cfg.get("ma"):
        return pview.NOT_ENABLED
    s = status(cfg, fresh=fresh)
    final, sess = is_deadline(cfg)
    return pview.view_text(cfg, s, final, sess, fund_info(cfg), ct.today(), lambda: session(s["side"])["phien"])


def reminder(now, second=False):
    """Tin nhắc ngày hạn đặt lệnh (8:30, nhắc lại 13:00 nếu chưa bấm)."""
    cfg = config()
    s = status(cfg, now, fresh=True)
    if second and (not (s["buy"] or s["side_buy"]) or s["skip"] or s["ordered"]):
        return None
    sess = session(cfg, now)
    return pview.reminder_view(cfg, s, sess, second, lambda: session(s["side"], now)["phien"],
                               lambda: session(s["side"])["phien"])


def history_text():
    return pview.history_view(config())


def chart_reply():
    cfg = config()
    rows = [(ym, k) for ym, k in sorted(cfg.get("ky", {}).items()) if k.get("chot") and "gt" in k]
    s = status(cfg)
    rows.append((s["ym"], {"muc": s["plan"], "gt": s["value"]}))
    try:
        return {"photos": [quickchart.chart_png(pview.chart_config(cfg, rows), 900, 450)], "caption": pview.chart_caption(cfg, s)}
    except Exception as e:
        print(f"[lỗi] vẽ biểu đồ đầu tư: {e!r}", file=sys.stderr)
        return "⚠️ Chưa vẽ được biểu đồ (dịch vụ vẽ không trả lời), thử lại sau"


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
    data = assets_repo.load()
    hold = next((it for it in data["items"] if it["loai"] == "quy" and it["ma"] == code), None)
    base = 0
    if hold:  # đã có ccq từ trước: tính vào điểm xuất phát của kế hoạch
        price = asset_prices("quy", [code])[0].get(code)
        base = round(hold["sl"] * price) if price else round(hold["sl"] * (hold.get("gia_von") or 0))
    cfg = {"ma": code, "id": fund[0], "ten": fund[1], "bat_dau": ym, "goc": base, "gop": {ym: gop},
           "tang": DEFAULT_TANG, "nap": {}, "ky": {}, "lenh": []}
    save(cfg)
    wait_item(data, cfg)
    assets_repo.save(data)
    lines = [f"✅ Đã bật đầu tư {code} ({html.escape(fund[1].title())}): góp {money(gop)}/tháng từ tháng {ym_text(ym)}."]
    if base:
        lines.append(f"Đã tính {units_text(hold['sl'])} ccq đang có ({money(base)}) vào điểm xuất phát.")
    lines.append("Đã mua trong tháng này (trước khi bật) thì ghi lại: /dautu dadat 1tr 9/11 (số tiền, ngày đặt lệnh; "
                 "bot tự tính phiên khớp).")
    if not salary_repo.load():
        lines.append("Đặt ngày lương để bot nhắc để tiền vào quỹ chờ: /luong 5 số_tiền_lương")
    text, rows = view()
    return "\n".join(lines) + "\n\n" + text, rows


@common.needs_store
def dautu(args):
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
            g = number(rest.replace("%", "")) / 100
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
        notes = []
        left = add_money(cfg, found[0], current_period(cfg), notes=notes)
        save(cfg)
        return "\n".join([f"✅ Đã thêm {money(found[0])} vào quỹ chờ {cfg['ma']}: {money(left)}"] + notes)
    if word == "rut":
        if not found:
            return USAGE
        notes = []
        taken, left = take_money(cfg, found[0], notes=notes)
        return "\n".join([f"Đã rút {money(taken)} khỏi quỹ chờ, còn {money(left)}"] + notes)
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
        return restructure(cfg, rest, found, market.now_vn())
    if word in ("doi", "hoandoi"):
        try:
            units = number(rest.split()[0]) if rest.split() else 0
        except ValueError:
            units = 0
        if units <= 0:
            return "Gõ số ccq đã hoán đổi, ví dụ: /dautu doi 125,5 (thêm ngày đặt nếu là lệnh cũ: /dautu doi 125,5 9/11)"
        now = market.now_vn()
        spec = order_spec(cfg, " ".join(rest.split()[1:]), now, sd)
        if isinstance(spec, str):
            return spec
        day, trading, ym = spec
        return record_switch(units, trading, now, ym, day)
    if word in ("quycho", "sodu"):
        if not found:
            return USAGE
        data = assets_repo.load()
        wait_item(data, cfg)["tien"] = found[0]
        assets_repo.save(data)
        return f"✅ Số dư quỹ chờ {cfg['ma']}: {money(found[0])}"
    if word in ("dadat", "mua", "datlenh"):
        if not found:
            return USAGE
        now = market.now_vn()
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
            f"thì vào {code}; tháng cần mua nhiều hơn tiền góp thì hoán đổi từ {code} (miễn phí, ~1 tuần). {code} vừa là phần "
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
        return common.clip(note), ("edit", lambda: view())
    if kind == "nap" and value.isdigit():
        cfg = config()
        notes = []
        left = add_money(cfg, int(value), current_period(cfg), notes=notes)
        save(cfg)
        toast = f"Đã để {money(int(value))} vào quỹ chờ ({money(left)})" + "".join(
            f" · {x[2:].replace('<b>', '').replace('</b>', '')}" for x in notes)
        if common.title_starts(message, "📋"):  # nút trên tin chia lương: vẽ lại tin đó
            return toast, ("edit", lambda: kehoach.plan(now.date()))
        rows = common.without_buttons(message, "dt:nap")
        return toast, ("buttons", lambda: rows)
    if kind == "chua" and value.isdigit():  # hoán đổi chưa xong: 2 ngày sau hỏi lại
        cfg = config()
        o = next((x for x in cfg.get("lenh", []) if x["id"] == int(value)), None)
        if o:
            o["hoi_lai"] = (now.date() + timedelta(days=2)).isoformat()
            save(cfg)
        return "2 ngày nữa mình hỏi lại", ("edit", lambda: "⏳ Hoán đổi chưa xong: 2 ngày nữa mình hỏi lại.")
    if kind == "bd":
        return "Đang vẽ biểu đồ…", ("send", chart_reply)
    if kind == "ls":
        return None, ("edit", history_text)
    return None, None


def match_job(now):
    """Sau 17h: lệnh đã có NAV thì tính ccq. Trả các tin báo [(câu báo, nút)]; lệnh mua có nút sửa số ccq."""
    if (now.hour, now.minute) < (17, 0) or not active():
        return []
    return [(note, ([[fix_button(code)]] if code else []) + [[("📈 Đầu tư", "dt:xem"), ("🧾 Lệnh", "dt:ls")]])
            for code, note in match_details(now)]
