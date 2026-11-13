"""Trợ lý của bot chi tiêu: hiểu câu nói thường, hỏi lại khi thiếu thông tin, xin xác nhận trước khi ghi.

Một "việc" là một dict {"viec": loại, ...trường}. Ba đường vào dùng chung một bộ máy:
- tin nhắn tự do: AI phân loại câu thành việc (ask_ai), code kiểm tra lại từng trường;
- ảnh: docanh nhờ AI đọc lệnh quỹ, đơn mua vàng, kết quả lệnh cổ phiếu thành việc (from_photo);
- nút bấm: ➕ Thêm tài khoản, sổ tiết kiệm, khoản nợ... tạo việc trống rồi bot hỏi từng trường (start).
Thiếu trường bắt buộc thì bot hỏi từng câu và nhớ đang hỏi dở việc gì (K_STATE, 15 phút). Việc ghi lại được ngay như
trước (khoản thu, trả nợ, xem màn hình, hỏi) thì làm luôn; việc khác hiện thẻ "Mình hiểu là…" với nút ✅ Đúng / ✏️ Sửa /
❌ Thôi, bấm ✅ mới ghi. Khoản chi thường ("cà phê 35k") không đi qua đây: vẫn ghi ngay như cũ (wants).
Số liệu luôn do code tính và ghi bằng các hàm sẵn có (taisan, sono, duphong, dautu...); AI chỉ hiểu câu. AI lỗi hay
bận thì bot hỏi lại bằng nút, không tự đoán.
"""
import html
import re
import sys
from datetime import date, timedelta

import kho
import sochitieu as ct
from bantin import WEEKDAYS, vn_num

K_STATE = "chitieu:cho:"  # việc đang làm dở của từng chat: {"viec": {...}, "hoi": trường đang hỏi, "sua": bool, "the": id}
K_CARD = "chitieu:the:"  # thẻ chờ xác nhận: id -> việc
K_CARD_ID = "chitieu:the:dem"
K_PLAIN = "chitieu:hieu:chi"  # ghi chú AI đã xác định là khoản chi thường: lần sau ghi ngay, khỏi hỏi AI
STATE_SECONDS, CARD_SECONDS = 900, 2 * 86400
TRY_LIMIT = 40  # số lượt thử ?hieu= mỗi ngày trên trang tình trạng


def F(ten, kieu, hoi=None, can=True, goi=False, chon=None):
    """Một trường của việc. kieu: tien (đồng), so, chu, ngay (ISO), chon (một trong các lựa chọn), co (đúng/sai).
    can: bắt buộc; goi: không bắt buộc nhưng hỏi một lần (có nút Bỏ qua); chon: [(giá trị, nhãn)] hoặc hàm trả danh sách."""
    return {"ten": ten, "kieu": kieu, "hoi": hoi, "can": can, "goi": goi, "chon": chon}


def debt_choices():
    try:
        return [(d["ten"], d["ten"]) for d in ct.sono().active()][:6]
    except Exception as e:
        print(f"[lỗi] danh sách nợ: {e!r}", file=sys.stderr)
        return []


TERMS = [(0, "Không kỳ hạn"), (1, "1 tháng"), (3, "3 tháng"), (6, "6 tháng"), (12, "12 tháng")]
JOBS = {
    "thu": {"nhan": "💰 Khoản thu", "xac_nhan": False, "truong": [
        F("tien", "tien", "Nhận được bao nhiêu?"), F("ghi_chu", "chu", can=False), F("ngay", "ngay", can=False)]},
    "tra_no": {"nhan": "💳 Trả nợ", "xac_nhan": False, "truong": [
        F("ten", "chu", "Trả khoản nợ nào?", chon=debt_choices), F("tien", "tien", "Trả bao nhiêu?"),
        F("ngay", "ngay", can=False)]},
    "du_phong": {"nhan": "🛟 Quỹ dự phòng", "xac_nhan": True, "truong": [
        F("tien", "tien", "Số tiền bao nhiêu?"),
        F("chieu", "chon", can=False, chon=[("nap", "Nạp vào"), ("rut", "Rút ra")])]},
    "tiet_kiem": {"nhan": "🐷 Sổ tiết kiệm", "xac_nhan": True, "truong": [
        F("ten", "chu", "Gửi ở ngân hàng nào? (tên sổ)"), F("tien", "tien", "Gửi bao nhiêu?"),
        F("lai", "so", "Lãi suất bao nhiêu %/năm?"), F("ky", "so", "Kỳ hạn mấy tháng?", chon=TERMS),
        F("ngay", "ngay", can=False)]},
    "tai_khoan": {"nhan": "🏦 Số dư tài khoản", "xac_nhan": True, "truong": [
        F("ten", "chu", "Tài khoản hay ví nào? (ví dụ Techcombank, MoMo, tiền mặt)"),
        F("tien", "tien", "Số dư hiện tại bao nhiêu?"), F("chinh", "co", can=False)]},
    "vang": {"nhan": "🥇 Mua vàng", "xac_nhan": True, "truong": [
        F("loai", "chon", "Vàng nhẫn (24k, ép vỉ) hay vàng miếng SJC?", chon=[("nhan", "Nhẫn 24k"), ("sjc", "Miếng SJC")]),
        F("chi", "so", "Bao nhiêu chỉ? (1 lượng = 10 chỉ)"),
        F("tien", "tien", "Tổng tiền đã trả bao nhiêu? (để tính lãi lỗ)", can=False, goi=True)]},
    "co_phieu": {"nhan": "📈 Cổ phiếu", "xac_nhan": True, "truong": [
        F("chieu", "chon", "Mua hay bán?", chon=[("mua", "Mua"), ("ban", "Bán")]),
        F("ma", "chu", "Mã cổ phiếu nào?"), F("sl", "so", "Số lượng bao nhiêu cổ phiếu?"),
        F("gia", "so", "Giá khớp bao nhiêu? (nghìn đồng một cổ phiếu, ví dụ 12 hoặc 95,5)"),
        F("gia_von", "so", can=False)]},
    "quy": {"nhan": "💹 Quỹ mở", "xac_nhan": True, "truong": [
        F("chieu", "chon", can=False, chon=[("mua", "Mua"), ("hoan_doi", "Hoán đổi")]),
        F("ma", "chu", can=False), F("tien", "tien", "Số tiền bao nhiêu?", can=False), F("ccq", "so", can=False),
        F("ngay", "ngay", can=False), F("sau_gio", "co", can=False)]},
    "quy_cho": {"nhan": "📈 Quỹ chờ đầu tư", "xac_nhan": True, "truong": [
        F("tien", "tien", "Số tiền bao nhiêu?"),
        F("chieu", "chon", can=False, chon=[("nap", "Để vào"), ("rut", "Rút ra")])]},
    "chuyen_tk": {"nhan": "🔁 Chuyển tiền", "xac_nhan": True, "truong": [
        F("tien", "tien", "Chuyển bao nhiêu?"), F("den", "chu", "Chuyển sang tài khoản, ví nào?"),
        F("tu", "chu", "Chuyển từ tài khoản, ví nào?", can=False)]},
    "sua_ccq": {"nhan": "✏️ Sửa số ccq", "xac_nhan": False, "truong": [
        F("ccq", "so", "Fmarket báo lệnh vừa khớp được bao nhiêu ccq?"), F("ma", "chu", can=False)]},
    "no_moi": {"nhan": "💳 Khoản nợ", "xac_nhan": True, "truong": [
        F("ten", "chu", "Nợ ai, hoặc khoản gì? (ví dụ chú Tư, trả góp tủ lạnh)"),
        F("tien", "tien", "Hiện còn nợ bao nhiêu?"),
        F("moi_thang", "tien", "Mỗi tháng trả bao nhiêu?", can=False, goi=True),
        F("lai", "so", "Lãi suất bao nhiêu %/năm?", can=False, goi=True, chon=[(0, "Không lãi")]),
        F("ngay_tra", "so", can=False)]},
    "cho_vay": {"nhan": "🤝 Cho vay", "xac_nhan": True, "truong": [
        F("ten", "chu", "Cho ai vay?"), F("tien", "tien", "Cho vay bao nhiêu?")]},
    "ngan_sach": {"nhan": "🎯 Ngân sách", "xac_nhan": True, "truong": [
        F("nhom", "chu", "Ngân sách cho nhóm nào? (tổng, hằng ngày, ăn uống, mua sắm…)"),
        F("tien", "tien", "Mỗi tháng bao nhiêu?")]},
    "ngay_luong": {"nhan": "💼 Ngày lương", "xac_nhan": True, "truong": [
        F("ngay_luong", "so", "Lương về ngày mấy hằng tháng?"), F("tien", "tien", "Lương khoảng bao nhiêu?")]},
}
SCREENS = ("tong_quan", "chi_tieu", "tai_san", "no", "ke_hoach", "chia_luong", "du_phong", "dau_tu", "tiet_kiem",
           "suc_khoe", "lich_su", "bieu_do", "du_bao", "ngan_sach", "huong_dan")
