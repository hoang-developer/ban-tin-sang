"""Đọc ảnh hóa đơn, màn hình chuyển khoản, lịch sử giao dịch ngân hàng gửi vào bot chi tiêu: AI đọc số tiền,
ngày, nội dung, loại giao dịch rồi bot ghi như một tin nhắn thường (vẫn có nút ✏️ đổi nhóm, ❌ xóa).
Ảnh nhiều giao dịch: bot hiện danh sách, tự bỏ qua trả thẻ tín dụng và chuyển giữa tài khoản của chính bạn,
người dùng bấm chọn rồi Ghi; giao dịch đã ghi (cùng ngày, số tiền, chiều) không ghi lại.

Thử ngày 04/11/2026 (Gemini 3.5 Flash-Lite): đúng số tiền 7/7 ảnh, gồm hóa đơn Highlands chụp thật trả bằng
Got It 20.000 + MoMo 9.000 (đọc đúng tổng 29.000), hóa đơn chụp nghiêng mờ, màn hình chuyển/nhận tiền;
ảnh không phải hóa đơn thì AI trả "khac". Ảnh được gửi cho nhà cung cấp AI (Google ở gói miễn phí dùng để
cải thiện sản phẩm), bot không lưu ảnh.
"""
import html
import re
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


KINDS = ("chi_tieu", "thu_nhap", "tra_no", "tra_the", "chuyen_noi_bo")
SKIP_WHY = {"tra_the": "trả thẻ tín dụng: các khoản quẹt thẻ ghi riêng rồi, ghi nữa là trùng",
            "chuyen_noi_bo": "chuyển giữa các tài khoản của bạn, không phải thu chi",
            "da_ghi": "đã ghi trước đó"}
PENDING = "chitieu:anhcho:"  # danh sách giao dịch đọc từ ảnh, chờ người dùng chọn rồi bấm Ghi
DONE_TX = "chitieu:gd:"  # giao dịch đã ghi (ngày|số tiền|chiều): ảnh lịch sử chụp lại không ghi trùng
OWNERS = "chitieu:chutk"  # tên chủ tài khoản bot đã nhận ra (người đứng tên ở các dòng trả thẻ tín dụng)


def person(text):
    """Tên người (từ 2 chữ, toàn chữ cái) đã bỏ dấu, viết thường; '' nếu không giống tên người."""
    words = ct.plain(re.sub(r"[^\w\s]", " ", text or "")).split()
    return " ".join(words) if len(words) >= 2 and all(w.isalpha() for w in words) else ""


def owner_names(txs):
    """Tên chủ tài khoản: các tên đã nhớ, cộng tên người ở các dòng trả thẻ tín dụng trong ảnh này (ai trả nợ
    thẻ tín dụng thì thường chính là chủ thẻ). Nhớ lại cho các ảnh sau."""
    names = list(kho.get(OWNERS, []) or [])
    for tx in txs:
        who = person(tx["noi_ban"])
        if tx["kieu"] == "tra_the" and who and who not in names:
            names.append(who)
    names = names[-5:]
    if names != (kho.get(OWNERS, []) or []):
        kho.put(OWNERS, names)
    return names


def own_transfer(tx, names):
    """Tiền chuyển qua lại với chính chủ tài khoản: người gửi/nhận là chủ tài khoản, hoặc nội dung chỉ là
    "<tên chủ tài khoản> chuyển tiền". Có chữ lương, thưởng thì không phải."""
    note = " ".join(ct.plain(tx["noi_dung"]).split())
    if not names or re.search(r"(?<!\w)(luong|thuong)(?!\w)", note):
        return False
    return person(tx["noi_ban"]) in names or any(note in (n, f"{n} chuyen tien", f"{n} chuyen khoan") for n in names)


