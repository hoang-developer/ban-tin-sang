"""Tiết kiệm từ khi dùng bot chi tiêu (/tietkiem): chi lặt vặt mỗi ngày so với mốc trước khi dùng bot, chuỗi ngày ghi
chép, nhắc 21h, mốc thành tích.

- Mốc: chi lặt vặt (mỗi khoản dưới 1 triệu, không tính thu nhập, trả nợ) trung bình mỗi ngày trước khi dùng bot.
  Mặc định 323.700đ/ngày, tính từ sao kê thẻ tín dụng và tài khoản thanh toán 11/09–20/10/2026 (đã bỏ trả thẻ, chuyển
  giữa tài khoản của mình, trả nợ, khoản mua hộ; trừ tiền bạn bè trả lại). Đổi: /tietkiem moc 300k.
- Ngày có ghi: có ít nhất một khoản chi, hoặc bấm "Hôm nay không tiêu". Chỉ ngày có ghi mới được tính: bớt được = mốc −
  chi lặt vặt của ngày đó. Ngày không ghi gì thì bỏ qua (không ghi không phải là tiết kiệm). Hôm nay chưa hết ngày nên
  chưa cộng vào số đã bớt.
- Chuỗi ngày ghi chép: ghi bù ngày hôm qua ("hôm qua ăn tối 250k" hoặc nút "Hôm qua không tiêu") thì chuỗi vẫn giữ.
  Nghiên cứu (Silverman & Barasch 2023) cho thấy chuỗi bị đứt làm giảm động lực, cho sửa lại thì đỡ; nên bot không
  nhấn vào chuyện đứt chuỗi, chỉ hiện chuỗi hiện tại và kỷ lục.
- Đã để dành thật: tiền nạp quỹ dự phòng, góp đầu tư (/dautu), trả nợ từ ngày bắt đầu. "Chi ít hơn mốc" chỉ thành tiền
  để dành khi chuyển đi, nên /tietkiem có nút chuyển phần đã bớt vào quỹ chờ đầu tư hoặc quỹ dự phòng.
"""
import sys
from datetime import date, timedelta

import kho
import phantich as pt
import sochitieu as ct

KEY = "chitieu:tietkiem"  # {"moc", "bat_dau", "khong_tieu": [ngày ISO], "nhac": bool, "da_chuyen": đồng}
DEFAULT_BASE = 323_700
DEFAULT_START = "2026-11-04"
SMALL = 1_000_000  # khoản lặt vặt: dưới 1 triệu (khoản lớn, thất thường không tính, giống cách tính mốc)
STREAK_MARKS = (7, 30, 100, 365)
SAVED_MARKS = (1_000_000, 5_000_000, 10_000_000, 20_000_000, 50_000_000, 100_000_000)
USAGE = ("💚 /tietkiem: chi lặt vặt so với trước khi dùng bot, chuỗi ngày ghi chép, đã để dành thật\n"
         "/tietkiem khongtieu: hôm nay không tiêu gì (giữ chuỗi; ghi bù hôm qua: /tietkiem khongtieu hôm qua)\n"
         "/tietkiem moc 300k: đổi mốc chi lặt vặt mỗi ngày · /tietkiem batdau 04/11: ngày bắt đầu tính\n"
         "/tietkiem nhac tat (hoặc bat): nhắc 21h khi hôm đó chưa ghi gì")


def config():
    return {"moc": DEFAULT_BASE, "bat_dau": DEFAULT_START, "khong_tieu": [], "nhac": True, "da_chuyen": 0,
            **(kho.get(KEY, {}) or {})}


def save(cfg):
    kho.put(KEY, cfg)


def money(x):
    return pt.short(x) if abs(x) >= 1000 else "0đ"


def debt_group():
    try:
        import sono
        return sono.debt_group()[0]
    except Exception as e:
        print(f"[lỗi] nhóm trả nợ: {e!r}", file=sys.stderr)
        return None


def is_debt(e, group):
    return bool(e.get("no")) or (group is not None and e["nhom"] == group)


def days_data(cfg, today):
    """({ngày: chi lặt vặt}, {ngày có ghi}, các khoản từ ngày bắt đầu) tới hết hôm nay."""
    start = date.fromisoformat(cfg["bat_dau"])
    if today < start:
        return {}, set(), []
    entries = ct.between(start, today)
    group = debt_group()
    small, logged = {}, set()
    for e in entries:
        if e["nhom"] == ct.INCOME:
            continue
        d = date.fromisoformat(e["ngay"])
        logged.add(d)
        if e["tien"] < SMALL and not is_debt(e, group):
            small[d] = small.get(d, 0) + e["tien"]
    logged |= {date.fromisoformat(x) for x in cfg["khong_tieu"] if cfg["bat_dau"] <= x <= today.isoformat()}
    return small, logged, entries


