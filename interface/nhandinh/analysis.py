"""Nhận định trong phiên cho bot bản tin: ngành hút tiền, khuyến nghị của các công ty chứng khoán (CTCK), tin tài
chính, rồi AI (Gemini, dùng chung cấu hình AI với bot chi tiêu) tổng hợp thành vài dòng.

Nguồn (thử ngày 05/11/2026):
- Khuyến nghị CTCK: VNDirect finfo (HSC, VNDirect, UBS, Yuanta, Vietcap, MBS...), có giá mục tiêu; ~100 khuyến
  nghị mỗi 30 ngày.
- Ngành: phân ngành ICB cấp 3 của VNDirect; giá, giá trị giao dịch, khối ngoại của ~430 mã HOSE từ Vietcap.
- Tin: RSS CafeF, Vietstock (cổ phiếu, nhận định thị trường, phân tích cơ bản), VnExpress kinh doanh.

Mọi con số do code tính. AI chỉ được dùng dữ liệu đưa vào; dòng nào nhắc mã không có trong dữ liệu thì bị bỏ.
Đây là thông tin tổng hợp để tham khảo, không phải lời khuyên đầu tư.
"""
import html

from domain.nhandinh.rules import pt_short
from infrastructure import clock, kho
from presentation.nhandinh import view
from repositories.nhandinh import cache
from services.chungkhoan import market
from services.nhandinh import ai as ai_service
from services.nhandinh import data as service

now_vn = clock.now_vn
gather, recommendations, safe = service.gather, service.recommendations, service.safe


def nganh_text(data=None):
    data = data or gather()
    return view.nganh_text(data, now_vn())


def khuyennghi(args):
    if args:
        code = args[0].upper()
        items = recommendations(180).get(code, [])
        if not items:
            return f"Không có khuyến nghị nào cho {html.escape(code)} trong 180 ngày qua (nguồn VNDirect)"
        q = (safe(market.quotes, [code]) or {}).get(code)
        price = (q["price"] or q["ref"]) if q else None
        return view.recommendation_detail(code, items, price)
    data = gather()
    rows = data["recs"]
    if not rows:
        return "Chưa lấy được khuyến nghị của các CTCK, thử lại sau"
    return view.recommendation_list(rows)


def tin_text(data=None):
    data = data or gather()
    if not data["news"]:
        return "Chưa lấy được tin tài chính, thử lại sau"
    return view.tin_text(data["news"], now_vn())


def brief(now=None, data=None):
    """Tin nhận định ngắn (chữ, nút); chi tiết xem bằng các nút."""
    now = now or now_vn()
    data = data or gather()
    lines = [view.headline(now, data)]
    smart = ai_service.ai_lines(data)
    if smart:
        lines += smart
    else:
        lines += view.short_fallback(data)
    return "\n".join(lines), view.BUTTONS


def nhandinh(args):
    word = (args[0].lower() if args else "")
    if word in ("tat", "tắt", "bat", "bật"):
        if not kho.ready():
            return "Cần kho dữ liệu để bật/tắt, gõ /caidat"
        if word in ("tat", "tắt"):
            cache.set_auto(False)
            return "Đã tắt nhận định tự gửi trong phiên. Bật lại: /nhandinh bat"
        cache.set_auto(True)
        return "Đã bật: ngày giao dịch bot gửi nhận định lúc 10h15 và 13h45"
    return brief()


def on_button(arg):
    """Nút "nd:...": (thông báo nhỏ, việc tiếp theo) như lenh.on_button."""
    if arg == "moi":
        return "Đang tổng hợp lại…", ("edit", brief)
    if arg == "nganh":
        return None, ("send", nganh_text)
    if arg == "kn":
        return None, ("send", lambda: khuyennghi([]))
    if arg == "tin":
        return None, ("send", tin_text)
    return None, None


def scheduled(now):
    """Nhận định tự gửi trong phiên: (chữ, nút) hoặc None nếu đã tắt, hay hôm nay không giao dịch."""
    if cache.auto_off():
        return None
    data = gather()
    vni = data["index"].get("VN-Index")
    if not vni or not vni[2]:  # chưa có giao dịch (ngày nghỉ lễ)
        return None
    return brief(now, data)