def prompt(owners=()):
    owner = f"Chủ tài khoản tên: {', '.join(owners).upper()}. " if owners else ""
    groups = ", ".join(f"{code} ({ct.bare(label)})" for code, (label, _, _) in ct.groups().items()
                       if code != ct.INCOME)
    return ("Ảnh này có thể là: hóa đơn/biên lai (1 khoản); màn hình MỘT giao dịch chuyển khoản; hoặc DANH SÁCH "
            "nhiều giao dịch (lịch sử tài khoản, biến động số dư ngân hàng) của người Việt. Trả lời đúng một dòng "
            "JSON, không giải thích:\n"
            '{"loai": "hoa_don" | "chuyen_khoan" | "danh_sach" | "khac", "giao_dich": [{'
            '"so_tien": số nguyên đồng, '
            '"chieu": "chi" hoặc "thu" (tiền vào tài khoản, dấu + là thu), '
            '"ngay": "dd/mm/yyyy" hoặc null, '
            '"noi_dung": ghi chú ngắn tiếng Việt, viết thường, PHẢI có dấu kể cả khi ảnh in không dấu (vd "phin sữa '
            'đá highlands", "lương tháng 10/2026", "trả nợ vay", "trả thẻ tín dụng", "hoàn tiền mua vé máy bay"), '
            '"noi_ban": tên cửa hàng hoặc người nhận/gửi, '
            '"diem": phần trả bằng voucher, phiếu quà tặng, điểm thưởng (Got It, Urbox...), 0 nếu không có, '
            '"kieu": "chi_tieu" (mua bán, dịch vụ, chuyển cho người khác) | "thu_nhap" (lương, thưởng, người khác '
            'chuyển cho) | "tra_no" (trả nợ vay, trả góp khoản vay) | "tra_the" (thanh toán / trích nợ sao kê thẻ tín '
            'dụng) | "chuyen_noi_bo" (chuyển giữa các tài khoản của CHÍNH chủ tài khoản: cùng tên người; người trả nợ '
            'thẻ tín dụng thường chính là chủ tài khoản), '
            '"nhom": một mã trong ' + groups + "}]}\n"
            "Riêng khi ảnh là XÁC NHẬN LỆNH QUỸ MỞ (mua hoặc hoán đổi chứng chỉ quỹ, ví dụ trên Fmarket), ĐƠN MUA VÀNG "
            "tích trữ (vàng nhẫn, vàng miếng, vàng ép vỉ) hoặc KẾT QUẢ LỆNH CỔ PHIẾU (mua/bán, khối lượng, giá khớp) thì "
            'trả {"loai": "tai_san", "giao_dich": [], "viec": {...}}, với "viec" là một trong ba dạng:\n'
            '{"viec": "quy", "chieu": "mua" | "hoan_doi", "ma": mã quỹ mua, "tien": số tiền mua (đồng), "ccq": số ccq đem '
            'hoán đổi, "ngay": "YYYY-MM-DD" ngày đặt lệnh}\n'
            '{"viec": "vang", "loai": "nhan" (nhẫn, 24k, ép vỉ) | "sjc" (vàng miếng SJC), "chi": TỔNG số chỉ (số vỉ × số '
            'chỉ mỗi vỉ; 1 lượng = 10 chỉ), "tien": số tiền thực trả (Thành tiền, sau giảm giá)}\n'
            '{"viec": "co_phieu", "chieu": "mua" | "ban", "ma": mã cổ phiếu, "sl": khối lượng, "gia": giá khớp tính bằng '
            'nghìn đồng như trên ảnh (12.00 là 12), "gia_von": giá vốn hoặc giá hòa vốn nếu ảnh có}\n'
            "Trường nào ảnh không ghi thì bỏ hẳn, không đoán.\n"
            "Hóa đơn: 1 phần tử, so_tien là TỔNG GIÁ TRỊ (dòng TỔNG CỘNG / Tong tien / TỔNG THANH TOÁN, kể cả phần trả "
            "bằng voucher hay điểm; không lấy tiền khách đưa, tiền thừa, số dư hay từng dòng phương thức thanh toán). "
            + owner +
            "Danh sách: mỗi dòng giao dịch một phần tử, đúng thứ tự trên ảnh; dòng bị cắt mất số tiền thì bỏ; tiêu đề "
            '"Hôm nay" thì ngay là null. Không phải hóa đơn hay giao dịch thì {"loai": "khac", "giao_dich": []}.')


def money_of(value):
    if isinstance(value, (int, float)):
        return max(0, round(value))
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())  # "29.000đ", "-4,390,000" -> số
    return int(digits) if digits else 0


