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

from infrastructure import kho
from repositories.dautu import fund as fund_repo
from repositories.luong import salary as salary_repo
from domain.dautu.calendar import cutoff_day, months, weekdays_after, ym_add, ym_of, ym_text  # noqa: F401
from domain.dautu.plan import (DEFAULT_FUND, DEFAULT_GOP, DEFAULT_TANG, MIN_ORDER, STEP, SWITCH_DAYS,  # noqa: F401
                                contributed_of, extra_of, goes_main, gop_of, holding, pending_main, side, target, them_of,
                                total_of, wait_name)
from domain.dautu.calendar import read_date  # noqa: F401
from domain.dautu.text import money, units_text  # noqa: F401
from services.dautu.status import close_periods, status, wait_item  # noqa: F401
from services.dautu.orders import (add_money, fix_units, match_details, match_orders, order_spec,  # noqa: F401
                                   record_order, record_plan, record_switch, skip, take_money)
from services.dautu.switch import (finish_switch, nav_on, open_switches, switch_calc, switch_preview,  # noqa: F401
                                   switch_prompts)
from services.dautu.market import (current_period, find_fund, fund_info, is_deadline, nav_history,  # noqa: F401
                                   next_trading, now_vn, session)
import phantich as pt
import sochitieu as ct
import taisan as ts
from bantin import vn_num

# {"ma", "id", "ten", "bat_dau": "YYYY-MM", "goc": giá trị quỹ có sẵn lúc bắt đầu, "gop": {"YYYY-MM": số góp từ tháng đó},
#  "tang": 0.01, "nap": {"YYYY-MM": đã góp vào hệ thống trong tháng}, "ky": {"YYYY-MM": {"chot", "bo", "muc", "gt"}},
#  "lenh": [{"id", "ky", "tien", "dat", "phien", "trang_thai": "cho"|"khop", "nav", "ccq"}], "tat": bool, "top_luc"}
WATCH = ("VIC", "VHM", "VRE", "VPL")  # nhóm Vingroup: báo nếu vào top 10 của quỹ
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
    return fund_repo.load()


def save(cfg):
    fund_repo.save(cfg)


def active(cfg=None):
    cfg = config() if cfg is None else cfg
    return bool(cfg.get("ma")) and not cfg.get("tat")




# ---- Dữ liệu quỹ trên Fmarket ----------------------------------------------------------

# ---- Dữ liệu quỹ trên Fmarket, phiên giao dịch: xem services/dautu/market.py


# ---- Quỹ chờ, kế hoạch, tình trạng kỳ: xem domain/dautu/plan.py và services/dautu/status.py


# ---- Câu trả lời -----------------------------------------------------------------------

def pct(x):
    return "0,0%" if abs(x) < 0.0005 else f"{x * 100:+.1f}%".replace(".", ",")


def arrow(x):
    """+1,2% -> '🔺1,2%', −0,8% -> '🔻0,8%'."""
    return "0,0%" if abs(x) < 0.0005 else f"{'🔺' if x > 0 else '🔻'}{abs(x) * 100:.1f}%".replace(".", ",")


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
    line = f"📊 NAV {vn_num(s['nav'], 2)}đ ({s['nav_day']:%d/%m})"
    if s["month_change"] is not None:
        line += f" · tháng {arrow(s['month_change'])}"
    if s["drawdown"] is not None:
        line += f" · đỉnh 52 tuần {pct(s['drawdown']).replace('-', '−')}"
    return line


def decision_lines(cfg, s, final=True):
    """Các dòng "kế hoạch / đang có / nên mua" của kỳ đang mở. final=False (chưa tới hạn): chỉ là con số dự kiến."""
    lines = [f"🎯 Kế hoạch {ym_text(s['ym'])} <b>{money(s['plan'])}</b> · có {money(s['value'])}"
             + (f" (⏳ {money(s['pending'])} chờ khớp)" if s["pending"] else "")]
    if s["skip"]:
        lines.append("⏸ Tháng này tạm dừng" + (f" · quỹ chờ {money(s['cash'])}, vẫn mua được tới {money(s['buy'])}"
                                              if s["buy"] else ""))
        return lines
    if not final:
        lines.append(f"📅 NAV giữ nguyên thì cuối tháng mua ~<b>{money(s['buy'])}</b>" if s["buy"] else
                     "📅 NAV giữ nguyên thì cuối tháng không mua (quỹ cao hơn kế hoạch)")
    elif s["side"]:
        lines += order_lines(cfg, s)
    elif s["buy"]:
        lines.append(f"👉 <b>Mua {ct.vnd(s['buy'])}</b>" + (
            f" (hết tiền; thiếu {money(s['need'] - s['buy'])}, tháng sau tự bù)" if s["short"] else ""))
    elif s["need"] > 0:
        lines.append(f"👉 Không mua: cần {money(s['need'])} nhưng quỹ chờ có {money(s['cash'])}")
    else:
        lines.append(f"👉 <b>Không mua</b>: quỹ cao hơn kế hoạch {money(-s['need'])} · để "
                     f"{money(gop_of(cfg, s['ym']))} vào quỹ chờ")
    if s["side"]:
        lines.append(f"💰 Chưa đặt lệnh {money(s['money_now'])} · {s['side']['ma']} {money(s['side_value'] or 0)}")
    else:
        lines.append(f"💰 Quỹ chờ {money(s['cash'])}" + (f" + chưa để {money(s['unpaid'])}" if s["unpaid"] else ""))
    if s["below_milestone"]:
        f = s["fund"]
        lines.append(f"⚠️ Quỹ dự phòng mới {vn_num(f.covered, 1)}/1 tháng chi (thiếu "
                     f"{money(f.monthly - f.balance)}): ưu tiên quỹ dự phòng trước")
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
        steps.append(f"Hoán đổi <b>{units_text(s['switch_units'])} ccq {sd} → {cfg['ma']}</b> (≈ {money(s['switch'])}; "
                     f"bán {sd} rồi mua {cfg['ma']}, ~{SWITCH_DAYS} ngày)")
    if not steps:
        return ["👉 Tháng này không cần đặt lệnh"]
    head = (f"👉 {cfg['ma']} cao hơn kế hoạch {money(-s['need'])}: chưa mua thêm, tiền góp vào {sd}"
            if s["need"] <= 0 else f"👉 Mua thêm {cfg['ma']} {money(s['buy'])}" + (
                f" (hết tiền; thiếu {money(s['need'] - s['buy'])}, tháng sau tự bù)" if s["short"] else ""))
    return [head] + [f"   {i}. {t}" for i, t in enumerate(steps, 1)]


