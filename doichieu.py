"""Đối chiếu tài sản mỗi tháng (/doichieu, nút 🔄 ở 💰 Tiền của tôi, tin sáng ngày 15).

Mỗi ngăn (tài khoản, quỹ dự phòng, quỹ chờ, sổ tiết kiệm, cổ phiếu, quỹ mở, tiền số, ngoại tệ, tài sản khác, khoản nợ)
một dòng: bot đang tính bao nhiêu. Bấm ✅ nếu khớp, ✏️ để nhắn số thật. Bot ghi đè số thật và lưu khoản lệch:
- Tài khoản chính: chốt lại số dư; lệch thì hỏi có ghi là khoản chi (hoặc thu) chưa ghi không. Khoản đó vào báo cáo
  chi tiêu nhưng không trừ số dư lần nữa (số dư đã là số thật).
- Quỹ mở còn lệnh chờ khớp hoặc hoán đổi đang chuyển: chưa cho đối chiếu (khớp xong bot tự cộng, nhập trước sẽ bị
  cộng hai lần).
- Vàng không có ở đây (ít khi đổi, mỗi lần mua có giá riêng): sửa ở 💼 Tài sản.
Ngày 15 (DAY) chọn vì lương (ngày 5), trả nợ (quanh ngày 10), lệnh quỹ cuối tháng và hoán đổi (~ngày 8) đã xong.
"""
import html
import sys

import kho
import sochitieu as ct

KEY = "chitieu:doichieu"  # {"YYYY-MM": {"muc": {id: {"ten", "bot", "that", "lech", "don_vi"}}}}
DAY = 15
UNITS = ("quy", "cp", "etf", "coin", "ngoaite")  # đối chiếu theo số lượng, không theo tiền


def ts():
    return ct.taisan()


def log(ym=None):
    data = kho.get(KEY, {}) or {}
    return data.get(ym, {"muc": {}}) if ym else data


def save_log(ym, month):
    data = kho.get(KEY, {}) or {}
    data[ym] = month
    kho.put(KEY, dict(sorted(data.items())[-12:]))


def short(x):
    return ts().short(x) if abs(x) >= 1000 else f"{round(x)}đ"


def qty(x):
    return ts().qty_text(round(x, 4))


def items(day):
    """Các ngăn cần đối chiếu: [(mục tài sản, giá trị bot đang tính, đơn vị: "đ" hoặc tên đơn vị)]."""
    data = ts().load()
    out = []
    for it in data["items"]:
        kind = it["loai"]
        if kind == "tien":
            out.append((it, ts().main_balance(it, day) if it.get("chinh") else it["tien"], "đ"))
        elif kind in ("tietkiem", "khac"):
            out.append((it, it["tien"], "đ"))
        elif kind == "no" and it.get("tien", 0) > 0:
            out.append((it, it["tien"], "đ"))
        elif kind in UNITS:
            unit = {"quy": "ccq", "cp": "cp", "etf": "ccq", "coin": it["ma"].upper(), "ngoaite": it["ma"]}[kind]
            out.append((it, it["sl"], unit))
    return out


def name(it):
    label = it.get("ten") or it.get("ma", "").upper()
    return html.escape(label) + (" (chính)" if it.get("chinh") else "") + (" 💳" if it["loai"] == "no" else "")


def amount_text(value, unit):
    return short(value) if unit == "đ" else f"{qty(value)} {unit}"


def pending_fund(it):
    """Quỹ mở còn lệnh chờ khớp hoặc hoán đổi đang chuyển (đối chiếu lúc này sẽ bị cộng hai lần)."""
    if it["loai"] != "quy":
        return False
    try:
        cfg = ct.dautu().config()
        main = cfg.get("ma")
        for o in cfg.get("lenh", []):
            if o.get("trang_thai") == "cho" and (o.get("quy") or main) == it["ma"]:
                return True
            if o.get("loai") == "doi" and o.get("trang_thai") in ("cho", "chuyen") and it["ma"] in (main, o.get("quy")):
                return True
    except Exception as e:
        print(f"[lỗi] lệnh quỹ khi đối chiếu: {e!r}", file=sys.stderr)
    return False