def read_receipt(data, mime):
    """Nhờ AI đọc ảnh: {"loai", "giao_dich": [{tien, chieu, ngay, noi_dung, noi_ban, diem, nhom, kieu}], "model"}."""
    # Lúc Gemini đông có khi mất 10–20 giây/ảnh: chờ mỗi model tới 30 giây, tổng không quá 48 giây
    text, model = ct.ai_chat("Bạn đọc hóa đơn và màn hình giao dịch ngân hàng của người Việt, trả lời bằng JSON.",
                             prompt(kho.get(OWNERS, []) or []), max_tokens=4000, image=(data, mime), timeout=30,
                             budget=48)
    raw = ct.first_json(text)
    if not isinstance(raw, dict):
        raise RuntimeError(f"AI trả lời không đúng dạng: {text[:100]!r}")
    items = raw.get("giao_dich")
    if not isinstance(items, list):  # kiểu cũ: một khoản nằm ngay ngoài cùng
        items = [raw] if raw.get("so_tien") else []
    txs = []
    for it in items[:20]:
        if not isinstance(it, dict) or not money_of(it.get("so_tien")):
            continue
        chieu = "thu" if it.get("chieu") == "thu" else "chi"
        kieu = it.get("kieu") if it.get("kieu") in KINDS else ("thu_nhap" if chieu == "thu" else "chi_tieu")
        if chieu == "thu" and kieu in ("chi_tieu", "tra_no", "tra_the"):
            kieu = "thu_nhap"
        if chieu == "chi" and kieu == "thu_nhap":
            kieu = "chi_tieu"
        txs.append({"tien": money_of(it.get("so_tien")), "chieu": chieu, "ngay": it.get("ngay"),
                    "noi_dung": ct.norm(str(it.get("noi_dung") or ""))[:60], "noi_ban": str(it.get("noi_ban") or "")[:40],
                    "diem": money_of(it.get("diem")), "nhom": str(it.get("nhom") or ""), "kieu": kieu})
    print(f"[ảnh] đọc bằng {model}: {raw.get('loai')}, {len(txs)} giao dịch", file=sys.stderr)
    return {"loai": raw.get("loai"), "giao_dich": txs, "model": model, "viec": raw.get("viec")}


def fingerprint(ngay, tien, chieu):
    return f"{DONE_TX}{ngay}|{tien}|{chieu}"


def receipt_date(text, today):
    """'04/11/2026' -> date; không đọc được, ở tương lai hay quá 1 năm thì lấy hôm nay."""
    try:
        d, m, y = (int(x) for x in str(text).replace("-", "/").split("/")[:3])
        when = date(y, m, d)
    except (ValueError, TypeError):
        return today
    return when if today - timedelta(days=366) <= when <= today else today


def photo(message, tok, now):
    """Ghi khoản từ ảnh trong tin nhắn; trả câu trả lời (chữ, hoặc (chữ, nút)). Ảnh nhiều giao dịch thì hiện danh
    sách để chọn trước khi ghi."""
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
    if info["loai"] == "tai_san" and info.get("viec"):
        # lệnh quỹ, đơn mua vàng, kết quả lệnh cổ phiếu: hỏi trường còn thiếu rồi xin xác nhận trước khi ghi
        reply = ct.troly().from_photo(info["viec"], (message.get("chat") or {}).get("id"), now)
        if reply is not None:
            kho.delete(seen)  # chưa ghi gì cho tới khi bấm ✅; gửi lại ảnh này vẫn được
            return reply
    txs = info["giao_dich"]
    if info["loai"] == "khac" or not txs:
        kho.delete(seen)
        return "🤔 Không thấy hóa đơn hay giao dịch nào trong ảnh. Chụp rõ dòng tổng tiền rồi gửi lại nhé"
    names = owner_names(txs)
    for tx in txs:
        if tx["kieu"] in ("thu_nhap", "chi_tieu") and own_transfer(tx, names):
            tx["kieu"] = "chuyen_noi_bo"
    if len(txs) == 1 and txs[0]["kieu"] in ("chi_tieu", "thu_nhap"):
        # hóa đơn: hai ly cà phê cùng giá trong ngày là chuyện thường, không coi là trùng
        return single(txs[0], message, now, check_dup=info["loai"] != "hoa_don")
    day = now.date()
    for tx in txs:
        tx["ngay"] = receipt_date(tx["ngay"], day).isoformat()
        tx["da_ghi"] = kho.get(fingerprint(tx["ngay"], tx["tien"], tx["chieu"])) is not None
        tx["chon"] = tx["kieu"] in ("chi_tieu", "thu_nhap", "tra_no") and not tx["da_ghi"]
    kho.put(PENDING + unique, txs, 2 * 86400)
    return render_list(unique, txs, day)


