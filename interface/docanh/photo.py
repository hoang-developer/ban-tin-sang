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
import sys

from domain.docanh.receipt import receipt_date
from infrastructure import ai, kho
from presentation.docanh import view
from repositories.chitieu import groups as groups_repo
from repositories.docanh import receipts as repo
from services.docanh import receipts
from domain.common.format import vnd
from domain.common.text import norm
from interface import common
from interface.chitieu import bot as chitieu_bot
from interface.chitieu import context as chitieu_ctx
from interface.chitieu import features
from presentation.chitieu import view as cview


def image_of(message):
    """(mã file, mã ảnh duy nhất, kiểu ảnh) của ảnh trong tin nhắn; None nếu tin không có ảnh."""
    if message.get("photo"):
        best = message["photo"][-1]  # Telegram xếp các cỡ từ nhỏ tới lớn
        return best["file_id"], best.get("file_unique_id", best["file_id"]), "image/jpeg"
    doc = message.get("document") or {}
    if (doc.get("mime_type") or "").startswith("image/"):
        return doc["file_id"], doc.get("file_unique_id", doc["file_id"]), doc["mime_type"]
    return None


def photo(message, tok, now):
    """Ghi khoản từ ảnh trong tin nhắn; trả câu trả lời (chữ, hoặc (chữ, nút)). Ảnh nhiều giao dịch thì hiện danh
    sách để chọn trước khi ghi."""
    if not kho.ready():
        return cview.NEED_STORE
    groups_repo.reset()
    file_id, unique, mime = image_of(message)
    if not ai.key():
        return view.NO_AI_KEY
    if not repo.claim_image(unique):
        return view.ALREADY_READ
    try:
        info = receipts.read_receipt(receipts.download(file_id, tok), mime)
    except Exception as e:
        print(f"[lỗi] đọc ảnh: {e!r}", file=sys.stderr)
        repo.release_image(unique)
        return view.UNREADABLE
    if info["loai"] == "tai_san" and info.get("viec"):
        # lệnh quỹ, đơn mua vàng, kết quả lệnh cổ phiếu: hỏi trường còn thiếu rồi xin xác nhận trước khi ghi
        reply = features.troly().from_photo(info["viec"], (message.get("chat") or {}).get("id"), now)
        if reply is not None:
            repo.release_image(unique)  # chưa ghi gì cho tới khi bấm ✅; gửi lại ảnh này vẫn được
            return reply
    txs = info["giao_dich"]
    if info["loai"] == "khac" or not txs:
        repo.release_image(unique)
        return view.NOTHING_FOUND
    receipts.mark_own_transfers(txs)
    if len(txs) == 1 and txs[0]["kieu"] in ("chi_tieu", "thu_nhap"):
        # hóa đơn: hai ly cà phê cùng giá trong ngày là chuyện thường, không coi là trùng
        return single(txs[0], message, now, check_dup=info["loai"] != "hoa_don")
    day = now.date()
    receipts.prepare_list(txs, day)
    repo.save_pending(unique, txs)
    return view.render_list(unique, txs, day)


