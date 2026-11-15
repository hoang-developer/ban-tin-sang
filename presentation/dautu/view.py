"""Màn hình /dautu: chữ và nút dựng từ số liệu đã tính (không đọc kho, không gọi mạng)."""
from datetime import date, timedelta

import sochitieu as ct  # module cũ ở gốc: nút ⬅️ Hôm nay
from domain.common.format import vn_num, vnd
from domain.dautu.calendar import ym_of, ym_text
from domain.dautu.plan import SWITCH_DAYS, WATCH, gop_of, side, them_of
from domain.dautu.text import arrow, gain_text, money, pct, units_text  # noqa: F401 (pct, arrow, gain_text dùng chung)


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
        lines.append(f"👉 <b>Mua {vnd(s['buy'])}</b>" + (
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
        steps.append(f"Mua {cfg['ma']} <b>{vnd(s['direct'])}</b> (tiền góp)")
    if s["side_buy"]:
        steps.append(f"Mua {sd} <b>{vnd(s['side_buy'])}</b>")
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


def deadline_text(cfg, ym, sess, today):
    if ym_of(sess["dong"].date()) == ym and ym_of(sess["phien"]) != ym:
        return f"14:40 hôm nay {sess['dong']:%d/%m}" if sess["dong"].date() == today else f"14:40 {sess['dong']:%d/%m}"
    last = last_weekday(ym)
    return f"14:40 ~{last:%d/%m}"


def last_weekday(ym):
    d = date(int(ym[:4]), int(ym[5:]), 28) + timedelta(days=4)
    d = d.replace(day=1) - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def buttons(cfg, s, sess, final, side_phien):
    """side_phien: hàm không tham số trả phiên khớp của quỹ chờ (chỉ gọi khi cần nút đặt hai lệnh)."""
    rows = []
    phien = sess["phien"].strftime("%Y%m%d")
    if s["side"] and final and not s["skip"] and (s["direct"] or s["side_buy"] or s["switch"]):
        sp = side_phien().strftime("%Y%m%d")
        rows.append([("✅ Đã đặt các lệnh trên", f"dt:dat2:{int(s['direct'])}:{int(s['side_buy'])}:"
                      f"{round(s['switch_units'] * 100)}:{s['ym']}:{phien}:{sp}")])
    elif s["buy"] and not s["skip"] and final:
        rows.append([(f"✅ Đã đặt lệnh {money(s['buy'])}", f"dt:dat:{int(s['buy'])}:{phien}:{s['ym']}")])
    if not s["skip"] and not s["ordered"]:
        rows.append([("⏸ Tạm dừng tháng này", f"dt:bo:{s['ym']}")])
    rows.append([("🔄 Cập nhật", "dt:xem"), ("📊 Biểu đồ", "dt:bd"), ("🧾 Lệnh", "dt:ls")])
    rows.append([("🎯 Kế hoạch", "kh:lt"), ct.BACK])
    return rows


NOT_ENABLED = ("📈 <b>Đầu tư quỹ mở hằng tháng</b>\nChưa bật. Bật bằng: /dautu batdau 4tr VMEEF (góp 4 triệu mỗi "
               "tháng vào quỹ VMEEF). Mỗi cuối tháng bot tính nên mua bao nhiêu theo Value Averaging: quỹ giảm thì "
               "mua nhiều hơn, quỹ tăng nhanh thì mua ít hoặc để tiền chờ.\n\n" + USAGE)


def view_text(cfg, s, final, sess, info, today, side_phien):
    """Màn hình /dautu của quỹ đang bật: (chữ, nút)."""
    extra = them_of(cfg, s["ym"])
    lines = [f"📈 <b>{cfg['ma']}: góp {money(gop_of(cfg, s['ym']) or cfg['gop'][max(cfg['gop'])])}/tháng</b>"
             + (f" + {money(extra)} {s['side']['ma']}" if extra else "")
             + (" (đang tắt: /dautu bat)" if cfg.get("tat") else ""),
             nav_line(cfg, s), *decision_lines(cfg, s, final),
             f"⏰ Hạn đặt lệnh: {deadline_text(cfg, s['ym'], sess, today)}",
             summary_line(s)]
    info = info or {}
    if info.get("top"):
        top = ", ".join(h["ma"] for h in info["top"])
        flagged = [h["ma"] for h in info["top"] if h["ma"] in WATCH]
        lines.append(f"🔟 Top 10 ({info.get('top_luc') or '—'}): {top}"
                     + (f"\n⚠️ Có nhóm Vingroup: {', '.join(flagged)}" if flagged else ""))
    left = {k: v for k, v in cfg.get("ke_hoach_them", {}).items() if k >= s["ym"]}
    if left:
        lines.append(f"🔁 Đang rải vào {cfg['ma']}: còn {money(sum(left.values()))}, tới {ym_text(max(left))}"
                     " (bỏ: /dautu taicocau xoa)")
    return "\n".join(lines), buttons(cfg, s, sess, final, side_phien)


def reminder_view(cfg, s, sess, second, side_when, side_phien):
    """Tin nhắc ngày hạn đặt lệnh (8:30, nhắc lại 13:00 nếu chưa bấm). side_when: hàm trả phiên khớp của quỹ chờ."""
    title = (f"📈 <b>{cfg['ma']}: hôm nay là hạn đặt lệnh tháng {int(s['ym'][5:])}</b>" if not second else
             f"⏰ <b>{cfg['ma']}: còn tới 14:40 để đặt lệnh tháng {int(s['ym'][5:])}</b>")
    when = f"⏰ Fmarket trước <b>14:40 {sess['dong']:%d/%m}</b> → {cfg['ma']} khớp phiên {sess['phien']:%d/%m}"
    if s["side"]:
        when += f", {s['side']['ma']} phiên {side_when():%d/%m}"
    lines = [title, when, nav_line(cfg, s), *decision_lines(cfg, s), summary_line(s)]
    return "\n".join(lines), buttons(cfg, s, sess, True, side_phien)


def history_view(cfg):
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


def fix_button(code):
    return (f"✏️ Fmarket báo số ccq {code} khác", f"y:them:sua_ccq:{code}")


def chart_config(cfg, rows):
    """Cấu hình biểu đồ đường: kế hoạch và giá trị thực tế theo kỳ. rows: [(ym, {"muc", "gt"})]."""
    return {"type": "line", "data": {"labels": [ym_text(ym) for ym, _ in rows], "datasets": [
        {"label": "Kế hoạch (triệu)", "data": [round(k["muc"] / 1e6, 2) for _, k in rows], "borderColor": "#868e96",
         "borderDash": [6, 4], "fill": False},
        {"label": f"Giá trị {cfg['ma']} (triệu)", "data": [round(k["gt"] / 1e6, 2) for _, k in rows],
         "borderColor": "#1971c2", "backgroundColor": "#1971c233", "fill": True}]},
        "options": {"plugins": {"datalabels": {"display": False}, "title": {
            "display": True, "font": {"size": 20}, "text": f"{cfg['ma']}: kế hoạch và thực tế (triệu đồng)"}}}}


def chart_caption(cfg, s):
    return f"📊 <b>{cfg['ma']}</b>: kế hoạch {money(s['plan'])} · đang có {money(s['value'])}"