def render_list(unique, txs, day):
    """Danh sách giao dịch đọc được: ✅ sẽ ghi, ⏭ bỏ qua (kèm lý do); nút bấm số để đổi, nút Ghi."""
    lines = [f"📷 <b>Đọc được {len(txs)} giao dịch</b> · bấm số để chọn/bỏ, rồi bấm Ghi"]
    for i, tx in enumerate(txs, 1):
        sign = "+" if tx["chieu"] == "thu" else "−"
        what = html.escape(tx["noi_dung"] or tx["noi_ban"] or "không rõ nội dung")
        when = "" if tx["ngay"] == day.isoformat() else f" · {tx['ngay'][8:]}/{tx['ngay'][5:7]}"
        why = "" if tx["chon"] else (
            f" <i>({SKIP_WHY.get('da_ghi' if tx.get('da_ghi') else tx['kieu'], 'bỏ qua')})</i>")
        lines.append(f"{'✅' if tx['chon'] else '⏭'} {i}. <b>{sign}{ct.vnd(tx['tien'])}</b> {what}{when}{why}")
    chosen = [tx for tx in txs if tx["chon"]]
    if chosen:
        income = sum(tx["tien"] for tx in chosen if tx["chieu"] == "thu")
        spend = sum(tx["tien"] for tx in chosen if tx["chieu"] == "chi")
        lines.append("Sẽ ghi: " + " · ".join(x for x in [f"thu {ct.vnd(income)}" if income else "",
                                                          f"chi {ct.vnd(spend)}" if spend else ""] if x))
    toggles = [(f"{'✅' if tx['chon'] else '⏭'} {i}", f"anh:chon:{unique}:{i - 1}") for i, tx in enumerate(txs, 1)]
    rows = [toggles[i:i + 5] for i in range(0, len(toggles), 5)]
    rows.append(([(f"✅ Ghi {len(chosen)} khoản", f"anh:ghi:{unique}")] if chosen else []) + [("❌ Bỏ", f"anh:bo:{unique}")])
    return "\n".join(lines), rows


def entry_from(tx, learned, active):
    """Khoản để ghi từ một giao dịch đọc được."""
    note = tx["noi_dung"] or ct.norm(tx["noi_ban"])
    e = {"ngay": tx["ngay"], "tien": tx["tien"], "ghichu": note, "anh": True}
    if tx["chieu"] == "thu":
        e["nhom"] = ct.INCOME
        return e
    e["nhom"] = ct.classify(note, learned)  # nhóm bạn đã dạy, từ khóa: đáng tin hơn AI đoán
    if e["nhom"] == ct.OTHER and tx["kieu"] == "tra_no":
        e["nhom"] = ct.find_group("trả nợ") or ct.OTHER  # có nhóm Trả nợ (tự tạo) thì vào đó
    if e["nhom"] == ct.OTHER and tx["nhom"] in active and tx["nhom"] not in (ct.OTHER, ct.INCOME):
        e["nhom"], e["ai"] = tx["nhom"], True
    return e


def record(txs, now):
    learned, active, out = kho.get(ct.K_LEARN, {}), ct.groups(), []
    for tx in txs:
        e = entry_from(tx, learned, active)
        e["id"] = kho.command("INCR", ct.K_COUNTER)
        e["gio"] = now.strftime("%H:%M")
        ct.save(e)
        kho.put(fingerprint(e["ngay"], e["tien"], tx["chieu"]), e["id"], 120 * 86400)
        out.append(e)
    return out


