"""Đọc ảnh hóa đơn, màn hình chuyển khoản gửi vào bot chi tiêu: AI đọc số tiền, ngày, nội dung rồi bot ghi
như một tin nhắn thường (vẫn có nút ✏️ đổi nhóm, ❌ xóa).

Thử ngày 04/11/2026 (Gemini 3.5 Flash-Lite): đúng số tiền 7/7 ảnh, gồm hóa đơn Highlands chụp thật trả bằng
Got It 20.000 + MoMo 9.000 (đọc đúng tổng 29.000), hóa đơn chụp nghiêng mờ, màn hình chuyển/nhận tiền;
ảnh không phải hóa đơn thì AI trả "khac". Ảnh được gửi cho nhà cung cấp AI (Google ở gói miễn phí dùng để
cải thiện sản phẩm), bot không lưu ảnh.
"""
import html
import sys
import urllib.request
from datetime import date, timedelta

import kho
import sochitieu as ct
import tg

MAX_BYTES = 8_000_000  # ảnh Telegram đã nén thường dưới 500KB; file gửi nguyên bản có thể lớn hơn
SEEN = "chitieu:anh:"  # ảnh đã ghi (theo mã ảnh của Telegram), tránh ghi trùng khi gửi lại


def image_of(message):
    """(mã file, mã ảnh duy nhất, kiểu ảnh) của ảnh trong tin nhắn; None nếu tin không có ảnh."""
    if message.get("photo"):
        best = message["photo"][-1]  # Telegram xếp các cỡ từ nhỏ tới lớn
        return best["file_id"], best.get("file_unique_id", best["file_id"]), "image/jpeg"
    doc = message.get("document") or {}
    if (doc.get("mime_type") or "").startswith("image/"):
        return doc["file_id"], doc.get("file_unique_id", doc["file_id"]), doc["mime_type"]
    return None


def download(file_id, tok):
    path = tg.call("getFile", tok, file_id=file_id)["file_path"]
    with urllib.request.urlopen(f"https://api.telegram.org/file/bot{tok}/{path}", timeout=20) as r:
        data = r.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("ảnh quá lớn")
    return data


def prompt():
    groups = ", ".join(f"{code} ({ct.bare(label)})" for code, (label, _, _) in ct.groups().items()
                       if code != ct.INCOME)
    return ("Ảnh này có thể là hóa đơn, biên lai, hoặc màn hình chuyển khoản/biến động số dư ngân hàng của người "
            "Việt. Trích ra một khoản để ghi sổ chi tiêu. Trả lời đúng một dòng JSON, không giải thích:\n"
            '{"loai": "hoa_don" | "chuyen_khoan" | "khac", '
            '"so_tien": TỔNG GIÁ TRỊ hóa đơn hoặc giao dịch, số nguyên đồng: lấy dòng TỔNG CỘNG / Tong tien / TỔNG '
            'THANH TOÁN, kể cả phần trả bằng voucher hay điểm; không lấy tiền khách đưa, tiền thừa, số dư, cũng '
            'không lấy riêng từng dòng phương thức thanh toán (MoMo, thẻ, Got It...), '
            '"diem": phần của tổng đó trả bằng voucher, phiếu quà tặng, điểm thưởng (Got It, Urbox, đổi điểm...), '
            '0 nếu không có, '
            '"chieu": "chi" hoặc "thu" (nhận tiền vào tài khoản là thu), "ngay": "dd/mm/yyyy" hoặc null, '
            '"noi_dung": ghi chú ngắn kiểu "món chính + tên quán" (vd "phin sữa đá highlands", "đi chợ siêu thị an '
            'phú", "tiền điện tháng 10"), viết thường, PHẢI có dấu tiếng Việt kể cả khi ảnh in không dấu (vd '
            '"hoan tien mua ve may bay" phải viết "hoàn tiền mua vé máy bay"), '
            '"noi_ban": tên cửa hàng hoặc người nhận/gửi, '
            '"nhom": một mã trong ' + groups + "}. "
            'Không phải hóa đơn hay giao dịch thì {"loai": "khac"}.')


def read_receipt(data, mime):
    """Nhờ AI đọc ảnh: dict đã kiểm tra (loai, tien, chieu, ngay, noi_dung, noi_ban, diem, nhom, model)."""
    # Lúc Gemini đông có khi mất 10–20 giây/ảnh: chờ mỗi model tới 30 giây, tổng không quá 48 giây
    text, model = ct.ai_chat("Bạn đọc hóa đơn và màn hình giao dịch ngân hàng của người Việt, trả lời bằng JSON.",
                             prompt(), max_tokens=3000, image=(data, mime), timeout=30, budget=48)
    raw = ct.first_json(text)
    if not isinstance(raw, dict):
        raise RuntimeError(f"AI trả lời không đúng dạng: {text[:100]!r}")

    def money(key):
        value = raw.get(key) or 0
        if isinstance(value, (int, float)):
            return max(0, round(value))
        digits = "".join(ch for ch in str(value) if ch.isdigit())  # "29.000đ", "29,000" -> 29000
        return int(digits) if digits else 0
    print(f"[ảnh] đọc bằng {model}", file=sys.stderr)
    return {"loai": raw.get("loai"), "tien": money("so_tien"), "chieu": "thu" if raw.get("chieu") == "thu" else "chi",
            "ngay": raw.get("ngay"), "noi_dung": ct.norm(str(raw.get("noi_dung") or ""))[:60],
            "noi_ban": str(raw.get("noi_ban") or "")[:40], "diem": money("diem"), "nhom": str(raw.get("nhom") or ""),
            "model": model}


