"""Việc theo giờ của bot, chạy mỗi lần có lời gọi /api/tick (cron-job.org mỗi 15 phút, GitHub dự phòng).

Mỗi việc tự xem đã tới giờ chưa; việc ngày một lần được đánh dấu trong kho để không làm lại.
"""
import html
import re
import sys
import unicodedata
from datetime import datetime, timedelta, timezone

import amlich
import canhbao
import kho
import lenh
import tg
from bantin import WEEKDAYS, gold_prices, hourly, index_history, section, stocks, tips, vn_num, weather
from chungkhoan import change, color, dong, google_news, index_rows, quotes

# Từ khóa nhận ra tin quyền lợi cổ đông (so khớp sau khi đưa về chữ thường)
DIVIDEND_WORDS = ["cổ tức", "chốt quyền", "chốt danh sách", "không hưởng quyền", "phát hành thêm",
                  "thưởng cổ phiếu", "cổ phiếu thưởng"]


def between(now, start, end):
    return start <= (now.hour, now.minute) < end


def trading_day(now):
    return now.weekday() < 5


def done_today(job, now):
    return kho.get(f"xong:{job}:{now.date()}") is not None


def mark_done(job, now):
    kho.put(f"xong:{job}:{now.date()}", True, 3 * 86400)


# ---- Các việc --------------------------------------------------------------------

def canh_bao(now, chat):
    """Các cảnh báo của canhbao.py, trạng thái lưu trong kho thay cho state.json."""
    if not between(now, (6, 0), (22, 0)):
        return None
    state = kho.get("canhbao", {})
    alerts = canhbao.run(state, now, watchlist={**canhbao.WATCHLIST, **lenh.price_alerts()})
    items = kho.get("vivang", [])
    if items:
        alerts = [a + "\n" + lenh.wallet_brief(items) if a.startswith("🪙") else a for a in alerts]
    if alerts:
        tg.send(chat, "\n\n".join(alerts))
    kho.put("canhbao", state)
    return f"{len(alerts)} cảnh báo"


def board_text(now):
    closed = (now.hour, now.minute) >= (15, 0)
    lines = [f"📌 <b>Bảng điện</b> · {WEEKDAYS[now.weekday()]} {now:%d/%m} · "
             f"{'đã đóng cửa' if closed else 'cập nhật ' + now.strftime('%H:%M')}"]
    try:
        rows = index_rows()
        for name in ("VN-Index", "VN30"):
            value, ref = rows[name][:2]
            lines.append(f"{color(value, ref)} {name} <b>{vn_num(value)}</b>  {change(value, ref, 2)}")
        lines.append(" · ".join(f"{color(rows[n][0], rows[n][1])} {n} {vn_num(rows[n][0])} "
                                f"({vn_num((rows[n][0] / rows[n][1] - 1) * 100, sign=True)}%)"
                                for n in ("HNX", "UPCoM")))
    except Exception as e:
        print(f"[lỗi] bảng điện, chỉ số: {e!r}", file=sys.stderr)
        lines.append("⚪ Chỉ số: không lấy được")
    watch = kho.get("theodoi", {})
    if watch:
        try:
            for s, q in quotes(watch).items():
                p = q["price"] or q["ref"]
                lines.append(f"⭐ {s} <b>{dong(p)}</b> {color(p, q['ref'])} "
                             f"{vn_num((p / q['ref'] - 1) * 100, sign=True)}%")
        except Exception as e:
            print(f"[lỗi] bảng điện, mã theo dõi: {e!r}", file=sys.stderr)
    try:
        buy, sell = gold_prices()["sjc"]
        lines.append(f"🪙 SJC mua {vn_num(buy, 1)} – bán {vn_num(sell, 1)}")
    except Exception as e:
        print(f"[lỗi] bảng điện, vàng: {e!r}", file=sys.stderr)
    if not closed:
        lines.append("<i>Tự cập nhật 15 phút một lần trong phiên</i>")
    return "\n".join(lines)