def single(tx, message, now, check_dup=True):
    """Ảnh một khoản (hóa đơn, một giao dịch): ghi luôn."""
    day = now.date()
    caption = (message.get("caption") or "").strip()
    chosen, missing, rest = ct.read_tag(caption) if caption else (None, None, "")
    tx["ngay"] = receipt_date(tx["ngay"], day).isoformat()
    if ct.norm(rest):
        tx["noi_dung"] = ct.norm(rest)
    if check_dup and kho.get(fingerprint(tx["ngay"], tx["tien"], tx["chieu"])) is not None:
        return (f"📷 Giao dịch {'+' if tx['chieu'] == 'thu' else '−'}{ct.vnd(tx['tien'])} ngày "
                f"{tx['ngay'][8:]}/{tx['ngay'][5:7]} đã ghi trước đó. Xem lại: /lichsu")
    learned = kho.get(ct.K_LEARN, {})
    e = entry_from(tx, learned, ct.groups())
    if chosen and tx["chieu"] == "chi":
        e["nhom"] = chosen
        e.pop("ai", None)
        ct.learn(e["ghichu"], chosen)
    e["id"] = kho.command("INCR", ct.K_COUNTER)
    e["gio"] = now.strftime("%H:%M")
    ct.save(e)
    kho.put(fingerprint(e["ngay"], e["tien"], tx["chieu"]), e["id"], 120 * 86400)
    seen_from = f" · {html.escape(tx['noi_ban'])}" if tx["noi_ban"] else ""
    extra = [f"📷 Đọc từ ảnh{seen_from}, kiểm tra lại số tiền và ngày nhé"]
    if missing:
        extra.append(f"⚠️ Chưa có nhóm «{html.escape(missing)}», tạo bằng: /nhom them {html.escape(missing)}")
    debt_lines, debt_rows = ct.debt_after([e], day)  # chuyển khoản trả nợ: trừ dư nợ
    extra += debt_lines
    try:
        extra += ct.phantich().after_record([e], day)
    except Exception as err:
        print(f"[lỗi] phân tích sau khi ghi ảnh: {err!r}", file=sys.stderr)
    text, rows = ct.entries_message([e], day, extra=extra)
    rows = (rows or []) + debt_rows
    if tx["diem"] and tx["chieu"] == "chi" and tx["diem"] < tx["tien"] * 1.01:
        text += (f"\n🎁 Có {ct.vnd(tx['diem'])} trả bằng voucher/điểm thưởng. Điểm đổi từ chi tiêu (thẻ tín dụng…) "
                 "nên ghi là khoản thu:")
        rows = rows + [[(f"➕ Ghi {ct.vnd(tx['diem'])} vào Thu nhập", f"anh:diem:{tx['diem']}")]]
    return text, rows


def on_button(arg, message, now):
    """Nút ảnh: "diem:<số tiền>" ghi phần trả bằng điểm/voucher; "chon:<ảnh>:<số>" chọn/bỏ một giao dịch;
    "ghi:<ảnh>" ghi các giao dịch đã chọn; "bo:<ảnh>" bỏ cả danh sách."""
    kind, _, rest = arg.partition(":")
    day = now.date()
    if kind == "diem" and rest.isdigit():
        e = {"id": kho.command("INCR", ct.K_COUNTER), "ngay": day.isoformat(), "gio": now.strftime("%H:%M"),
             "tien": int(rest), "ghichu": "đổi điểm, voucher", "nhom": ct.INCOME}
        ct.save(e)
        rows = [row for row in ct.keyboard_rows(message) if not any(d.startswith("anh:diem") for _, d in row)]
        return f"Đã ghi {ct.vnd(int(rest))} vào Thu nhập", ("buttons", lambda: rows)
    if kind not in ("chon", "ghi", "bo"):
        return None, None
    unique, _, index = rest.rpartition(":") if kind == "chon" else (rest, "", "")
    txs = kho.get(PENDING + unique)
    if txs is None:
        return "Danh sách này đã hết hạn hoặc đã ghi, gửi lại ảnh nhé", None
    if kind == "bo":
        kho.delete(PENDING + unique)
        kho.delete(SEEN + unique)  # gửi lại ảnh này được
        return "Đã bỏ", ("edit", lambda: "📷 Đã bỏ danh sách, không ghi khoản nào")
    if kind == "chon":
        if not index.isdigit() or int(index) >= len(txs):
            return None, None
        txs[int(index)]["chon"] = not txs[int(index)]["chon"]
        kho.put(PENDING + unique, txs, 2 * 86400)
        return None, ("edit", lambda: render_list(unique, txs, day))
    chosen = [tx for tx in txs if tx["chon"]]
    if not chosen:
        return "Chưa chọn khoản nào", None
    kho.delete(PENDING + unique)
    entries = record(chosen, now)
    extra = [f"📷 Ghi từ ảnh, bỏ qua {len(txs) - len(chosen)} giao dịch không chọn"]
    debt_lines, debt_rows = ct.debt_after(entries, day)  # có khoản trả nợ: trừ dư nợ trong /no
    extra += debt_lines
    try:
        extra += ct.phantich().after_record(entries, day)
    except Exception as err:
        print(f"[lỗi] phân tích sau khi ghi ảnh: {err!r}", file=sys.stderr)
    def done():
        text, rows = ct.entries_message(entries, day, extra=extra)
        rows = (rows or []) + debt_rows
        hint = ct.salary_fund_hint(entries, day)  # ảnh có lương: gợi ý chia lương (trả nợ, quỹ dự phòng...)
        return (text + "\n" + hint[0], rows + [hint[1]]) if hint else (text, rows)
    return f"Đã ghi {len(entries)} khoản", ("edit", done)