def summary_line(s):
    if s["side"]:  # cả danh mục: quỹ chính + quỹ chờ + tiền chưa đặt lệnh
        total = s["value"] + (s["side_value"] or 0) + s["cash"]
        gain = total - s["contributed"]
        share = s["value"] / total * 100 if total else 0
        return (f"💼 {money(total)}: cổ phiếu {money(s['value'])} ({share:.0f}%) · "
                f"{s['side']['ma']} {money(s['side_value'] or 0)} ({100 - share:.0f}%)"
                + (f" · góp {money(s['contributed'])} → {gain_text(gain, s['contributed'])}" if s["contributed"] else ""))
    gain = s["value"] - s["invested"] if s["invested"] else 0
    line = f"💼 Đã mua {money(s['invested'])}"
    if s["invested"] and s["nav"]:
        line += f" → {gain_text(gain, s['invested'])}"
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
             f"⏰ Hạn đặt lệnh: {deadline_text(cfg, s['ym'], sess)}",
             summary_line(s)]
    info = fund_info(cfg) or {}
    if info.get("top"):
        top = ", ".join(h["ma"] for h in info["top"])
        flagged = [h["ma"] for h in info["top"] if h["ma"] in WATCH]
        lines.append(f"🔟 Top 10 ({info.get('top_luc') or '—'}): {top}"
                     + (f"\n⚠️ Có nhóm Vingroup: {', '.join(flagged)}" if flagged else ""))
    left = {k: v for k, v in cfg.get("ke_hoach_them", {}).items() if k >= s["ym"]}
    if left:
        lines.append(f"🔁 Đang rải vào {cfg['ma']}: còn {money(sum(left.values()))}, tới {ym_text(max(left))}"
                     " (bỏ: /dautu taicocau xoa)")
    return "\n".join(lines), buttons(cfg, s, sess, final)


def deadline_text(cfg, ym, sess):
    if ym_of(sess["dong"].date()) == ym and ym_of(sess["phien"]) != ym:
        return f"14:40 hôm nay {sess['dong']:%d/%m}" if sess["dong"].date() == ct.today() else f"14:40 {sess['dong']:%d/%m}"
    last = last_weekday(ym)
    return f"14:40 ~{last:%d/%m}"


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
    when = f"⏰ Fmarket trước <b>14:40 {sess['dong']:%d/%m}</b> → {cfg['ma']} khớp phiên {sess['phien']:%d/%m}"
    if s["side"]:
        when += f", {s['side']['ma']} phiên {session(s['side'], now)['phien']:%d/%m}"
    lines = [title, when, nav_line(cfg, s), *decision_lines(cfg, s), summary_line(s)]
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
            sold = f"bán {o['ban'][8:]}/{o['ban'][5:7]}" if o.get("ban") else ""
            state = {"khop": f"{units_text(o.get('ccq') or 0)} ccq {cfg['ma']} ({money(o['tien'])}) · {sold}, mua "
                             f"{o['phien'][8:]}/{o['phien'][5:7]}",
                     "chuyen": f"{cfg['ma']} · ✅ {sold} ≈ {money(o['tien'])}, 🔁 chờ mua",
                     "cho": f"{cfg['ma']} · ⏳ chờ bán"}[o["trang_thai"]]
            lines.append(f"• đặt {o['dat'][8:]}/{o['dat'][5:7]}: hoán đổi {units_text(o['ccq_ra'])} ccq {code} → {state}")
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


# ---- Ghi lệnh, góp tiền, khớp lệnh, hoán đổi: xem services/dautu/orders.py và switch.py


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
    if not salary_repo.load():
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
        return note[:190], ("edit", lambda: view())
    if kind == "nap" and value.isdigit():
        cfg = config()
        notes = []
        left = add_money(cfg, int(value), current_period(cfg), notes=notes)
        save(cfg)
        toast = f"Đã để {money(int(value))} vào quỹ chờ ({money(left)})" + "".join(
            f" · {x[2:].replace('<b>', '').replace('</b>', '')}" for x in notes)
        if (message.get("text") or "").startswith("📋"):  # nút trên tin chia lương: vẽ lại tin đó
            from interface.kehoach import plan as kehoach
            return toast, ("edit", lambda: kehoach.plan(now.date()))
        rows = [[b for b in row if not b[1].startswith("dt:nap")] for row in ct.keyboard_rows(message)]
        return toast, ("buttons", lambda: [r for r in rows if r])
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
        from services.duphong import reserve as reserve_service
        f = reserve_service.status(day)
        if f.monthly and f.covered < 1:
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
    pending = sum(o["tien"] for o in cfg.get("lenh", []) if o["trang_thai"] in ("cho", "chuyen"))
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