def bang_dien(now, chat):
    """Tin ghim đầu chat, sửa lại mỗi lượt trong phiên; mỗi ngày giao dịch một tin mới."""
    if not trading_day(now) or not between(now, (9, 0), (15, 20)):
        return None
    text = board_text(now)
    board = kho.get("bangdien", {})
    if board.get("ngay") == str(now.date()):
        try:
            tg.edit(chat, board["id"], text)
            return "đã sửa"
        except tg.TelegramError as e:
            if "not found" not in e.description:
                raise  # tin đã bị xóa thì gửi tin mới ở dưới
    msg = tg.send(chat, text)
    if board.get("id"):
        try:
            tg.call("unpinChatMessage", chat_id=chat, message_id=board["id"])
        except tg.TelegramError:
            pass  # tin cũ đã bị xóa hoặc bỏ ghim
    tg.call("pinChatMessage", chat_id=chat, message_id=msg["message_id"], disable_notification=True)
    kho.put("bangdien", {"ngay": str(now.date()), "id": msg["message_id"]})
    return "đã gửi và ghim"


def gui_doan(now, chat):
    if not trading_day(now) or not between(now, (8, 15), lenh.GUESS_DEADLINE) or done_today("gui_doan", now):
        return None
    tg.send(chat, lenh.GUESS_TEXT, lenh.GUESS_BUTTONS)
    mark_done("gui_doan", now)
    return "đã hỏi"


def cham_doan(now, chat):
    if not trading_day(now) or not between(now, (15, 0), (23, 0)) or done_today("cham_doan", now):
        return None
    guess = kho.get(f"doan:{now.date()}")
    if guess is None:
        mark_done("cham_doan", now)
        return "hôm nay không đoán"
    t, c = index_history("VNINDEX", "VNINDEX")
    if datetime.fromtimestamp(t[-1], timezone.utc).date() != now.date():
        text = "🎯 Hôm nay không có phiên giao dịch, lượt đoán không tính."
    else:
        pct = (c[-1] - c[-2]) / c[-2] * 100
        result = "xanh" if c[-1] > c[-2] else "do" if c[-1] < c[-2] else None
        s = kho.get("doan_thongke", {"dung": 0, "tong": 0, "chuoi": 0, "chuoi_max": 0, "thang": {}})
        if result is None:
            text = "🎯 VN-Index đứng giá tham chiếu, lượt đoán hòa."
        else:
            right = guess == result
            month = s["thang"].setdefault(now.strftime("%Y-%m"), [0, 0])
            month[0] += right
            month[1] += 1
            s["dung"] += right
            s["tong"] += 1
            s["chuoi"] = s["chuoi"] + 1 if right else 0
            s["chuoi_max"] = max(s["chuoi_max"], s["chuoi"])
            kho.put("doan_thongke", s)
            text = (f"🎯 {'✅ Đoán đúng!' if right else '❌ Đoán trật.'} VN-Index {vn_num(c[-1])} "
                    f"({vn_num(pct, sign=True)}%) – {lenh.GUESS_LABEL[result]}, bạn chọn "
                    f"{lenh.GUESS_LABEL[guess]}\nChuỗi đúng: {s['chuoi']} · tháng này {month[0]}/{month[1]}")
    tg.send(chat, text)
    kho.put(f"doan_kq:{now.date()}", text, 3 * 86400)
    mark_done("cham_doan", now)
    return "đã chấm"


def reminders_due(day, offsets):
    """Các ngày cần nhớ rơi vào day + offset ngày (offset trong offsets)."""
    lines = []
    for r in kho.get("nhac", []):
        d = amlich.next_date(r["ngay"], r["thang"], r["am"], day)
        n = (d - day).days
        if n in offsets:
            lines.append((n, d, r))
    return lines


def nhac_ngay(now, chat):
    if not between(now, (7, 0), (23, 0)) or done_today("nhac_ngay", now):
        return None
    lines = []
    for n, d, r in reminders_due(now.date(), (0, 3)):
        what = f"{html.escape(r['ten'])} ({lenh.when_text(r)})"
        lines.append(f"🔔 <b>Hôm nay</b>: {what}" if n == 0 else
                     f"🔔 Còn {n} ngày ({WEEKDAYS[d.weekday()]} {d:%d/%m}): {what}")
    if lines:
        tg.send(chat, "\n".join(lines))
    mark_done("nhac_ngay", now)
    return f"{len(lines)} lời nhắc"


def normalize(text):
    return unicodedata.normalize("NFC", text).lower()