PERIODS = ("ngay", "tuan", "thang", "thangtruoc")
SIMPLE = ("chi", "hoi", "xem", "khong_tieu", "xoa_cuoi", "khac")
# Thêm bằng nút: các loại hỏi được từng trường. Cổ phiếu, quỹ, tiền số có sẵn thì vẫn khai báo bằng /taisan.
ADD_MENU = [[("🏦 Tài khoản, ví", "y:them:tai_khoan"), ("🐷 Sổ tiết kiệm", "y:them:tiet_kiem")],
            [("🥇 Vàng", "y:them:vang"), ("🤝 Cho vay", "y:them:cho_vay")],
            [("💳 Khoản nợ", "y:them:no_moi"), ("📈 Mua bán cổ phiếu", "y:them:co_phieu")],
            [("🔁 Chuyển giữa tài khoản", "y:them:chuyen_tk"), ("🏦 Tài khoản chính", "ts:chinh")],
            [("📖 Cổ phiếu, quỹ, tiền số có sẵn", "ts:hd"), ct.BACK]]
EXAMPLES = ("• mua 2 chỉ vàng nhẫn hết 27tr\n• gửi tiết kiệm VCB 50tr lãi 4,7% 6 tháng\n• vay anh Nam 10tr, mỗi tháng trả "
            "2tr\n• nạp 2tr vào quỹ dự phòng\n• tài khoản Techcombank còn 14tr\n• tôi còn nợ bao nhiêu?")


# ---- Khi nào cần hiểu câu (không phải khoản chi thường) -------------------------------

# Chữ báo hiệu tin không phải khoản chi thường. So trên chữ có dấu khi người dùng gõ có dấu ("váy" khác "vay",
# "bạn" khác "bán"); gõ không dấu thì so trên chữ đã bỏ dấu.
TRIGGERS = ["chuyển", "nạp", "rút", "tiết kiệm", "vàng", "vay", "mượn", "quỹ", "ccq", "chứng chỉ", "cổ phiếu", "bán",
            "đầu tư", "tài khoản", "số dư", "ngân sách", "lương về", "nhận lương", "nhận tiền", "được thưởng",
            "hoán đổi", "tất toán", "đáo hạn", "dự phòng", "vff", "vmeef", "không tiêu", "khớp lệnh", "đặt lệnh",
            "nợ", "trả góp", "khoản vay"]
# Câu hỏi về thứ ngoài sổ chi tiêu (nợ, tài sản, quỹ, kế hoạch): không trả lời bằng sổ chi tiêu
BEYOND = ["nợ", "vay", "quỹ", "ccq", "vff", "vmeef", "tài sản", "tiết kiệm", "vàng", "cổ phiếu", "đầu tư", "dự phòng",
          "kế hoạch", "mục tiêu", "lãi", "lỗ", "ngân sách", "trả xong", "bao giờ", "khi nào", "tài khoản", "số dư",
          "sức khỏe", "để dành", "được tiêu", "nên tiêu"]


def word_re(words):
    return re.compile(r"(?<!\w)(?:" + "|".join(re.escape(w) for w in words) + r")(?!\w)")


TRIGGER_RE = (word_re(TRIGGERS), word_re([ct.plain(w) for w in TRIGGERS]))
BEYOND_RE = (word_re(BEYOND), word_re([ct.plain(w) for w in BEYOND]))


def mentions(text, pair):
    """Tin có nhắc một trong các chữ? Gõ có dấu thì so chữ có dấu, gõ không dấu thì so chữ đã bỏ dấu."""
    accented, bare = ct.norm(text), ct.plain(text)
    return bool(pair[0].search(accented) if accented != bare else pair[1].search(bare))


def beyond_spending(text):
    return mentions(text, BEYOND_RE)


def plain_notes():
    return kho.get(K_PLAIN, []) or []


def remember_plain(text):
    """AI bảo đây là khoản chi thường: nhớ ghi chú (đã bỏ số, ngày) để lần sau ghi ngay."""
    e = ct.parse_line(text, ct.today())
    key = ct.learn_key(e["ghichu"]) if e else ""
    notes = plain_notes()
    if key and key not in notes:
        kho.put(K_PLAIN, (notes + [key])[-300:])


def wants(text):
    """Tin này cần hiểu bằng AI (không phải khoản chi thường)? Chưa bật AI thì không: bot chạy như trước."""
    t = text.strip()
    if not ct.ai_key() or not t or "\n" in t or t[0] in "+/" or "#" in t:
        return False
    if not ct.parse_amount(t):
        return True  # không có số tiền: không phải khoản chi
    if not mentions(t, TRIGGER_RE):
        return False
    e = ct.parse_line(t, ct.today())
    return not (e and ct.learn_key(e["ghichu"]) in plain_notes())


# ---- Nhờ AI hiểu câu -------------------------------------------------------------------

def personal_context():
    """Tên khoản nợ, quỹ, tài khoản của người dùng (không kèm số tiền) để AI gọi đúng tên."""
    lines = []
    try:
        data = ct.taisan().load()
        debts = [it["ten"] for it in data["items"] if it["loai"] == "no" and it.get("tien", 0) > 0]
        accounts = [it["ten"] for it in data["items"] if it["loai"] in ("tien", "tietkiem")]
        if debts:
            lines.append("Khoản nợ đang có: " + "; ".join(debts[:10]))
        if accounts:
            lines.append("Tài khoản, sổ tiết kiệm đang có: " + "; ".join(accounts[:12]))
        cfg = ct.dautu().config()
        if cfg.get("ma"):
            side = ct.dautu().side(cfg)
            lines.append(f"Quỹ mở đang đầu tư định kỳ: {cfg['ma']}" + (f"; quỹ chờ: {side['ma']}" if side else ""))
    except Exception as e:
        print(f"[lỗi] ngữ cảnh cho AI: {e!r}", file=sys.stderr)
    return "\n".join(lines)


