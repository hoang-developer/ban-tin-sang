"""Chữ của phần đọc ảnh: danh sách giao dịch để chọn, các lời nhắn khi ảnh không dùng được."""
import html

from domain.common.format import vnd
from domain.docanh.receipt import SKIP_WHY

NO_AI_KEY = "📷 Đọc ảnh cần AI: thêm biến GEMINI_API_KEY trên Vercel rồi Redeploy (xem README). Giờ nhắn tay kiểu: cà phê 35k"
ALREADY_READ = "📷 Ảnh này đã ghi rồi. Xem lại: /lichsu"
UNREADABLE = "⚠️ Chưa đọc được ảnh (AI bận hoặc ảnh quá mờ). Gửi lại sau, hoặc nhắn tay kiểu: cà phê 35k"
NOTHING_FOUND = "🤔 Không thấy hóa đơn hay giao dịch nào trong ảnh. Chụp rõ dòng tổng tiền rồi gửi lại nhé"


def duplicate(tx):
    return (f"📷 Giao dịch {'+' if tx['chieu'] == 'thu' else '−'}{vnd(tx['tien'])} ngày "
            f"{tx['ngay'][8:]}/{tx['ngay'][5:7]} đã ghi trước đó. Xem lại: /lichsu")


def render_list(unique, txs, day):
    """Danh sách giao dịch đọc được: ✅ sẽ ghi, ⏭ bỏ qua (kèm lý do); nút bấm số để đổi, nút Ghi."""
    lines = [f"📷 <b>Đọc được {len(txs)} giao dịch</b> · bấm số để chọn/bỏ, rồi bấm Ghi"]
    for i, tx in enumerate(txs, 1):
        sign = "+" if tx["chieu"] == "thu" else "−"
        what = html.escape(tx["noi_dung"] or tx["noi_ban"] or "không rõ nội dung")
        when = "" if tx["ngay"] == day.isoformat() else f" · {tx['ngay'][8:]}/{tx['ngay'][5:7]}"
        why = "" if tx["chon"] else (
            f" <i>({SKIP_WHY.get('da_ghi' if tx.get('da_ghi') else tx['kieu'], 'bỏ qua')})</i>")
        lines.append(f"{'✅' if tx['chon'] else '⏭'} {i}. <b>{sign}{vnd(tx['tien'])}</b> {what}{when}{why}")
    chosen = [tx for tx in txs if tx["chon"]]
    if chosen:
        income = sum(tx["tien"] for tx in chosen if tx["chieu"] == "thu")
        spend = sum(tx["tien"] for tx in chosen if tx["chieu"] == "chi")
        lines.append("Sẽ ghi: " + " · ".join(x for x in [f"thu {vnd(income)}" if income else "",
                                                          f"chi {vnd(spend)}" if spend else ""] if x))
    toggles = [(f"{'✅' if tx['chon'] else '⏭'} {i}", f"anh:chon:{unique}:{i - 1}") for i, tx in enumerate(txs, 1)]
    rows = [toggles[i:i + 5] for i in range(0, len(toggles), 5)]
    rows.append(([(f"✅ Ghi {len(chosen)} khoản", f"anh:ghi:{unique}")] if chosen else []) + [("❌ Bỏ", f"anh:bo:{unique}")])
    return "\n".join(lines), rows
