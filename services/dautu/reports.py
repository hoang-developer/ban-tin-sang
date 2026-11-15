"""Việc đầu tư quỹ phục vụ chỗ khác: phần góp trong gợi ý chia lương, dòng NAV bản tin tối, báo danh mục,
tin tối về lãi/lỗ. Câu báo còn nằm trong module này (tách sang presentation khi các bot được chia)."""
import sys

from domain.common.format import vn_num
from domain.dautu.calendar import ym_of
from domain.dautu.plan import WATCH, holding, is_active, side, total_of
from domain.dautu.text import gain_text, money, pct
from repositories.dautu import fund as fund_repo
from repositories.taisan import assets as assets_repo
from services.dautu.market import fund_info, nav_history


def salary_part(day):
    """Phần đầu tư trong gợi ý chia lương: (số nên để tháng này, đã để, ghi chú) hoặc None nếu chưa bật."""
    cfg = fund_repo.load()
    if not is_active(cfg):
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
    cfg = fund_repo.load()
    if not is_active(cfg):
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
    fund_repo.save(cfg)
    flagged = [h for h in info.get("top", []) if h["ma"] in WATCH]
    if not flagged:
        return None
    return (f"⚠️ <b>{cfg['ma']}</b> vừa cập nhật danh mục ({when}): top 10 có "
            + ", ".join(f"{h['ma']} {vn_num(h['tyle'] or 0, 1)}%" for h in flagged) + ". Xem: /dautu")


def daily_report(now):
    """Tin tối (từ 20h, ngày có NAV mới), ngắn gọn: mỗi quỹ đang giữ một dòng (giá trị theo NAV, lãi/lỗ so với tiền
    gốc), một dòng tổng. None nếu tắt, chưa có gì, hoặc hôm nay không có NAV mới (cuối tuần, ngày lễ)."""
    cfg = fund_repo.load()
    if not is_active(cfg) or cfg.get("baocao_toi") is False:
        return None
    data = assets_repo.load()
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