def prompt(day, personal=True):
    today = f"{WEEKDAYS[day.weekday()]} {day:%d/%m/%Y} ({day.isoformat()})"
    return (
        f"Bạn là bộ hiểu tin nhắn của một bot quản lý tài chính cá nhân của người Việt. Hôm nay là {today}. Đọc tin nhắn "
        "rồi trả về ĐÚNG MỘT dòng JSON, không giải thích. Trường \"viec\" là một trong:\n"
        '- "chi": một khoản chi tiêu thường (mua đồ, ăn uống, hóa đơn, biếu tặng, chuyển khoản trả tiền hàng, nạp điện '
        'thoại hay game, đóng quỹ lớp, mua vàng mã...). Không cần trường nào khác.\n'
        '- "thu": tiền nhận được (lương, thưởng, được cho, bán đồ cũ, hoàn tiền). Trường: "tien", "ghi_chu" (ngắn, có '
        'dấu), "ngay".\n'
        '- "tra_no": trả bớt một khoản nợ. "ten" (tên khoản nợ, dùng đúng tên đang có nếu khớp), "tien", "ngay".\n'
        '- "no_moi": vay thêm hoặc khai báo một khoản nợ (vay ai, mua trả góp, nợ thẻ). "ten", "tien" (số còn nợ), '
        '"moi_thang" (mỗi tháng trả), "lai" (%/năm; 0 nếu nói không lãi), "ngay_tra" (ngày trả hằng tháng).\n'
        '- "cho_vay": cho người khác vay hay mượn tiền. "ten" (người vay), "tien".\n'
        '- "du_phong": nạp vào hoặc rút khỏi quỹ dự phòng (quỹ khẩn cấp). "tien", "chieu": "nap" | "rut".\n'
        '- "tiet_kiem": gửi hoặc mở sổ tiết kiệm ở ngân hàng. "ten" (ngân hàng hay tên sổ), "tien", "lai" (%/năm), '
        '"ky" (số tháng; 0 nếu không kỳ hạn), "ngay" (ngày gửi).\n'
        '- "tai_khoan": báo số dư hiện có của một tài khoản, ví, tiền mặt. "ten", "tien", "chinh": true nếu nói là tài '
        'khoản chính hay tài khoản nhận lương.\n'
        '- "vang": MUA vàng tích trữ. "loai": "nhan" (nhẫn, vàng 24k/9999, vàng ép vỉ) | "sjc" (vàng miếng SJC), "chi" '
        '(tổng số chỉ; 1 lượng = 1 cây = 10 chỉ), "tien" (tổng tiền đã trả).\n'
        '- "co_phieu": mua hoặc bán cổ phiếu, ETF trên sàn. "chieu": "mua" | "ban", "ma", "sl" (số cổ phiếu), "gia" '
        '(giá một cổ phiếu đúng như người dùng nói: 12 hay 95,5 nghĩa là nghìn đồng), "gia_von" (nếu có nói).\n'
        '- "quy": mua chứng chỉ quỹ mở, hoặc hoán đổi từ quỹ này sang quỹ kia. "chieu": "mua" | "hoan_doi", "ma" (mã quỹ '
        'mua; hoán đổi thì không cần), "tien" (số tiền mua), "ccq" (số ccq đem hoán đổi), "ngay" (ngày đặt lệnh, chỉ khi '
        'người dùng nói rõ ngày hay buổi), "sau_gio": true nếu nói đặt sau 14h40.\n'
        '- "sua_ccq": báo số ccq thực tế của lệnh quỹ vừa khớp. "ccq", "ma".\n'
        '- "quy_cho": để tiền vào, hoặc rút ra khỏi, quỹ chờ đầu tư (tiền chờ mua quỹ mở theo kế hoạch). "tien", "chieu": '
        '"nap" | "rut".\n'
        '- "chuyen_tk": chuyển tiền giữa hai tài khoản, ví của CHÍNH MÌNH (ngân hàng sang ví MoMo, rút tiền mặt ở ATM). '
        '"tu" (tài khoản đi, nếu có nói), "den" (tài khoản đến), "tien". Chuyển cho người khác là "chi".\n'
        '- "ngan_sach": đặt ngân sách chi tiêu mỗi tháng. "nhom" ("tổng", "hằng ngày" hoặc tên nhóm chi như "ăn uống"), '
        '"tien".\n'
        '- "ngay_luong": cho biết ngày nhận lương hằng tháng. "ngay_luong" (1–31), "tien".\n'
        '- "khong_tieu": nói hôm nay hoặc hôm qua không tiêu gì. "ngay": "homnay" | "homqua".\n'
        '- "xoa_cuoi": muốn xóa khoản vừa ghi.\n'
        '- "xem": muốn mở một màn hình, hoặc HỎI về nợ, tài sản, quỹ, kế hoạch, tiền để dành. "man" là một trong: '
        'tong_quan, chi_tieu (báo cáo chi tiêu; thêm "ky": ngay | tuan | thang | thangtruoc), tai_san (tài sản ròng, '
        'vàng, cổ phiếu, số dư), no (sổ nợ: còn nợ bao nhiêu, bao giờ trả xong), ke_hoach (lộ trình, mục tiêu), '
        'chia_luong, du_phong (quỹ dự phòng), dau_tu (quỹ mở: lãi lỗ, tháng này mua bao nhiêu, hạn đặt lệnh), tiet_kiem '
        '(đã bớt chi bao nhiêu, chuỗi ngày ghi), suc_khoe (khám sức khỏe tài chính), lich_su (các khoản vừa ghi), '
        'bieu_do, du_bao (hôm nay còn được tiêu bao nhiêu), ngan_sach, huong_dan.\n'
        '- "hoi": câu hỏi về các khoản chi, thu ĐÃ GHI (hết bao nhiêu, nhiều nhất, so sánh, liệt kê).\n'
        '- "khac": không thuộc việc nào ở trên (kể cả bán vàng, rút tiết kiệm), hoặc không hiểu.\n'
        "Quy tắc: số tiền là số nguyên đồng (35k = 35000; 1tr2 = 1200000; 2 củ = 2000000; 1 tỷ = 1000000000). Ngày viết "
        "YYYY-MM-DD. Chỉ điền trường người dùng có nói, không tự đoán, không điền null. Câu thiếu thông tin (chưa nói "
        "ngân hàng, lãi suất, số tiền...) thì VẪN chọn đúng việc và chỉ điền phần đã biết: bot sẽ hỏi phần còn thiếu. Chỉ "
        "dùng \"khac\" khi câu không thuộc việc nào.\n"
        "Ví dụ:\n"
        'gửi tiết kiệm tcb 50tr lãi 4,7% kỳ 6 tháng → {"viec": "tiet_kiem", "ten": "TCB", "tien": 50000000, "lai": 4.7, '
        '"ky": 6}\n'
        'mua 2 vỉ vàng 0,1 chỉ hết 2tr476 → {"viec": "vang", "loai": "nhan", "chi": 0.2, "tien": 2476000}\n'
        'vay anh Nam 10tr không lãi → {"viec": "no_moi", "ten": "anh Nam", "tien": 10000000, "lai": 0}\n'
        'chuyển 5tr vào tiết kiệm → {"viec": "tiet_kiem", "tien": 5000000}\n'
        'trả góp tủ lạnh còn 8tr2 mỗi tháng 4tr1 không lãi → {"viec": "no_moi", "ten": "trả góp tủ lạnh", "tien": '
        '8200000, "moi_thang": 4100000, "lai": 0}\n'
        'trả nợ chú Tư 5tr → {"viec": "tra_no", "ten": "chú Tư", "tien": 5000000}\n'
        'hôm nay còn được tiêu bao nhiêu → {"viec": "xem", "man": "du_bao"}\n'
        'chuyển khoản tiền nhà 5tr → {"viec": "chi"}\n'
        'nạp 1tr vào quỹ dự phòng → {"viec": "du_phong", "tien": 1000000, "chieu": "nap"}\n'
        'chuyển 5tr từ VCB sang MoMo → {"viec": "chuyen_tk", "tu": "VCB", "den": "MoMo", "tien": 5000000}\n'
        'rút 2tr tiền mặt → {"viec": "chuyen_tk", "den": "tiền mặt", "tien": 2000000}\n'
        'để 4tr vào quỹ chờ → {"viec": "quy_cho", "tien": 4000000, "chieu": "nap"}\n'
        'bán 1300 HAG giá 12 → {"viec": "co_phieu", "chieu": "ban", "ma": "HAG", "sl": 1300, "gia": 12}\n'
        'tôi còn nợ bao nhiêu → {"viec": "xem", "man": "no"}\n'
        'quỹ lãi lỗ thế nào rồi → {"viec": "xem", "man": "dau_tu"}\n'
        'tháng này cà phê hết bao nhiêu → {"viec": "hoi"}'
        + (("\n" + personal_context()) if personal else ""))


def number_of(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip().rstrip("%").replace(",", "."))
    except ValueError:
        return None


def value_of(f, value):
    """Giá trị AI đưa cho một trường, đã kiểm tra theo kiểu trường; None nếu không dùng được."""
    if value is None or value == "":
        return None
    kind = f["kieu"]
    if kind == "tien":
        x = number_of(value)
        if x is None:
            found = ct.parse_amount(str(value))
            x = found[0] if found else None
        return int(round(abs(x))) if x and 0 < abs(x) < 1e12 else None
    if kind == "so":
        x = number_of(value)
        return x if x is not None and 0 <= x < 1e9 else None
    if kind == "chu":
        s = " ".join(str(value).split())[:40]
        if s.islower() and f["ten"] == "ten":
            s = s[0].upper() + s[1:]  # "techcombank" -> "Techcombank"
        return s if s and ct.plain(s) not in ("null", "none", "khong ro") else None
    if kind == "ngay":
        try:
            when = date.fromisoformat(str(value)[:10])
        except ValueError:
            m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", str(value))
            if not m:
                return None
            try:
                when = date(int(m[3]), int(m[2]), int(m[1]))
            except ValueError:
                return None
        return when.isoformat() if abs((when - ct.today()).days) < 3700 else None
    if kind == "chon":
        return value if value in [c[0] for c in choices(f)] else None
    if kind == "co":
        return True if value is True or str(value).lower() in ("true", "1", "co", "có") else None
    return None