def screen(day):
    """Màn hình đối chiếu tháng: mỗi ngăn một dòng và một hàng nút."""
    if not kho.ready():
        return ct.NEED_STORE
    ym = day.strftime("%Y-%m")
    done = log(ym)["muc"]
    rows_data = items(day)
    if not rows_data:
        return ("🔄 Chưa có tài sản nào để đối chiếu. Nhắn kiểu «tài khoản VCB còn 30tr».",
                [[("➕ Thêm", "y:them"), ct.BACK]])
    lines = [f"🔄 <b>Đối chiếu tài sản {day.month}/{day.year}</b>",
             "<i>Mở app ngân hàng, Fmarket… so từng dòng: khớp bấm ✅, lệch bấm ✏️ rồi nhắn số thật</i>"]
    rows, left = [], 0
    for it, value, unit in rows_data:
        rid = str(it["id"])
        rec = done.get(rid)
        if rec:
            mark = "✅" if not rec["lech"] else (color(rec["lech"], rec.get("no")) + (" +" if rec["lech"] > 0 else " −")
                                                + amount_text(abs(rec["lech"]), rec["don_vi"]))
            lines.append(f"{mark} {name(it)}: {amount_text(rec['that'], unit)}")
            continue
        left += 1
        if pending_fund(it):
            lines.append(f"⏳ {name(it)}: {amount_text(value, unit)} · còn lệnh chờ khớp, đối chiếu sau")
            continue
        lines.append(f"⬜ {name(it)}: bot tính {amount_text(value, unit)}")
        rows.append([(f"✏️ {(it.get('ten') or it.get('ma', '')).upper() if it['loai'] in UNITS else it.get('ten')}"[:28],
                      f"y:them:{'doi_chieu_sl' if unit != 'đ' else 'doi_chieu'}:{rid}"), ("✅ Khớp", f"dc:ok:{rid}")])
    total = sum(r["lech"] for r in done.values() if r["don_vi"] == "đ" and not r.get("no"))
    if done:
        lines.append(f"\nΣ lệch tiền: {('🟢 +' if total >= 0 else '🔴 −') + short(abs(total)) if total else '✅ 0đ'}"
                     + (f" · còn {left} ngăn" if left else " · 🎉 xong"))
    if left > 1:
        rows.append([("✅ Khớp hết phần còn lại", "dc:het")])
    return "\n".join(lines), rows + [[("💰 Tiền của tôi", "m:tien"), ct.BACK]]


def record(day, it, bot_value, real, unit):
    ym = day.strftime("%Y-%m")
    month = log(ym)
    lech = real - bot_value if unit != "đ" or abs(real - bot_value) >= 1000 else 0
    month["muc"][str(it["id"])] = {"ten": it.get("ten") or it.get("ma"), "bot": bot_value, "that": real,
                                   "lech": round(lech, 4) if unit != "đ" else round(lech), "don_vi": unit,
                                   **({"no": True} if it["loai"] == "no" else {})}
    save_log(ym, month)
    return lech


def set_value(item_id, real, now):
    """Ghi số thật của một ngăn: ghi đè, lưu khoản lệch. Trả (câu báo, nút)."""
    day = now.date()
    data = ts().load()
    found = next(((it, v, u) for it, v, u in items(day) if str(it["id"]) == str(item_id)), None)
    if not found:
        return "Ngăn này không còn trong tài sản", [[("🔄 Đối chiếu", "dc:xem")]]
    it, bot_value, unit = found
    if pending_fund(it):
        return f"⏳ {name(it)} còn lệnh chờ khớp: khớp xong bot tự cộng ccq, đối chiếu sau nhé", [[("🔄 Đối chiếu", "dc:xem")]]
    it = next(x for x in data["items"] if x["id"] == it["id"])
    if unit == "đ":
        real = int(round(real))
        if it.get("chinh"):
            ts().pin_balance(it, real)
        else:
            it["tien"] = real
        it["ngay"] = day.isoformat()
        if it["loai"] == "no" and real <= 0:
            it["xong"] = day.isoformat()
    else:
        if real < 0:
            return "Số lượng không âm nhé", [[("🔄 Đối chiếu", "dc:xem")]]
        it["sl"] = round(real, 4)
    ts().save(data)
    lech = record(day, it, bot_value, real, unit)
    head = f"{name(it)}: bot {amount_text(bot_value, unit)} → thật {amount_text(real, unit)}"
    if not lech:
        return f"✅ {head} · khớp", screen_rows(day)
    note = f"{color(lech, it['loai'] == 'no')} {head} · lệch {'+' if lech > 0 else '−'}{amount_text(abs(lech), unit)}"
    rows = screen_rows(day)
    if it.get("chinh"):  # tài khoản chính lệch: thường là khoản chi (thu) quên ghi
        label = f"🧾 Ghi {short(-lech)} là chi chưa ghi" if lech < 0 else f"💰 Ghi {short(lech)} là thu chưa ghi"
        rows = [[(label, f"dc:ghi:{it['id']}"), ("Chỉ sửa số dư", "dc:xem")]]
    return note, rows


