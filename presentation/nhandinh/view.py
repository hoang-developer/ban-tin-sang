"""Chữ của nhận định trong phiên: ngành, khuyến nghị, tin, dòng đầu và bản tóm tắt không cần AI."""
import html
from datetime import datetime, timezone

from domain.common.format import vn_num
from domain.nhandinh.rules import (RATING, billions, market_line, pct, pt_short, rec_line, signed_billions,
                                   whole_pct)

BUTTONS = [[("🔥 Ngành", "nd:nganh"), ("🎯 Khuyến nghị", "nd:kn"), ("📰 Tin", "nd:tin")],
           [("🔄 Cập nhật nhận định", "nd:moi")]]
SHORT_REF = "<i>Nguồn VNDirect</i>"


def sector_lines(data, top=8, bottom=3):
    rows = data["sectors"]
    if not rows:
        return ["Chưa lấy được số liệu ngành"]

    def line(g):
        members = ", ".join(f"{s['ma']} {pct(s['pct'])}" for s in g["ma"])
        return (f"{'🟢' if g['pct'] > 0 else '🔴' if g['pct'] < 0 else '⚪'} <b>{html.escape(g['ten'])}</b> {pct(g['pct'])}"
                f" · {billions(g['gtgd'])} · NN {signed_billions(g['nn'])} · ↑{g['tang']} ↓{g['giam']}\n   {members}")
    lines = [line(g) for g in rows[:top]]
    if bottom and len(rows) > top:
        lines.append("…")
        lines += [line(g) for g in rows[max(top, len(rows) - bottom):]]
    money = sorted(rows, key=lambda g: -g["gtgd"])[:3]
    lines.append("💰 Hút tiền nhất: " + " · ".join(f"{html.escape(g['ten'])} {billions(g['gtgd'])}" for g in money))
    return lines


def news_line(item, now=None):
    now = now or datetime.now(timezone.utc)
    ago = ""
    if item["luc"]:
        minutes = int((now - item["luc"]).total_seconds() // 60)
        ago = f" · {minutes // 60} giờ trước" if minutes >= 60 else f" · {max(minutes, 1)} phút trước"
    return f"• <a href=\"{html.escape(item['link'])}\">{html.escape(item['tieu_de'])}</a> ({item['nguon']}{ago})"


def nganh_text(data, now):
    return "\n".join([f"🔥 <b>Ngành trên HOSE</b> · {now:%H:%M %d/%m}", market_line(data),
                      "<i>% theo vốn hóa · giá trị giao dịch · khối ngoại ròng · số mã tăng/giảm</i>"]
                     + sector_lines(data))


def recommendation_detail(code, items, price):
    """Khuyến nghị của các CTCK cho một mã trong 180 ngày."""
    firms = len(set(i["firm"] for i in items))
    lines = [f"🎯 <b>{code}</b>" + (f" · giá {pt_short(price)}" if price else "")
             + f" · {firms} CTCK khuyến nghị trong 180 ngày"]
    for i in items[:8]:
        target = (i.get("targetPrice") or 0) * 1000
        upside = f" ({whole_pct((target / price - 1) * 100)})" if target and price else ""
        lines.append(f"{i['reportDate'][8:10]}/{i['reportDate'][5:7]} {html.escape(i['firm'])} "
                     f"{RATING.get((i.get('type') or '').upper(), i.get('type'))}"
                     + (f" {pt_short(target)}{upside}" if target else ""))
    return "\n".join(lines + [SHORT_REF])


def recommendation_list(rows):
    return "\n".join([f"🎯 <b>Khuyến nghị CTCK 30 ngày</b> · {len(rows)} mã",
                      "<i>(số CTCK khuyến nghị · giá mục tiêu TB · còn tăng so với giá hiện tại)</i>"]
                     + [rec_line(r) for r in rows[:12]] + ["Chi tiết một mã: /khuyennghi FPT", SHORT_REF])


def tin_text(news, now):
    return "\n".join([f"📰 <b>Tin tài chính mới</b> · {now:%H:%M %d/%m}"] + [news_line(i) for i in news[:15]])


def headline(now, data):
    """Một dòng đầu: giờ, VN-Index, thanh khoản, khối ngoại ròng HOSE."""
    vni = data["index"].get("VN-Index")
    parts = [f"🧠 <b>Nhận định {now:%H:%M}</b>"]
    if vni:
        parts.append(f"VN-Index {vn_num(vni[0], 0)} ({pct((vni[0] / vni[1] - 1) * 100)})")
        parts.append(billions(vni[2]))
    if data["stocks"]:
        parts.append("ngoại " + signed_billions(sum(s["nn"] for s in data["stocks"])))
    return " · ".join(parts)


def short_fallback(data):
    """Không có AI: 3–4 dòng số liệu gọn."""
    today_pct = {s["ma"]: s["pct"] for s in data["stocks"]}
    hot = sorted((g for g in data["sectors"] if g["pct"] > 0), key=lambda g: -g["gtgd"])[:3]
    lines = []
    if hot:
        lines.append("🔥 " + " · ".join(f"{html.escape(g['ten'])} {pct(g['pct'])} ({billions(g['gtgd'])})" for g in hot))
    for r in data["recs"][:2]:
        move = f" {pct(today_pct[r['ma']])}" if r["ma"] in today_pct else ""
        target = f", mục tiêu {pt_short(r['muc_tieu'])}" if r["muc_tieu"] else ""
        upside = f" ({whole_pct(r['con_tang'])})" if r["con_tang"] is not None else ""
        lines.append(f"🎯 {r['ma']}{move}: {r['so']} CTCK khuyến nghị {r['loai']}{target}{upside}")
    if data["news"]:
        lines.append(news_line(data["news"][0]))
    return lines