def text_amounts(text):
    """(mọi số tiền code đọc được trong câu, riêng các số có ghi đơn vị như 35k, 2tr476), để soát số tiền AI đưa."""
    found = [(v, explicit) for v, explicit in (ct.money(m) for m in ct.MONEY.finditer(text or "")) if v]
    return [v for v, _ in found], [v for v, explicit in found if explicit]


def clean(raw, text=None):
    """JSON của AI -> việc hợp lệ: bỏ trường lạ, sai kiểu; số tiền chính đối chiếu với số code đọc được trong câu."""
    job = raw.get("viec") if isinstance(raw, dict) else None
    if job == "xem":
        man = raw.get("man")
        return {"viec": "xem", "man": man if man in SCREENS else "tong_quan",
                **({"ky": raw["ky"]} if raw.get("ky") in PERIODS else {})}
    if job == "khong_tieu":
        return {"viec": job, "ngay": "homqua" if raw.get("ngay") == "homqua" else "homnay"}
    if job in ("chi", "hoi", "xoa_cuoi"):
        a = {"viec": job}
        if job == "chi":  # câu không có số tiền mà AI vẫn đọc ra ("ăn phở ba lăm nghìn")
            for f in (F("tien", "tien"), F("ghi_chu", "chu")):
                v = value_of(f, raw.get(f["ten"]))
                if v is not None:
                    a[f["ten"]] = v
        return a
    if job not in JOBS:
        return {"viec": "khac"}
    a = {"viec": job}
    for f in JOBS[job]["truong"]:
        v = value_of(f, raw.get(f["ten"]))
        if v is not None:
            a[f["ten"]] = v
    seen, explicit = text_amounts(text) if text else ([], [])
    sure = explicit or seen  # số có ghi đơn vị đáng tin hơn số trơn ("2 vỉ", "0,1 chỉ")
    if a.get("tien") and a["tien"] not in seen and len(sure) == 1:
        a["tien"] = int(sure[0])  # câu chỉ có một số tiền mà AI đọc khác: tin số code đọc
    return a


def ask_ai(text, day, context=None, personal=True):
    """Nhờ AI hiểu một tin thành việc. context=(việc đang dở, câu bot vừa hỏi hoặc None): tin là câu trả lời/lời sửa."""
    system = prompt(day, personal)
    if context:
        doing, asked = context
        system += ("\nĐang làm dở việc này: " + repr({k: v for k, v in doing.items() if not k.startswith("_")})
                   + (f". Bot vừa hỏi: «{asked}»" if asked else ". Người dùng muốn sửa lại")
                   + ". Tin dưới đây là câu trả lời hoặc lời sửa: trả về JSON ĐẦY ĐỦ của việc đó sau khi cập nhật (giữ các "
                   "trường không đổi). Nếu tin là một việc khác hẳn thì trả JSON của việc mới.")
    out, model = ct.ai_chat(system, text, timeout=15, budget=25)
    raw = ct.first_json(out)
    if not isinstance(raw, dict):
        raise RuntimeError(f"AI trả lời không đúng dạng: {out[:100]!r}")
    print(f"[hiểu] {model}: {raw.get('viec')}", file=sys.stderr)
    return clean(raw, None if context else text)


# ---- Trạng thái hội thoại, thẻ xác nhận --------------------------------------------------

def chat_key(chat):
    return f"{K_STATE}{chat or 0}"


def state(chat):
    return kho.get(chat_key(chat))


def forget(chat):
    if kho.ready() and state(chat) is not None:
        kho.delete(chat_key(chat))


def choices(f):
    return (f["chon"]() if callable(f["chon"]) else f["chon"]) or []


def field(job, name):
    return next((f for f in JOBS[job]["truong"] if f["ten"] == name), None)


def num(x):
    return f"{float(x):g}".replace(".", ",")


def price_dong(x):
    """Giá cổ phiếu: 12 hay 95,5 là nghìn đồng; từ 1.000 trở lên là đồng."""
    return x * 1000 if x < 1000 else x


def missing(a):
    """Trường kế tiếp cần hỏi: trường bắt buộc còn thiếu, rồi trường nên hỏi một lần (chưa bỏ qua)."""
    job = a["viec"]
    if job == "quy":  # mua cần số tiền; hoán đổi cần số ccq
        need = "ccq" if a.get("chieu") == "hoan_doi" else "tien"
        if a.get(need) is None:
            f = dict(field(job, need))
            f["hoi"] = "Hoán đổi bao nhiêu ccq?" if need == "ccq" else "Số tiền mua bao nhiêu?"
            return f
        return None
    fields = JOBS[job]["truong"]
    for f in fields:
        if f["can"] and a.get(f["ten"]) is None:
            return f
    if job == "chuyen_tk" and not a.get("tu") and main_name() is None:
        return field(job, "tu")  # chưa có tài khoản chính: phải biết tiền đi từ đâu
    for f in fields:
        if f["goi"] and a.get(f["ten"]) is None and f["ten"] not in a.get("_bo", []):
            return f
    return None


def show(f, v):
    name = f["ten"]
    if f["kieu"] == "tien":
        return ("trả " if name == "moi_thang" else "") + ct.vnd(v) + ("/tháng" if name == "moi_thang" else "")
    if name == "lai":
        return f"lãi {num(v)}%/năm" if v else "không lãi"
    if name == "ky":
        return f"{int(v)} tháng" if v else "không kỳ hạn"
    if name == "chi":
        return f"{num(v)} chỉ"
    if name == "sl":
        return f"{vn_num(v, 0)} cp"
    if name in ("gia", "gia_von"):
        return ("giá vốn " if name == "gia_von" else "giá ") + vn_num(price_dong(v), 0) + "đ"
    if name == "ccq":
        return f"{num(v)} ccq"
    if name == "ngay_luong":
        return f"ngày {int(v)}"
    if f["kieu"] == "chon":
        return dict(choices(f)).get(v, str(v))
    if f["kieu"] == "ngay":
        return f"ngày {v[8:]}/{v[5:7]}"
    if name == "chinh":
        return "tài khoản chính"
    if name in ("tu", "den"):
        return ("từ " if name == "tu" else "sang ") + html.escape(str(v))
    if f["kieu"] == "co":
        return "sau 14h40"
    return html.escape(str(v))


def known(a):
    """'🐷 Sổ tiết kiệm: VCB · 100.000.000đ' từ các trường đã có."""
    spec = JOBS[a["viec"]]
    parts = [show(f, a[f["ten"]]) for f in spec["truong"] if a.get(f["ten"]) is not None]
    return spec["nhan"] + (": " + " · ".join(parts) if parts else "")


def question(a, f):
    opts = choices(f)
    rows = [[(label, f"y:tl:{f['ten']}:{i}") for i, (_, label) in enumerate(opts)][j:j + 3] for j in range(0, len(opts), 3)]
    last = ([("⏭ Bỏ qua", f"y:bo:{f['ten']}")] if not f["can"] else []) + [("❌ Thôi", "y:thoi")]
    return f"{known(a)}\n❓ <b>{f['hoi']}</b>", rows + [last]