def co_tuc(now, chat):
    """Dò tin cổ tức, chốt quyền của các mã đang theo dõi."""
    if not between(now, (7, 30), (23, 0)) or done_today("co_tuc", now):
        return None
    seen = kho.get("cotuc_daxem", [])
    found = []
    for symbol in kho.get("theodoi", {}):
        query = f'"{symbol}" (cổ tức OR "chốt quyền" OR "chốt danh sách" OR "không hưởng quyền") when:3d'
        for title, link in google_news(query):
            if (link in seen or not re.search(rf"\b{symbol}\b", title)
                    or not any(w in normalize(title) for w in DIVIDEND_WORDS)):
                continue
            seen.append(link)
            found.append(f'• <b>{symbol}</b>: <a href="{html.escape(link)}">{html.escape(title, quote=False)}</a>')
    if found:
        tg.send(chat, "💰 <b>Tin quyền lợi cổ đông</b>\n" + "\n".join(found[:8]))
    kho.put("cotuc_daxem", seen[-300:])
    mark_done("co_tuc", now)
    return f"{len(found)} tin"


def evening_message(now):
    tomorrow = now.date() + timedelta(days=1)
    parts = [f"🌙 <b>Bản tin tối – {WEEKDAYS[now.weekday()]}, {now:%d/%m}</b>"]

    def weather_tomorrow():
        lines = weather(day=1)
        try:
            lines += tips(hourly(), tomorrow, now.replace(tzinfo=None))
        except Exception as e:
            print(f"[lỗi] gợi ý ngày mai: {e!r}", file=sys.stderr)
        moon = {1: " · mùng 1", 15: " · rằm"}.get(amlich.to_lunar(tomorrow)[0], "")
        return lines + [f"🌙 Mai là {amlich.label(tomorrow)} âm lịch{moon}"]

    parts.append(section(f"🌤️ Ngày mai – {WEEKDAYS[tomorrow.weekday()]} {tomorrow:%d/%m}", weather_tomorrow))

    if trading_day(now):
        def market():
            lines = stocks()
            watch = kho.get("theodoi", {})
            if watch:
                for s, q in quotes(watch).items():
                    p = q["price"] or q["ref"]
                    lines.append(f"⭐ {s} {dong(p)} {color(p, q['ref'])} {vn_num((p / q['ref'] - 1) * 100, sign=True)}%")
            return lines
        parts.append(section("📈 Chứng khoán hôm nay", market))

    def gold_today():
        prices = gold_prices()
        sell = prices["sjc"][1]
        hist = kho.get("vang_lichsu", {})
        earlier = [d for d in hist if d < str(now.date())]
        line = f"Miếng SJC bán {vn_num(sell, 1)} triệu/lượng"
        if earlier:
            last = max(earlier)
            line += f" ({vn_num(sell - hist[last], 1, sign=True)} so với {last[8:]}/{last[5:7]})"
        hist[str(now.date())] = sell  # ghi lại mỗi tối, /neu vang dùng
        kho.put("vang_lichsu", dict(sorted(hist.items())[-800:]))
        lines = [line]
        items = kho.get("vivang", [])
        if items:
            lines.append(lenh.wallet_brief(items))
        return lines

    parts.append(section("🪙 Vàng", gold_today))

    remind = reminders_due(tomorrow, (0,))
    if remind:
        parts.append("<b>🔔 Ngày mai</b>\n" + "\n".join(
            f"• {html.escape(r['ten'])} ({lenh.when_text(r)})" for _, _, r in remind))
    result = kho.get(f"doan_kq:{now.date()}")
    if result:
        parts.append(result)
    return "\n\n".join(parts)


def ban_tin_toi(now, chat):
    if not between(now, (21, 0), (23, 0)) or done_today("ban_tin_toi", now):
        return None
    tg.send(chat, evening_message(now))
    mark_done("ban_tin_toi", now)
    return "đã gửi"


JOBS = [canh_bao, bang_dien, gui_doan, cham_doan, nhac_ngay, co_tuc, ban_tin_toi]


def run(now):
    """Chạy mọi việc đã tới giờ; trả về ghi chú từng việc để xem trong log."""
    chat = tg.owner_chat()
    notes = []
    for job in JOBS:
        try:
            notes.append(f"{job.__name__}: {job(now, chat) or 'chưa tới giờ'}")
        except Exception as e:
            print(f"[lỗi] {job.__name__}: {e!r}", file=sys.stderr)
            notes.append(f"{job.__name__}: lỗi {e!r}")
    kho.put("tick_cuoi", now.strftime("%H:%M %d/%m"))
    return notes