def streaks(logged, today):
    """(chuỗi hiện tại, kỷ lục). Hôm nay chưa ghi thì chuỗi tính tới hôm qua (vẫn còn, chưa đứt)."""
    d = today if today in logged else today - timedelta(days=1)
    current = 0
    while d in logged:
        current += 1
        d -= timedelta(days=1)
    best = run = 0
    prev = None
    for d in sorted(logged):
        run = run + 1 if prev and (d - prev).days == 1 else 1
        best = max(best, run)
        prev = d
    return current, best


def real_saved(cfg, entries):
    """{"duphong", "dautu", "tra_no"}: tiền đã để dành thật từ tháng bắt đầu."""
    ym = cfg["bat_dau"][:7]
    out = {"duphong": 0, "dautu": 0, "tra_no": 0}
    try:
        import duphong
        out["duphong"] = sum(v for k, v in duphong.config().get("nap", {}).items() if k >= ym)
    except Exception as e:
        print(f"[lỗi] quỹ dự phòng trong /tietkiem: {e!r}", file=sys.stderr)
    try:
        import dautu
        out["dautu"] = sum(v for k, v in dautu.config().get("nap", {}).items() if k >= ym)
    except Exception as e:
        print(f"[lỗi] đầu tư trong /tietkiem: {e!r}", file=sys.stderr)
    group = debt_group()
    out["tra_no"] = sum(e["tien"] for e in entries if e["nhom"] != ct.INCOME and is_debt(e, group))
    return out