def describe(a):
    """Câu mô tả việc trên thẻ xác nhận."""
    job, esc = a["viec"], html.escape
    money = ct.vnd(a["tien"]) if a.get("tien") else ""
    if job == "du_phong":
        out = a.get("chieu") == "rut"
        return (f"🛟 {'Rút' if out else 'Chuyển'} <b>{money}</b> {'khỏi' if out else 'vào'} quỹ dự phòng"
                + ("" if out else "\n<i>Là để dành, không tính là khoản chi</i>"))
    if job == "tiet_kiem":
        start = f", gửi ngày {a['ngay'][8:]}/{a['ngay'][5:7]}/{a['ngay'][:4]}" if a.get("ngay") else ""
        return (f"🐷 Sổ tiết kiệm <b>{esc(a['ten'])}</b>: <b>{money}</b>, lãi {num(a['lai'])}%/năm, "
                + (f"kỳ hạn {int(a['ky'])} tháng" if a.get("ky") else "không kỳ hạn") + start
                + "\n<i>Là tài sản, không tính là khoản chi</i>")
    if job == "tai_khoan":
        return f"🏦 Số dư <b>{esc(a['ten'])}</b> hiện là <b>{money}</b>" + (
            "\n<i>Là tài khoản chính: từ giờ bot tự cộng thu, trừ chi vào đây</i>" if a.get("chinh") else "")
    if job == "vang":
        kind = "vàng miếng SJC" if a["loai"] == "sjc" else "vàng nhẫn 24k"
        paid = ""
        if a.get("tien"):
            per = a["tien"] / (a["chi"] / 10) / 1e6
            paid = f", trả <b>{money}</b> (≈ {vn_num(per, 2)} triệu/lượng)"
        return f"🥇 Mua <b>{num(a['chi'])} chỉ</b> {kind}{paid}\n<i>Là tài sản, không tính là khoản chi</i>"
    if job == "co_phieu":
        cost = f", giá vốn {vn_num(price_dong(a['gia_von']), 0)}đ" if a.get("gia_von") else ""
        return (f"📈 {'Bán' if a['chieu'] == 'ban' else 'Mua'} <b>{vn_num(a['sl'], 0)} {esc(a['ma'].upper())}</b> giá "
                f"<b>{vn_num(price_dong(a['gia']), 0)}đ</b>{cost}")
    if job == "quy":
        when = (f", đặt ngày {a['ngay'][8:]}/{a['ngay'][5:7]}" if a.get("ngay") else "") + (
            " sau 14h40" if a.get("sau_gio") else "")
        if a.get("chieu") == "hoan_doi":
            return f"💹 Hoán đổi <b>{num(a['ccq'])} ccq</b> từ quỹ chờ sang quỹ chính{when}"
        return f"💹 Mua quỹ <b>{esc((a.get('ma') or fund_code() or 'quỹ đang đầu tư').upper())}</b>: <b>{money}</b>{when}"
    if job == "no_moi":
        extra = (f", mỗi tháng trả {ct.vnd(a['moi_thang'])}" if a.get("moi_thang") else "") + (
            "" if a.get("lai") is None else ", không lãi" if not a["lai"] else f", lãi {num(a['lai'])}%/năm") + (
            f", hạn ngày {int(a['ngay_tra'])}" if a.get("ngay_tra") else "")
        return f"💳 Khoản nợ <b>{esc(a['ten'])}</b>: còn nợ <b>{money}</b>{extra}"
    if job == "quy_cho":
        out = a.get("chieu") == "rut"
        code = fund_code()
        return (f"📈 {'Rút' if out else 'Để'} <b>{money}</b> {'khỏi' if out else 'vào'} quỹ chờ đầu tư"
                + (f" {esc(code)}" if code else "") + ("" if out else "\n<i>Là để dành, không tính là khoản chi</i>"))
    if job == "chuyen_tk":
        main = main_name()
        src = a.get("tu") or main or "?"
        return (f"🔁 Chuyển <b>{money}</b> từ <b>{esc(src)}</b> sang <b>{esc(a['den'])}</b>"
                "\n<i>Chuyển giữa tài khoản của bạn, không tính là khoản chi</i>")
    if job == "cho_vay":
        return f"🤝 Cho <b>{esc(a['ten'])}</b> vay <b>{money}</b>\n<i>Ghi là khoản phải thu (tài sản), không tính là chi</i>"
    if job == "ngan_sach":
        return f"🎯 Ngân sách <b>{esc(a['nhom'])}</b>: <b>{money}</b> mỗi tháng"
    if job == "ngay_luong":
        return f"💼 Lương về ngày <b>{int(a['ngay_luong'])}</b> hằng tháng, khoảng <b>{money}</b>"
    return known(a)


def fund_code():
    try:
        return ct.dautu().config().get("ma")
    except Exception:
        return None


def big_side_buy(a):
    """Mua quỹ chờ một khoản lớn (từ 3 lần tiền góp mỗi tháng): gợi ý rải dần sang quỹ chính."""
    try:
        dt = ct.dautu()
        cfg = dt.config()
        side = dt.side(cfg)
        if a["viec"] != "quy" or a.get("chieu") == "hoan_doi" or not side or (a.get("ma") or "").upper() != side["ma"]:
            return None
        monthly = dt.total_of(cfg, dt.ym_of(ct.today()))
        return cfg["ma"] if monthly and a.get("tien", 0) >= 3 * monthly else None
    except Exception as e:
        print(f"[lỗi] xét khoản mua lớn: {e!r}", file=sys.stderr)
        return None


def money_move(a):
    """Tiền của việc này đi ra (âm) hay về (dương) tài khoản chính bao nhiêu; 0 nếu không liên quan."""
    job = a["viec"]
    if job == "du_phong" and a.get("tien"):
        return a["tien"] if a.get("chieu") == "rut" else -a["tien"]
    if job in ("tiet_kiem", "cho_vay", "vang") and a.get("tien"):
        return -a["tien"]
    if job == "quy_cho" and a.get("tien"):
        return a["tien"] if a.get("chieu") == "rut" else -a["tien"]
    if job == "co_phieu" and a.get("sl") and a.get("gia"):
        if ct.taisan().broker_cash(ct.taisan().load()):
            return 0  # tiền đi, về tài khoản chứng khoán
        value = a["sl"] * price_dong(a["gia"])
        return value if a.get("chieu") == "ban" else -value
    return 0


def source(a):
    """(dòng nguồn tiền trên thẻ, nhãn nút đổi) hoặc None nếu chưa có tài khoản chính hoặc việc không đụng tiền."""
    delta = money_move(a)
    if not delta:
        return None
    try:
        ts = ct.taisan()
        main = ts.main_account()
        if not main:
            return None
        name, left = html.escape(main["ten"]), ts.main_balance(main)
    except Exception as e:
        print(f"[lỗi] tài khoản chính: {e!r}", file=sys.stderr)
        return None
    if a.get("san"):
        return (f"🏦 Tiền có sẵn, không {'cộng vào' if delta > 0 else 'trừ'} {name}",
                f"🔁 {'Về' if delta > 0 else 'Lấy từ'} {main['ten'][:20]}")
    line = (f"🏦 Tiền về <b>{name}</b>: còn ~{ts.short(left + delta)}" if delta > 0 else
            f"🏦 Tiền từ <b>{name}</b>: còn ~{ts.short(left + delta)} sau khi chuyển")
    return line, ("🔁 Không cộng vào tài khoản nào" if delta > 0 else "🔁 Tiền có sẵn, không trừ")


def card(a, chat, cid=None):
    """Thẻ "Mình hiểu là…": lưu việc, chờ bấm ✅ mới ghi."""
    cid = cid or kho.command("INCR", K_CARD_ID)
    kho.put(f"{K_CARD}{cid}", a, CARD_SECONDS)
    rows = [[("✅ Đúng, ghi lại", f"y:ok:{cid}"), ("✏️ Sửa", f"y:sua:{cid}"), ("❌ Thôi", f"y:huy:{cid}")]]
    main = big_side_buy(a)
    if main:
        rows.insert(1, [(f"🔁 Ghi và rải 80% sang {main} trong 3 tháng", f"y:ok:{cid}:rai")])
    text = describe(a)
    src = source(a)
    if src:
        text += "\n" + src[0]
        rows.insert(1, [(src[1], f"y:nguon:{cid}")])
    if a["viec"] == "tai_khoan" and not a.get("chinh") and no_main():
        rows.insert(1, [("✅ Ghi, là tài khoản chính (lương về, hay tiêu)", f"y:ok:{cid}:chinh")])
    head = "📷 Đọc từ ảnh, kiểm tra lại giúp mình:" if a.get("_anh") else "Mình hiểu là:"
    return f"{head}\n{text}", rows


def main_name():
    try:
        main = ct.taisan().main_account()
        return main["ten"] if main else None
    except Exception as e:
        print(f"[lỗi] tài khoản chính: {e!r}", file=sys.stderr)
        return None


def no_main():
    try:
        return ct.taisan().main_account() is None
    except Exception:
        return False


def advance(a, chat, now):
    """Bước kế tiếp của một việc: hỏi trường còn thiếu, hoặc hiện thẻ xác nhận, hoặc làm luôn."""
    f = missing(a)
    if f:
        kho.put(chat_key(chat), {"viec": a, "hoi": f["ten"]}, STATE_SECONDS)
        return question(a, f)
    forget(chat)
    if JOBS[a["viec"]]["xac_nhan"]:
        return card(a, chat)
    return run(a, now, chat)


def start(job, chat, now, **preset):
    """Bắt đầu một việc từ nút bấm: bot hỏi lần lượt từng trường."""
    return advance({"viec": job, **preset}, chat, now)


# ---- Thực hiện ---------------------------------------------------------------------------

def dated(a, text, day):
    """Thêm ngày vào đầu câu ghi sổ nếu việc có ngày khác hôm nay."""
    when = a.get("ngay")
    if when and when != day.isoformat() and when < day.isoformat():
        return f"{when[8:]}/{when[5:7]} {text}"
    return text