def receipt_date(text, today):
    """'04/11/2026' -> date; không đọc được, ở tương lai hay quá 1 năm thì lấy hôm nay."""
    try:
        d, m, y = (int(x) for x in str(text).replace("-", "/").split("/")[:3])
        when = date(y, m, d)
    except (ValueError, TypeError):
        return today
    return when if today - timedelta(days=366) <= when <= today else today


def photo(message, tok, now):
    """Ghi khoản từ ảnh trong tin nhắn; trả câu trả lời (chữ, hoặc (chữ, nút))."""
    if not kho.ready():
        return ct.NEED_STORE
    ct.reset()
    file_id, unique, mime = image_of(message)
    if not ct.ai_key():
        return "📷 Đọc ảnh cần AI: thêm biến GEMINI_API_KEY trên Vercel rồi Redeploy (xem README). Giờ nhắn tay kiểu: cà phê 35k"
    seen = SEEN + unique
    if not kho.put_new(seen, True, 60 * 86400):
        return "📷 Ảnh này đã ghi rồi. Xem lại: /lichsu"
    try:
        info = read_receipt(download(file_id, tok), mime)
    except Exception as e:
        print(f"[lỗi] đọc ảnh: {e!r}", file=sys.stderr)
        kho.delete(seen)
        return "⚠️ Chưa đọc được ảnh (AI bận hoặc ảnh quá mờ). Gửi lại sau, hoặc nhắn tay kiểu: cà phê 35k"
    if info["loai"] == "khac" or not info["tien"]:
        kho.delete(seen)
        return "🤔 Không thấy hóa đơn hay giao dịch nào trong ảnh. Chụp rõ dòng tổng tiền rồi gửi lại nhé"
    day = now.date()
    caption = (message.get("caption") or "").strip()
    chosen, missing, rest = ct.read_tag(caption) if caption else (None, None, "")
    note = ct.norm(rest) or info["noi_dung"] or ct.norm(info["noi_ban"])
    learned = kho.get(ct.K_LEARN, {})
    e = {"ngay": receipt_date(info["ngay"], day).isoformat(), "tien": info["tien"], "ghichu": note, "anh": True}
    active = ct.groups()
    if info["chieu"] == "thu":
        e["nhom"] = ct.INCOME
    elif chosen:
        e["nhom"] = chosen
        ct.learn(note, chosen)
    else:
        e["nhom"] = ct.classify(note, learned)  # nhóm bạn đã dạy, từ khóa: đáng tin hơn AI đoán
        if e["nhom"] == ct.OTHER and info["nhom"] in active and info["nhom"] not in (ct.OTHER, ct.INCOME):
            e["nhom"], e["ai"] = info["nhom"], True
    e["id"] = kho.command("INCR", ct.K_COUNTER)
    e["gio"] = now.strftime("%H:%M")
    ct.save(e)
    seen_from = f" · {html.escape(info['noi_ban'])}" if info["noi_ban"] else ""
    extra = [f"📷 Đọc từ ảnh{seen_from}, kiểm tra lại số tiền và ngày nhé"]
    if missing:
        extra.append(f"⚠️ Chưa có nhóm «{html.escape(missing)}», tạo bằng: /nhom them {html.escape(missing)}")
    try:
        extra += ct.phantich().after_record([e], day)
    except Exception as err:
        print(f"[lỗi] phân tích sau khi ghi ảnh: {err!r}", file=sys.stderr)
    text, rows = ct.entries_message([e], day, extra=extra)
    if info["diem"] and info["chieu"] == "chi" and info["diem"] < info["tien"] * 1.01:
        text += (f"\n🎁 Có {ct.vnd(info['diem'])} trả bằng voucher/điểm thưởng. Điểm đổi từ chi tiêu (thẻ tín dụng…) "
                 "nên ghi là khoản thu:")
        rows = rows + [[(f"➕ Ghi {ct.vnd(info['diem'])} vào Thu nhập", f"anh:diem:{info['diem']}")]]
    return text, rows


def on_button(arg, message, now):
    """Nút "anh:diem:<số tiền>": ghi phần trả bằng điểm/voucher thành khoản thu, bỏ nút đó."""
    kind, _, amount = arg.partition(":")
    if kind != "diem" or not amount.isdigit():
        return None, None
    e = {"id": kho.command("INCR", ct.K_COUNTER), "ngay": now.date().isoformat(), "gio": now.strftime("%H:%M"),
         "tien": int(amount), "ghichu": "đổi điểm, voucher", "nhom": ct.INCOME}
    ct.save(e)
    rows = [row for row in ct.keyboard_rows(message) if not any(d.startswith("anh:") for _, d in row)]
    return f"Đã ghi {ct.vnd(int(amount))} vào Thu nhập", ("buttons", lambda: rows)