def color(lech, debt=False):
    """🟢 có nhiều hơn bot tính (nợ thì ngược lại: nợ ít hơn mới tốt)."""
    return "🟢" if (lech > 0) != bool(debt) else "🔴"


def screen_rows(day):
    return [[("🔄 Tiếp tục đối chiếu", "dc:xem")]]


def mark_ok(item_id, day):
    found = next(((it, v, u) for it, v, u in items(day) if str(it["id"]) == str(item_id)), None)
    if not found or pending_fund(found[0]):
        return False
    it, value, unit = found
    record(day, it, value, value, unit)
    return True


def book_gap(item_id, now):
    """Khoản lệch của tài khoản chính → khoản chi (thu) chưa ghi: vào báo cáo, không trừ số dư lần nữa."""
    day = now.date()
    rec = log(day.strftime("%Y-%m"))["muc"].get(str(item_id))
    if not rec or not rec["lech"] or rec.get("ghi"):
        return "Khoản lệch này đã xử lý rồi"
    gap = rec["lech"]
    entry = {"id": kho.command("INCR", ct.K_COUNTER), "ngay": day.isoformat(), "gio": now.strftime("%H:%M"),
             "tien": abs(gap), "ghichu": f"{'chi' if gap < 0 else 'thu'} chưa ghi (đối chiếu {rec['ten']})",
             "nhom": ct.INCOME if gap > 0 else ct.OTHER, "khong_tk": True}
    ct.save(entry)
    month = log(day.strftime("%Y-%m"))
    month["muc"][str(item_id)]["ghi"] = True
    save_log(day.strftime("%Y-%m"), month)
    return f"✅ Đã ghi {short(abs(gap))} là {'khoản chi' if gap < 0 else 'khoản thu'} chưa ghi (không trừ số dư lần nữa)"


def all_ok(day):
    n = 0
    for it, value, unit in items(day):
        if str(it["id"]) not in log(day.strftime("%Y-%m"))["muc"] and not pending_fund(it):
            record(day, it, value, value, unit)
            n += 1
    return n


def remaining(day):
    done = log(day.strftime("%Y-%m"))["muc"]
    return [it for it, _, _ in items(day) if str(it["id"]) not in done]


def morning_part(day):
    """Ngày 15: một phần trong tin sáng (một lần mỗi tháng)."""
    if day.day != DAY:
        return None
    left = remaining(day)
    if not left or not kho.put_new(f"{KEY}:nhac:{day:%Y-%m}", True, 40 * 86400):
        return None
    return (f"🔄 Hôm nay đối chiếu tài sản tháng {day.month}: {len(left)} ngăn, so với app ngân hàng, Fmarket",
            [[("🔄 Bắt đầu đối chiếu", "dc:xem")]])


def todo(day):
    """Việc cần làm ở 🏠 Hôm nay: từ ngày 15 tới hết tháng, khi còn ngăn chưa đối chiếu."""
    if day.day < DAY:
        return None
    left = remaining(day)
    return (f"🔄 Đối chiếu tài sản tháng {day.month}: còn {len(left)} ngăn", ("🔄 Đối chiếu", "dc:xem")) if left else None


def doichieu(args):
    return screen(ct.today())


def on_button(arg, message, now):
    """Nút "dc:...": xem, ok:<id> (khớp), het (khớp hết), ghi:<id> (ghi khoản lệch là chi/thu chưa ghi)."""
    day = now.date()
    kind, _, value = arg.partition(":")
    if kind == "xem":
        return None, ("edit", lambda: screen(day))
    if kind == "ok":
        ok = mark_ok(value, day)
        return ("✅ Khớp" if ok else "Ngăn này chưa đối chiếu được"), ("edit", lambda: screen(day))
    if kind == "het":
        n = all_ok(day)
        return f"✅ Đã đánh dấu khớp {n} ngăn", ("edit", lambda: screen(day))
    if kind == "ghi":
        note = book_gap(value, now)
        return note[:190], ("edit", lambda: (note, screen_rows(day)))
    return None, None