def run(a, now, chat, option=None):
    """Thực hiện một việc đã đủ trường; trả câu trả lời (chữ, hoặc (chữ, nút))."""
    job, day = a["viec"], now.date()
    ts = ct.taisan()
    if job == "thu":
        return ct.record_text("+ " + dated(a, f"{a['tien']}đ {a.get('ghi_chu') or 'thu nhập'}", day), now)
    if job == "tra_no":
        return ct.record_text(dated(a, f"{a['tien']}đ trả nợ {a['ten']}", day), now)
    paid = not a.get("san")  # tiền đi từ (về) tài khoản chính, nếu có
    if job == "du_phong":
        note = ct.duphong().change(-a["tien"] if a.get("chieu") == "rut" else a["tien"], day, from_main=paid)
        return note, [[("🛟 Quỹ dự phòng", "dp:xem"), ct.BACK]]
    if job == "tiet_kiem":
        data = ts.load()
        start_day = date.fromisoformat(a["ngay"]) if a.get("ngay") else day
        note = ts.add_saving_item(data, a["ten"], a["tien"], a["lai"], int(a.get("ky") or 0), start_day)
        moved = ts.move_main(data, -a["tien"], f"sổ tiết kiệm {a['ten']}", day) if paid else None
        ts.save(data)
        return note + (f"\n{moved}" if moved else ""), [[("💼 Tài sản", "m:ts"), ct.BACK]]
    if job in ("tai_khoan", "cho_vay"):
        data = ts.load()
        name = a["ten"] if job == "tai_khoan" else f"Cho {a['ten']} vay"
        note = ts.add_simple(data, "tien" if job == "tai_khoan" else "khac", [name, f"{a['tien']}đ"])
        if not note:
            return "⚠️ Chưa ghi được, thử lại với tên ngắn hơn nhé"
        if job == "cho_vay" and paid:
            moved = ts.move_main(data, -a["tien"], f"cho {a['ten']} vay", day)
            note += f"\n{moved}" if moved else ""
        if job == "tai_khoan" and (a.get("chinh") or option == "chinh"):
            item = next(it for it in data["items"] if it["loai"] == "tien" and ts.same_name(it["ten"], name[:30]))
            if ts.can_be_main(item) and not item.get("chinh"):
                ts.set_main(data, item)
                note += ("\n🏦 Đã đặt làm tài khoản chính: từ giờ bot tự cộng thu, trừ chi, trừ tiền nạp quỹ, góp đầu "
                         "tư… vào đây")
        ts.save(data)
        return note, [[("🏦 Tài khoản chính", "ts:chinh"), ("💼 Tài sản", "m:ts"), ct.BACK]]
    if job == "vang":
        args = [a["loai"], num(a["chi"]), "chi"]
        if a.get("tien"):
            args.append(f"{a['tien'] / (a['chi'] / 10) / 1e6:.2f}".replace(".", ","))
        note = ts.add_gold(args)
        if note and a.get("tien") and paid:
            data = ts.load()
            moved = ts.move_main(data, -a["tien"], f"mua {num(a['chi'])} chỉ vàng", day)
            if moved:
                ts.save(data)
                note += f"\n{moved}"
        return (note or "⚠️ Chưa ghi được số vàng này", [[("💼 Tài sản", "m:ts"), ct.BACK]])
    if job == "co_phieu":
        return run_stock(a, now)
    if job == "quy_cho":
        dt = ct.dautu()
        cfg = dt.config()
        if not dt.active(cfg):
            return "Chưa bật đầu tư quỹ định kỳ nên chưa có quỹ chờ.", [[("📈 Đầu tư", "dt:xem"), ct.BACK]]
        notes = []
        if a.get("chieu") == "rut":
            taken, left = dt.take_money(cfg, a["tien"], to_main=paid, notes=notes)
            head = f"✅ Đã rút {ct.vnd(taken)} khỏi quỹ chờ {cfg['ma']}, còn {ct.vnd(left)}"
        else:
            left = dt.add_money(cfg, a["tien"], dt.current_period(cfg), from_main=paid, notes=notes)
            dt.save(cfg)
            head = f"✅ Đã để {ct.vnd(a['tien'])} vào quỹ chờ {cfg['ma']}: {ct.vnd(left)}"
        return "\n".join([head] + notes), [[("📈 Đầu tư", "dt:xem"), ct.BACK]]
    if job == "chuyen_tk":
        return run_transfer(a, now, chat)
    if job == "quy":
        return run_fund(a, now, option)
    if job == "sua_ccq":
        return ct.dautu().fix_units(f"{num(a['ccq'])} {a.get('ma') or ''}".strip()), [[("📈 Đầu tư", "dt:xem")]]
    if job == "no_moi":
        due = int(a["ngay_tra"]) if a.get("ngay_tra") and 1 <= a["ngay_tra"] <= 31 else None
        info = {"ten": a["ten"][:30], "con": a["tien"], "thang": a.get("moi_thang"),
                "lai": float(a["lai"]) if a.get("lai") is not None else None, "ngay_tra": due}
        return ct.sono().declare_info(info, day), [[("💳 Sổ nợ", "no:xem"), ct.BACK]]
    if job == "ngan_sach":
        return ct.ngansach([*str(a["nhom"]).split(), str(a["tien"])])
    if job == "ngay_luong":
        return ts.luong([str(int(a["ngay_luong"])), f"{a['tien']}đ"])
    return "⚠️ Việc này bot chưa làm được"


def run_transfer(a, now, chat):
    """Chuyển giữa hai tài khoản tiền của mình: trừ nơi đi, cộng nơi đến (tài khoản đến chưa có thì tạo)."""
    ts, day = ct.taisan(), now.date()
    data = ts.load()
    src = ts.find_account(data, a["tu"]) if a.get("tu") else ts.main_account(data)
    if src is None:
        if a.get("tu"):
            return f"Không thấy tài khoản «{html.escape(a['tu'])}» trong 💼 Tài sản. Thêm trước: «tài khoản {html.escape(a['tu'])} còn 10tr»"
        f = field("chuyen_tk", "tu")  # chưa có tài khoản chính: hỏi tiền đi từ đâu
        kho.put(chat_key(chat), {"viec": a, "hoi": "tu"}, STATE_SECONDS)
        return question(a, f)
    dst = ts.find_account(data, a["den"])
    if dst is src:
        return "Tài khoản đi và đến là một, không có gì để chuyển"
    if dst and (dst.get("duphong") or dst.get("dautu")):  # vào quỹ dự phòng, quỹ chờ: làm như việc riêng
        job = "du_phong" if dst.get("duphong") else "quy_cho"
        if src.get("chinh"):
            return run({"viec": job, "tien": a["tien"], "chieu": "nap"}, now, chat)
        reply = run({"viec": job, "tien": a["tien"], "chieu": "nap", "san": True}, now, chat)
        data = ts.load()
        src = ts.find_account(data, a["tu"])
        src["tien"] -= a["tien"]
        ts.save(data)
        text, rows = reply if isinstance(reply, tuple) else (reply, None)
        return text + f"\n🏦 {html.escape(src['ten'])} còn {ct.vnd(src['tien'])}", rows
    created = dst is None
    if created:
        dst = {"id": ts.new_id(data), "loai": "tien", "ten": a["den"][:30], "tien": 0, "ngay": day.isoformat()}
        data["items"].append(dst)
    lines = [f"✅ Đã chuyển {ct.vnd(a['tien'])} từ {html.escape(src['ten'])} sang {html.escape(dst['ten'])}"
             + (" (tài khoản mới)" if created else "")]
    for it, delta in ((src, -a["tien"]), (dst, a["tien"])):
        if it.get("chinh"):
            lines.append(ts.move_main(data, delta, f"{'sang ' + dst['ten'] if delta < 0 else 'từ ' + src['ten']}", day))
        else:
            it["tien"] += delta
            it["ngay"] = day.isoformat()
            lines.append(f"🏦 {html.escape(it['ten'])}: {ct.vnd(it['tien'])}")
    ts.save(data)
    return "\n".join(lines + ["<i>Chuyển giữa tài khoản của bạn, không tính là khoản chi</i>"]), [
        [("💼 Tài sản", "m:ts"), ct.BACK]]


