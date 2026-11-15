"""Hoán đổi quỹ chờ → quỹ chính: người dùng báo ngày bán, ngày mua; tính theo NAV đúng ngày và cập nhật số ccq."""
from datetime import date, timedelta

from domain.common.format import vn_num
from domain.dautu.plan import SWITCH_DAYS, holding, side
from domain.dautu.text import money, units_text
from repositories.dautu import fund as fund_repo
from repositories.taisan import assets as assets_repo
from services.dautu.market import nav_history


def open_switches(cfg=None):
    cfg = cfg or fund_repo.load()
    return [o for o in cfg.get("lenh", []) if o.get("loai") == "doi" and o["trang_thai"] in ("cho", "chuyen")]


def switch_prompts(day):
    """Hoán đổi đặt từ {SWITCH_DAYS} ngày trước mà chưa báo xong: [(câu hỏi, nút)] cho tin sáng (hỏi tới khi xong;
    bấm "Chưa" thì 2 ngày sau hỏi lại)."""
    cfg = fund_repo.load()
    out = []
    for o in open_switches(cfg):
        if date.fromisoformat(o["dat"]) + timedelta(days=SWITCH_DAYS) > day or o.get("hoi_lai", "") > day.isoformat():
            continue
        sold = (f" · ✅ đã bán {o['ban'][8:]}/{o['ban'][5:7]} ≈ {money(o['tien'])}" if o.get("ban") else "")
        out.append((f"🔁 Hoán đổi {units_text(o['ccq_ra'])} ccq {o['quy']} → {cfg['ma']} (đặt {o['dat'][8:]}/"
                    f"{o['dat'][5:7]}) xong chưa?{sold}",
                    [[("✅ Xong, cập nhật ngày", f"y:them:doi_xong:{o['id']}"), ("⏳ Chưa", f"dt:chua:{o['id']}")]]))
    return out


def nav_on(fund, day):
    """(ngày khớp, NAV) của phiên đầu tiên từ ngày `day` (nghỉ lễ thì phiên sau, tối đa 10 ngày); None nếu chưa có."""
    for fresh in (False, True):
        found = [(d, v) for d, v in nav_history(fund, fresh=fresh) if day <= d <= day + timedelta(days=10)]
        if found:
            return found[0]
    return None


def switch_calc(order_id, sell_day, buy_day, units_in=None):
    """Tính hoán đổi theo NAV đúng ngày: dict (lệnh, NAV bán, tiền, NAV mua, ccq vào) hoặc câu báo lỗi."""
    cfg = fund_repo.load()
    o = next((x for x in cfg.get("lenh", []) if x["id"] == order_id and x.get("loai") == "doi"), None)
    sd = side(cfg)
    if not o or not sd:
        return "Không thấy lệnh hoán đổi này"
    sell = nav_on(sd, sell_day)
    buy = nav_on(cfg, buy_day)
    if not sell:
        return f"Chưa có NAV {sd['ma']} ngày {sell_day:%d/%m}: sau 17h ngày khớp mới có, thử lại sau nhé"
    if not buy:
        return f"Chưa có NAV {cfg['ma']} ngày {buy_day:%d/%m}: sau 17h ngày khớp mới có, thử lại sau nhé"
    value = o["ccq_ra"] * sell[1]
    units = round(units_in, 2) if units_in else round(value / buy[1], 2)
    return {"o": o, "cfg": cfg, "sell": sell, "buy": buy, "value": value, "units": units, "given": bool(units_in)}


def switch_preview(order_id, sell_day, buy_day, units_in=None):
    c = switch_calc(order_id, sell_day, buy_day, units_in)
    if isinstance(c, str):
        return f"⚠️ {c}"
    o, cfg = c["o"], c["cfg"]
    return (f"🔁 Hoán đổi {units_text(o['ccq_ra'])} ccq {o['quy']} → {cfg['ma']}\n"
            f"• Bán {o['quy']} {c['sell'][0]:%d/%m}: NAV {vn_num(c['sell'][1], 2)}đ = <b>{money(c['value'])}</b>\n"
            f"• Mua {cfg['ma']} {c['buy'][0]:%d/%m}: NAV {vn_num(c['buy'][1], 2)}đ → <b>{units_text(c['units'])} ccq</b>"
            + (" (theo Fmarket)" if c["given"] else ""))


def finish_switch(order_id, sell_day, buy_day, units_in=None):
    """Hoán đổi đã xong: cập nhật số ccq hai quỹ theo NAV đúng ngày bán, ngày mua. Trả câu báo."""
    c = switch_calc(order_id, sell_day, buy_day, units_in)
    if isinstance(c, str):
        return f"⚠️ {c}"
    o, cfg = c["o"], c["cfg"]
    cfg = fund_repo.load()  # đọc lại để lưu đúng bản mới nhất
    o = next(x for x in cfg["lenh"] if x["id"] == order_id)
    data = assets_repo.load()
    src = holding(data, cfg, o["quy"])
    if o["trang_thai"] == "cho" and src:  # chưa trừ lúc bán (chưa có NAV phiên bán): trừ bây giờ
        src["sl"] = round(max(0, src["sl"] - o["ccq_ra"]), 2)
    if o["trang_thai"] == "khop":  # báo lại lần nữa: bỏ số ccq đã cộng lần trước
        old = holding(data, cfg)
        if old:
            old["sl"] = round(max(0, old["sl"] - (o.get("ccq") or 0)), 2)
    hold = holding(data, cfg)
    if hold is None:
        hold = {"id": assets_repo.new_id(data), "loai": "quy", "ma": cfg["ma"], "sl": 0, "gia_von": None}
        data["items"].append(hold)
    cost = hold["sl"] * (hold.get("gia_von") or 0) + c["value"]
    hold["sl"] = round(hold["sl"] + c["units"], 2)
    hold["gia_von"] = cost / hold["sl"] if hold["sl"] else None
    o.update({"trang_thai": "khop", "ban": c["sell"][0].isoformat(), "nav_ra": c["sell"][1],
              "phien": c["buy"][0].isoformat(), "nav": c["value"] / c["units"] if c["units"] else c["buy"][1],
              "ccq": c["units"], "tien": round(c["value"])})
    o.pop("hoi_lai", None)
    assets_repo.save(data)
    fund_repo.save(cfg)
    return (f"✅ Hoán đổi xong: bán {units_text(o['ccq_ra'])} ccq {o['quy']} {c['sell'][0]:%d/%m} = {money(c['value'])} → "
            f"<b>{units_text(c['units'])} ccq {cfg['ma']}</b> {c['buy'][0]:%d/%m}. Đang có {units_text(hold['sl'])} ccq "
            f"{cfg['ma']}")