def summary(today, cfg=None):
    cfg = cfg or config()
    base = cfg["moc"]
    small, logged, entries = days_data(cfg, today)
    past = sorted(d for d in logged if d < today)  # hôm nay chưa hết ngày: chưa cộng
    saved = sum(base - small.get(d, 0) for d in past)
    month = [d for d in past if d.month == today.month and d.year == today.year]
    start = date.fromisoformat(cfg["bat_dau"])
    elapsed = max(0, (today - start).days)  # số ngày đã qua (không tính hôm nay)
    current, best = streaks(logged, today)
    spent_past = sum(small.get(d, 0) for d in past)
    weeks = []
    for i in range(4):  # 4 tuần gần nhất (thứ Hai–Chủ nhật), chỉ ngày đã qua và có ghi
        monday = today - timedelta(days=today.weekday() + 7 * i)
        days = [d for d in past if monday <= d < monday + timedelta(days=7)]
        if days:
            weeks.append((monday, sum(small.get(d, 0) for d in days) / len(days), len(days)))
    return {"base": base, "start": start, "saved": saved, "days": len(past), "elapsed": elapsed,
            "month_saved": sum(base - small.get(d, 0) for d in month), "month_days": len(month),
            "avg": spent_past / len(past) if past else None, "today": small.get(today, 0),
            "today_logged": today in logged, "yesterday_logged": today - timedelta(days=1) in logged,
            "streak": current, "best": best, "real": real_saved(cfg, entries), "weeks": weeks,
            "movable": max(0, saved - cfg.get("da_chuyen", 0)) // 100_000 * 100_000, "cfg": cfg}


# ---- Câu trả lời -----------------------------------------------------------------------

def saved_text(x):
    return f"đã bớt ~{money(x)}" if x >= 0 else f"đang chi hơn mốc {money(-x)}"


def after_record(entries, day):
    """Dòng thêm dưới tin "Đã ghi": chuỗi, hôm nay so với mốc, đã bớt; kèm chúc mừng khi chạm mốc (mỗi mốc một lần)."""
    if not any(e["nhom"] != ct.INCOME for e in entries):
        return []
    s = summary(day)
    if day < s["start"]:
        return []
    line = (f"🔥 {s['streak']} ngày · hôm nay {money(s['today'])}/{money(s['base'])}"
            + (f" · từ {s['start']:%d/%m} {saved_text(s['saved'])}" if s["days"] else ""))
    return [line] + milestones(s)


def milestones(s):
    out = []
    for n in STREAK_MARKS:
        if s["streak"] >= n and kho.put_new(f"{KEY}:moc:chuoi:{n}", True, 5 * 365 * 86400):
            out.append(f"🎉 Ghi chép {n} ngày liên tiếp! Kỷ lục: {s['best']} ngày")
    for m in SAVED_MARKS:
        if s["saved"] >= m and kho.put_new(f"{KEY}:moc:bot:{m}", True, 5 * 365 * 86400):
            out.append(f"🎉 Từ {s['start']:%d/%m} đã chi lặt vặt ít hơn trước {money(m)}! Chuyển vào quỹ để thành "
                       "tiền để dành thật: /tietkiem")
    return out


def home_line(day):
    """Dòng màn hình tổng quan (/menu)."""
    s = summary(day)
    if day < s["start"]:
        return None
    real = sum(s["real"].values())
    return (f"💚 Từ {s['start']:%d/%m}: {saved_text(s['saved'])} so với trước"
            + (f" · để dành thật {money(real)}" if real else "") + f" · 🔥 {s['streak']} ngày")


def view(day):
    if not kho.ready():
        return ct.NEED_STORE
    s = summary(day)
    base, start = s["base"], s["start"]
    lines = [f"💚 <b>Tiết kiệm từ khi dùng bot</b> (từ {start:%d/%m/%Y})",
             f"Mốc chi lặt vặt trước đây: <b>{money(base)}/ngày</b> (khoản dưới 1tr, từ sao kê trước khi dùng bot)"]
    if s["days"]:
        diff = (s["avg"] - base) / base * 100 if base else 0
        lines.append(f"📉 <b>{saved_text(s['saved']).capitalize()}</b> qua {s['days']} ngày có ghi · TB "
                     f"{money(s['avg'])}/ngày ({diff:+.0f}% so với mốc)")
        if s["month_days"] and s["month_days"] != s["days"]:
            lines.append(f"   Tháng {day.month}: {saved_text(s['month_saved'])} ({s['month_days']} ngày)")
    else:
        lines.append("Chưa có ngày nào trọn vẹn để tính. Ghi chi tiêu hằng ngày, hết ngày bot cộng số đã bớt")
    lines.append(f"Hôm nay: {money(s['today'])}/{money(base)}" + ("" if s["today_logged"] else " (chưa ghi khoản nào)"))
    missing = s["elapsed"] - s["days"]
    lines.append(f"🔥 Chuỗi {s['streak']} ngày · kỷ lục {s['best']} · ghi {s['days']}/{s['elapsed']} ngày"
                 + (f" ({missing} ngày không ghi chưa được tính)" if missing > 0 else ""))
    if s["weeks"]:
        lines.append("Theo tuần: " + " · ".join(f"{m:%d/%m} {money(avg)}/ngày" for m, avg, _ in s["weeks"]))
    r = s["real"]
    real = sum(r.values())
    parts = [f"{label} {money(r[k])}" for k, label in (("duphong", "quỹ dự phòng"), ("dautu", "góp đầu tư"),
                                                       ("tra_no", "trả nợ")) if r[k]]
    lines.append(f"✅ <b>Đã để dành thật: {money(real)}</b>" + (f" ({' · '.join(parts)})" if parts else ""))
    if s["movable"]:
        lines.append(f"💡 Còn {money(s['movable'])} chi ít hơn mốc chưa chuyển đi: chuyển vào quỹ thì mới thành tiền "
                     "để dành thật, không thì dễ tiêu mất")
    lines.append("<i>Mốc lấy từ sao kê ngân hàng nên không có tiền mặt; sổ ghi có cả tiền mặt, nên số đã bớt có thể thấp "
                 "hơn thực tế một chút</i>")
    return "\n".join(lines), buttons(s, day)


def buttons(s, day):
    rows = []
    quick = []
    if not s["today_logged"]:
        quick.append(("🙅 Hôm nay không tiêu", f"tk:khong:{day.isoformat()}"))
    yesterday = day - timedelta(days=1)
    if not s["yesterday_logged"] and yesterday >= s["start"]:
        quick.append(("↩️ Hôm qua không tiêu", f"tk:khong:{yesterday.isoformat()}"))
    if quick:
        rows.append(quick)
    if s["movable"]:
        move = []
        try:
            import dautu
            if dautu.active():
                move.append((f"📈 {money(s['movable'])} → quỹ chờ {dautu.config()['ma']}", f"tk:chuyen:dt:{s['movable']}"))
        except Exception as e:
            print(f"[lỗi] nút chuyển đầu tư: {e!r}", file=sys.stderr)
        move.append((f"🛟 {money(s['movable'])} → quỹ dự phòng", f"tk:chuyen:dp:{s['movable']}"))
        rows.append(move)
    rows.append([("🔄 Cập nhật", "tk:xem"), ct.BACK])
    return rows


def mark_no_spend(day_iso, today):
    cfg = config()
    if not cfg["bat_dau"] <= day_iso <= today.isoformat() or (today - date.fromisoformat(day_iso)).days > 1:
        return "Chỉ đánh dấu được hôm nay hoặc hôm qua"
    when = "hôm nay" if day_iso == today.isoformat() else "hôm qua"
    if any(e["ngay"] == day_iso and e["nhom"] != ct.INCOME for e in ct.load(day_iso[:7])):
        return f"{when.capitalize()} đã có khoản chi, ngày đó đã được tính rồi"
    if day_iso not in cfg["khong_tieu"]:
        cfg["khong_tieu"] = sorted(cfg["khong_tieu"] + [day_iso])[-1000:]
        save(cfg)
    s = summary(today)
    return "\n".join([f"✅ Đã ghi {when} không tiêu gì · 🔥 {s['streak']} ngày"] + milestones(s))


def reminder(day):
    """21h: hôm nay chưa ghi khoản chi nào (và chưa bấm không tiêu) thì nhắc một lần, kèm chuỗi và số đã bớt."""
    cfg = config()
    if not cfg.get("nhac", True):
        return None
    s = summary(day, cfg)
    if day < s["start"] or s["today_logged"]:
        return None
    goal = (f"giữ chuỗi 🔥 {s['streak']} ngày" if s["streak"] else "bắt đầu chuỗi ngày ghi chép mới") + (
        f" · tháng này {saved_text(s['month_saved'])}" if s["month_days"] else "")
    text = (f"📝 Hôm nay chưa ghi khoản chi nào. Ghi nốt để {goal}.\n"
            "Nhắn kiểu: cà phê 35k · hoặc bấm nút nếu hôm nay không tiêu gì")
    return text, [[("🙅 Hôm nay không tiêu", f"tk:khong:{day.isoformat()}"), ("💚 Tiết kiệm", "tk:xem")]]


def period_line(kind, day):
    """Dòng thêm vào tổng kết tuần/tháng: số đã bớt trong kỳ và cộng dồn."""
    s = summary(day)
    if not s["days"]:
        return None
    if kind == "tuan":
        monday = day - timedelta(days=day.weekday())
        cfg = s["cfg"]
        small, logged, _ = days_data(cfg, day)
        days = [d for d in logged if monday <= d <= day]
        part = sum(s["base"] - small.get(d, 0) for d in days)
        head = f"Tuần này {saved_text(part)} so với trước ({len(days)} ngày có ghi)"
    else:
        head = None
    return "💚 " + " · ".join(x for x in (head, f"từ {s['start']:%d/%m} {saved_text(s['saved'])}",
                                          f"🔥 {s['streak']} ngày") if x)


# ---- Lệnh, nút -------------------------------------------------------------------------

def tietkiem(args):
    if not kho.ready():
        return ct.NEED_STORE
    day = ct.today()
    word = ct.plain(args[0]) if args else ""
    rest = " ".join(args[1:])
    if not word:
        return view(day)
    if word in ("huongdan", "help", "?"):
        return USAGE
    if word in ("khongtieu", "khong"):
        target = day - timedelta(days=1) if "qua" in ct.plain(rest) else day
        return mark_no_spend(target.isoformat(), day)
    cfg = config()
    if word == "moc":
        found = ct.parse_amount(rest)
        if not found or not 10_000 <= found[0] <= 10_000_000:
            return "Mốc chi lặt vặt mỗi ngày, ví dụ: /tietkiem moc 300k"
        cfg["moc"] = found[0]
        save(cfg)
        return view(day)
    if word == "batdau":
        when, _ = ct.parse_date(rest, day)
        if when > day:
            return "Ngày bắt đầu phải là hôm nay hoặc trước đó, ví dụ: /tietkiem batdau 04/11"
        cfg["bat_dau"] = when.isoformat()
        save(cfg)
        return view(day)
    if word == "nhac":
        cfg["nhac"] = ct.plain(rest) not in ("tat", "off", "khong")
        save(cfg)
        return "✅ Bật nhắc 21h khi hôm đó chưa ghi gì" if cfg["nhac"] else "Đã tắt nhắc 21h"
    return USAGE


def on_button(arg, message, now):
    """Nút "tk:...": (thông báo nhỏ, việc tiếp theo)."""
    kind, _, value = arg.partition(":")
    day = now.date()
    if kind == "xem":
        return None, ("edit", lambda: view(day))
    if kind == "khong":
        note = mark_no_spend(value, day)
        if (message.get("text") or "").startswith("💚"):
            return note[:190], ("edit", lambda: view(day))
        rows = [[b for b in row if not b[1].startswith("tk:khong")] for row in ct.keyboard_rows(message)]
        return note[:190], ("buttons", lambda: [r for r in rows if r])
    if kind == "chuyen":
        where, _, amount = value.partition(":")
        if not amount.isdigit():
            return None, None
        amount = int(amount)
        if where == "dt":
            import dautu
            cfg_dt = dautu.config()
            left = dautu.add_money(cfg_dt, amount, dautu.current_period(cfg_dt))
            dautu.save(cfg_dt)
            note = f"Đã chuyển {money(amount)} vào quỹ chờ {cfg_dt['ma']} ({money(left)})"
        else:
            import duphong
            note = duphong.change(amount, day).split("\n")[0][2:]
        cfg = config()
        cfg["da_chuyen"] = cfg.get("da_chuyen", 0) + amount
        save(cfg)
        return note[:190], ("edit", lambda: view(day))
    return None, None