def run_stock(a, now):
    ts = ct.taisan()
    code, qty, price = a["ma"].upper(), int(a["sl"]), int(round(price_dong(a["gia"])))
    if a["chieu"] == "ban" and a.get("gia_von"):
        data = ts.load()
        if not any(it["loai"] in ("cp", "etf") and it["ma"] == code for it in data["items"]):
            # chưa khai báo mã này: thêm theo giá vốn rồi mới bán, để tính được lãi lỗ
            note = ts.add_holding(data, "cp", [code, str(qty), str(int(round(price_dong(a["gia_von"]))))])
            if not note or not note.startswith("✅"):
                return note or f"⚠️ Chưa ghi được mã {html.escape(code)}"
            ts.save(data)
    reply = ts.trade(f"{'bán' if a['chieu'] == 'ban' else 'mua'} {qty} {code} giá {price}", now, pay_main=not a.get("san"))
    return reply or f"⚠️ Không thấy mã {html.escape(code)} trên sàn, kiểm tra lại mã cổ phiếu nhé"


def run_fund(a, now, option=None):
    dt = ct.dautu()
    cfg = dt.config()
    if not dt.active(cfg):
        return ("Chưa bật đầu tư quỹ định kỳ nên mình chưa ghi được lệnh quỹ. Bấm nút để xem cách bật.",
                [[("📈 Đầu tư", "dt:xem"), ct.BACK]])
    side = dt.side(cfg)
    code = (a.get("ma") or cfg["ma"]).upper()
    fund = side if side and code == side["ma"] else None
    swap = a.get("chieu") == "hoan_doi"
    if swap and not side:
        return "Quỹ chờ đang là tiền gửi nên không có gì để hoán đổi."
    if not swap and code != cfg["ma"] and not fund:
        return (f"Bot đang theo dõi {cfg['ma']}" + (f" và {side['ma']}" if side else "")
                + f", chưa theo dõi {html.escape(code)}. Quỹ khác thì khai báo ở 💼 Tài sản.")
    when = ""
    if a.get("ngay"):
        d = date.fromisoformat(a["ngay"])
        when = f"{d.day}/{d.month}"
    if a.get("sau_gio"):
        when += " sau 14h40"
    spec = dt.order_spec(cfg, when, now, side if swap else fund)
    if isinstance(spec, str):
        return spec
    day, trading, ym = spec
    if swap:
        return dt.record_switch(a["ccq"], trading, now, ym, day), [[("📈 Đầu tư", "dt:xem")]]
    if option == "rai" and fund:
        text = f"{a['tien']}đ {when}".strip()
        return dt.restructure(cfg, text, ct.parse_amount(text), now), [[("📈 Đầu tư", "dt:xem")]]
    return dt.record_order(a["tien"], trading, now, ym, day, fund=fund), [[("📈 Đầu tư", "dt:xem"), ("🧾 Lệnh", "dt:ls")]]


def screen(a, text, now):
    """Mở màn hình theo việc "xem"."""
    day, name = now.date(), a.get("man")
    menu = ct.menu()
    if name == "chi_tieu":
        return ct.report(a.get("ky") or "thang", day)[0], ct.REPORT_BUTTONS
    direct = {"tong_quan": "home", "tai_san": "ts", "no": "no", "ke_hoach": "kh"}
    if name in direct:
        return menu.screen(direct[name], day)
    makers = {
        "chia_luong": lambda: ct.kehoach().plan(day), "du_phong": lambda: ct.duphong().text(day),
        "dau_tu": lambda: ct.dautu().view(), "tiet_kiem": lambda: ct.tietkiem().view(day),
        "suc_khoe": lambda: ct.taisan().health(day), "lich_su": lambda: ct.lichsu([]),
        "bieu_do": lambda: ct.phantich().chart_reply("thang", day), "du_bao": lambda: ct.phantich().dubao([]),
        "ngan_sach": lambda: ct.ngansach([]), "huong_dan": lambda: menu.guide()}
    return makers.get(name, lambda: menu.screen("home", day))()


def unsure(text, down=False):
    """Không hiểu (hoặc AI bận): có số tiền thì hỏi có phải khoản chi không; không thì gợi ý cách nhắn."""
    why = "AI đang bận nên mình chưa đọc được câu này" if down else "Mình chưa rõ câu này là việc gì"
    quoted = html.escape(text.strip()[:80])
    if ct.parse_amount(text):
        cid = kho.command("INCR", K_CARD_ID)
        kho.put(f"{K_CARD}{cid}", {"viec": "_chi", "cau": text.strip()[:300]}, CARD_SECONDS)
        return (f"🤔 {why}: «{quoted}»\nNếu là một khoản chi thì bấm nút dưới. Việc khác (chuyển tiền, tài sản, nợ…) "
                "thì bấm ➕ Thêm hoặc nhắn lại rõ hơn.",
                [[("💸 Ghi là khoản chi", f"y:chi:{cid}"), ("❌ Không ghi", f"y:huy:{cid}")],
                 [("➕ Thêm tài sản, nợ", "y:them"), ct.BACK]])
    return (f"🤔 {why}: «{quoted}»\nBạn cứ nhắn câu thường, ví dụ:\n{EXAMPLES}\nHoặc mở menu để bấm nút.",
            [[("➕ Thêm tài sản, nợ", "y:them"), ("🏠 Menu", "m:home")]])


def handle(a, text, now, chat):
    """Xử lý một việc AI vừa hiểu. Trả câu trả lời; None nếu là khoản chi thường (ghi như cũ)."""
    job = a["viec"]
    if job == "chi":
        if ct.parse_amount(text):
            remember_plain(text)
            return None
        if a.get("tien"):
            return ct.record_text(f"{a['tien']}đ {a.get('ghi_chu') or 'khoản chi'}", now)
        return unsure(text)
    if job == "tra_no" and a.get("ten") and ct.parse_amount(text):
        remember_plain(text)  # câu trả nợ đủ ý: ghi nguyên câu như trước (sổ nợ tự trừ), lần sau khỏi hỏi AI
        return None
    if job == "hoi":
        return ct.phantich().hoi(text, now.date())
    if job == "xem":
        return screen(a, text, now)
    if job == "khong_tieu":
        day = now.date() - timedelta(days=1 if a.get("ngay") == "homqua" else 0)
        return ct.tietkiem().mark_no_spend(day.isoformat(), now.date())
    if job == "xoa_cuoi":
        return ct.xoa_cuoi([])
    if job == "khac":
        return unsure(text)
    return advance(a, chat, now)


NO_SPEND = re.compile(r"(?<!\w)(?:khong|ko|k|chua) (?:tieu|chi|mua)(?: gi| dong nao| xu nao)?(?: ca| het)?(?!\w)")


def quick(text, now):
    """Việc hiểu được bằng luật, không cần AI: "hôm nay không tiêu gì", "hôm qua ko tiêu". None nếu không phải."""
    bare = ct.plain(text.strip())
    if len(bare) <= 40 and not ct.parse_amount(text) and NO_SPEND.search(bare):
        day = now.date() - timedelta(days=1 if "hom qua" in bare else 0)
        return ct.tietkiem().mark_no_spend(day.isoformat(), now.date())
    return None


def understand(text, now, chat, question=False):
    """Hiểu một tin tự do. Trả câu trả lời; None nếu là khoản chi thường (để ghi như cũ). question: tin là câu hỏi,
    AI bận thì trả lời bằng sổ chi tiêu như trước."""
    try:
        a = ask_ai(text, now.date())
    except Exception as e:
        print(f"[lỗi] AI hiểu câu: {e!r}", file=sys.stderr)
        if question:
            return ct.phantich().hoi(text, now.date())
        if ct.parse_amount(text) and re.match(r"tra (?:no|gop|tien)(?!\w)", ct.plain(text.strip())):
            return None  # "trả nợ chú Tư 5tr": ghi như trước, sổ nợ tự trừ
        return unsure(text, down=True)
    return handle(a, text, now, chat)


# ---- Trả lời câu bot đang hỏi dở ---------------------------------------------------------

FILLER = {"khoang", "la", "tam", "het", "tong", "gan", "duoc", "co", "thoi", "a", "nhe", "da"}


def only_filler(rest):
    return all(w in FILLER for w in ct.plain(re.sub(r"[^\w\s]", " ", rest)).split())