def single(tx, message, now, check_dup=True):
    """Ảnh một khoản (hóa đơn, một giao dịch): ghi luôn."""
    day = now.date()
    caption = (message.get("caption") or "").strip()
    chosen, missing, rest = chitieu_ctx.read_tag(caption) if caption else (None, None, "")
    tx["ngay"] = receipt_date(tx["ngay"], day).isoformat()
    if norm(rest):
        tx["noi_dung"] = norm(rest)
    if check_dup and repo.recorded(tx["ngay"], tx["tien"], tx["chieu"]) is not None:
        return view.duplicate(tx)
    e = receipts.record_one(tx, now, chosen)
    seen_from = f" · {html.escape(tx['noi_ban'])}" if tx["noi_ban"] else ""
    extra = [f"📷 Đọc từ ảnh{seen_from}, kiểm tra lại số tiền và ngày nhé"]
    if missing:
        extra.append(f"⚠️ Chưa có nhóm «{html.escape(missing)}», tạo bằng: /nhom them {html.escape(missing)}")
    debt_lines, debt_rows = chitieu_bot.debt_after([e], day)  # chuyển khoản trả nợ: trừ dư nợ
    extra += debt_lines
    try:
        extra += features.phantich().after_record([e], day)
    except Exception as err:
        print(f"[lỗi] phân tích sau khi ghi ảnh: {err!r}", file=sys.stderr)
    text, rows = chitieu_ctx.entries_message([e], day, extra=extra)
    rows = (rows or []) + debt_rows
    if tx["diem"] and tx["chieu"] == "chi" and tx["diem"] < tx["tien"] * 1.01:
        text += (f"\n🎁 Có {vnd(tx['diem'])} trả bằng voucher/điểm thưởng. Điểm đổi từ chi tiêu (thẻ tín dụng…) "
                 "nên ghi là khoản thu:")
        rows = rows + [[(f"➕ Ghi {vnd(tx['diem'])} vào Thu nhập", f"anh:diem:{tx['diem']}")]]
    return text, rows


def on_button(arg, message, now):
    """Nút ảnh: "diem:<số tiền>" ghi phần trả bằng điểm/voucher; "chon:<ảnh>:<số>" chọn/bỏ một giao dịch;
    "ghi:<ảnh>" ghi các giao dịch đã chọn; "bo:<ảnh>" bỏ cả danh sách."""
    kind, _, rest = arg.partition(":")
    day = now.date()
    if kind == "diem" and rest.isdigit():
        receipts.record_points(int(rest), day, now)
        rows = [row for row in common.keyboard_rows(message) if not any(d.startswith("anh:diem") for _, d in row)]
        return f"Đã ghi {vnd(int(rest))} vào Thu nhập", ("buttons", lambda: rows)
    if kind not in ("chon", "ghi", "bo"):
        return None, None
    unique, _, index = rest.rpartition(":") if kind == "chon" else (rest, "", "")
    txs = repo.pending(unique)
    if txs is None:
        return "Danh sách này đã hết hạn hoặc đã ghi, gửi lại ảnh nhé", None
    if kind == "bo":
        repo.delete_pending(unique)
        repo.release_image(unique)  # gửi lại ảnh này được
        return "Đã bỏ", ("edit", lambda: "📷 Đã bỏ danh sách, không ghi khoản nào")
    if kind == "chon":
        if not index.isdigit() or int(index) >= len(txs):
            return None, None
        txs[int(index)]["chon"] = not txs[int(index)]["chon"]
        repo.save_pending(unique, txs)
        return None, ("edit", lambda: view.render_list(unique, txs, day))
    chosen = [tx for tx in txs if tx["chon"]]
    if not chosen:
        return "Chưa chọn khoản nào", None
    repo.delete_pending(unique)
    entries = receipts.record(chosen, now)
    extra = [f"📷 Ghi từ ảnh, bỏ qua {len(txs) - len(chosen)} giao dịch không chọn"]
    debt_lines, debt_rows = chitieu_bot.debt_after(entries, day)  # có khoản trả nợ: trừ dư nợ trong /no
    extra += debt_lines
    try:
        extra += features.phantich().after_record(entries, day)
    except Exception as err:
        print(f"[lỗi] phân tích sau khi ghi ảnh: {err!r}", file=sys.stderr)

    def done():
        text, rows = chitieu_ctx.entries_message(entries, day, extra=extra)
        rows = (rows or []) + debt_rows
        hint = chitieu_bot.salary_fund_hint(entries, day)  # ảnh có lương: gợi ý chia lương (trả nợ, quỹ dự phòng...)
        return (text + "\n" + hint[0], rows + [hint[1]]) if hint else (text, rows)
    return f"Đã ghi {len(entries)} khoản", ("edit", done)