def parse_value(f, text):
    """Đọc câu trả lời ngắn cho trường đang hỏi bằng code (không cần AI); None nếu không đọc được."""
    t = text.strip()
    if not t or "\n" in t or len(t) > 60:
        return None
    bare = ct.plain(t)
    for value, label in choices(f):
        if bare in (ct.plain(str(label)), ct.plain(str(value))):
            return value
    kind = f["kieu"]
    if kind == "tien":
        found = ct.parse_amount(t)
        if found and only_filler(t[:found[1]] + " " + t[found[2]:]):
            return int(found[0])
        return None
    if kind == "so":
        m = re.fullmatch(r"(\d+(?:[.,]\d+)?)\s*(%|chi|luong|cay|thang|cp|co phieu|ccq)?(?:\s*/\s*nam| mot nam| moi nam)?", bare)
        if not m:
            return None
        x = float(m[1].replace(",", "."))
        return x * 10 if m[2] in ("luong", "cay") and f["ten"] == "chi" else x
    if kind == "chu":
        if ct.parse_amount(t) or t.endswith("?") or len(t) > 40:
            return None  # có số tiền hay là câu hỏi: không phải tên
        return t.upper() if f["ten"] == "ma" else t
    if kind == "ngay":
        when, _ = ct.parse_date(t, ct.today())
        return when.isoformat() if when != ct.today() or "hom nay" in bare else None
    return None


def on_reply(text, now, chat):
    """Tin nhắn khi bot đang hỏi dở hoặc đang chờ lời sửa. Trả câu trả lời; None nếu không có việc dở hoặc tin là
    một khoản chi thường (ghi như cũ)."""
    st = state(chat)
    if not st:
        return None
    if "\n" in text.strip():  # nhiều dòng là nhiều khoản chi: bỏ việc đang dở, ghi như thường
        forget(chat)
        return None
    a = st["viec"]
    f = None
    if st.get("hoi"):
        f = missing(a) if a["viec"] == "quy" else field(a["viec"], st["hoi"])
        v = parse_value(f, text) if f else None
        if v is not None:
            a[f["ten"]] = v
            return advance(a, chat, now)
    if not ct.ai_key():
        forget(chat)
        return None
    try:
        b = ask_ai(text, now.date(), context=(a, f["hoi"] if f else None))
    except Exception as e:
        print(f"[lỗi] AI hiểu câu trả lời: {e!r}", file=sys.stderr)
        if f:
            text_q, rows = question(a, f)
            return "⚠️ Mình chưa đọc được câu trả lời (AI đang bận), bạn trả lời ngắn giúp nhé.\n" + text_q, rows
        return "⚠️ AI đang bận nên chưa sửa được. Bấm ✅ trên thẻ nếu vẫn đúng, hoặc nhắn lại sau."
    if b["viec"] == a["viec"]:
        if st.get("the"):
            kho.delete(f"{K_CARD}{st['the']}")  # thẻ cũ thay bằng thẻ đã sửa
        return advance({**a, **b}, chat, now)
    forget(chat)
    return handle(b, text, now, chat)


# ---- Ảnh, nút bấm, thử câu ---------------------------------------------------------------

PHOTO_JOBS = ("quy", "vang", "co_phieu")


def from_photo(raw, chat, now):
    """Việc AI đọc được từ ảnh (lệnh quỹ, đơn mua vàng, kết quả lệnh cổ phiếu): hỏi trường thiếu rồi xin xác nhận.
    None nếu không dùng được."""
    a = clean(raw) if isinstance(raw, dict) else {"viec": "khac"}
    if a["viec"] not in PHOTO_JOBS:
        return None
    a["_anh"] = True
    return advance(a, chat, now)


def on_button(arg, message, now):
    """Nút "y:...": ok/sua/huy thẻ xác nhận, tl/bo trả lời câu đang hỏi, them bắt đầu thêm bằng nút."""
    kind, _, rest = arg.partition(":")
    chat = (message.get("chat") or {}).get("id")
    if kind == "them":
        if not rest:
            return None, ("send", lambda: ("➕ <b>Thêm gì?</b> Bấm một loại, bot sẽ hỏi từng bước. Hoặc cứ nhắn câu "
                                           "thường, ví dụ «gửi tiết kiệm VCB 50tr lãi 4,7% 6 tháng».", ADD_MENU))
        job, _, preset = rest.partition(":")
        if job not in JOBS:
            return None, None
        extra = {"ma": preset.upper()} if preset and job == "sua_ccq" else {}
        if preset == "chinh" and job == "tai_khoan":
            main = ct.taisan().main_account()
            extra = {"ten": main["ten"], "chinh": True} if main else {"chinh": True}
        return None, ("send", lambda: start(job, chat, now, **extra))
    if kind == "thoi":
        forget(chat)
        return "Đã bỏ", ("edit", lambda: "Đã bỏ, không ghi gì.")
    if kind in ("tl", "bo"):
        st = state(chat)
        name, _, index = rest.partition(":")
        if not st or st.get("hoi") != name:
            return "Câu hỏi này đã cũ", None
        a = st["viec"]
        f = missing(a) if a["viec"] == "quy" else field(a["viec"], name)
        if kind == "bo":
            a.setdefault("_bo", []).append(name)
        else:
            opts = choices(f)
            if not index.isdigit() or int(index) >= len(opts):
                return "Lựa chọn này đã cũ", None
            a[name] = opts[int(index)][0]
        return None, ("edit", lambda: advance(a, chat, now))
    cid, _, option = rest.partition(":")
    a = kho.get(f"{K_CARD}{cid}")
    if a is None:
        return "Thẻ này đã xử lý hoặc hết hạn", None
    if kind == "huy":
        kho.delete(f"{K_CARD}{cid}")
        return "Đã bỏ", ("edit", lambda: "Đã bỏ, không ghi gì.")
    if kind == "chi" and a.get("viec") == "_chi":
        kho.delete(f"{K_CARD}{cid}")
        return "Đã ghi", ("edit", lambda: ct.record_text(a["cau"], now))
    if kind == "nguon":
        a["san"] = not a.get("san")
        return None, ("edit", lambda: card(a, chat, cid))
    if kind == "sua":
        kho.put(chat_key(chat), {"viec": a, "sua": True, "the": cid}, STATE_SECONDS)
        return None, ("send", lambda: "✏️ Sửa chỗ nào? Nhắn phần đúng, ví dụ «giá 2tr5», «6 tháng» hay «ngày 9/11».")
    if kind == "ok" and a.get("viec") in JOBS:
        kho.delete(f"{K_CARD}{cid}")
        forget(chat)
        return "Đang ghi…", ("edit", lambda: run(a, now, chat, option or None))
    return None, None


def try_text(text, day):
    """Thử hiểu một câu mà không ghi gì (trang tình trạng ?hieu=...): cho biết bot sẽ làm gì với câu đó."""
    text = (text or "").strip()[:200]
    if not text:
        return "Thêm câu cần thử: ?hieu=mua 2 chỉ vàng nhẫn hết 27tr"
    used = kho.command("INCR", f"chitieu:hieu:thu:{day}")
    kho.command("EXPIRE", f"chitieu:hieu:thu:{day}", 2 * 86400)
    if used > TRY_LIMIT:
        return f"Hôm nay đã thử {TRY_LIMIT} câu, mai thử tiếp."
    lines = [f"Câu: {text}"]
    if ct.phantich().is_question(text) and not beyond_spending(text):
        return "\n".join(lines + ["→ Câu hỏi về chi tiêu: trả lời bằng sổ chi tiêu như trước (không qua bộ hiểu câu)."])
    if not wants(text):
        return "\n".join(lines + ["→ Khoản chi/thu thường: ghi ngay như trước (không hỏi AI)."])
    try:
        system = prompt(day, personal=False)
        out, model = ct.ai_chat(system, text, timeout=15, budget=25)
    except Exception as e:
        return "\n".join(lines + [f"→ AI lỗi: {e}"])
    a = clean(ct.first_json(out) or {}, text)
    lines += [f"AI ({model}) trả: {out.strip()[:300]}", f"Việc sau khi kiểm tra: {a}"]
    if a["viec"] in JOBS:
        f = missing(a)
        lines.append("→ Bot hỏi tiếp: " + f["hoi"] if f else "→ " + (
            "Thẻ xác nhận: " if JOBS[a["viec"]]["xac_nhan"] else "Làm luôn: ") + re.sub(r"<[^>]+>", "", describe(a)))
    else:
        lines.append({"chi": "→ Ghi như khoản chi thường.", "hoi": "→ Trả lời bằng sổ chi tiêu.",
                      "khac": "→ Bot báo chưa hiểu và gợi ý cách nhắn."}.get(a["viec"], f"→ Làm luôn: {a['viec']}"))
    return "\n".join(lines)
