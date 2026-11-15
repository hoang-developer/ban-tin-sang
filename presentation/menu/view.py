"""Chữ và nút của menu bot chi tiêu: 4 nút chính, lời chào, cách ghi, mọi lệnh, màn hình hỏi, cài đặt."""
from presentation.chitieu.view import BACK

BOTTOM = {"🏠 Hôm nay": "home", "💰 Tiền của tôi": "tien", "🎯 Kế hoạch": "kh", "💬 Hỏi": "hoi"}
OLD_BOTTOM = {"🏠 Menu": "home", "📊 Chi tiêu": "chi", "💼 Tài sản": "tien"}  # hàng nút cũ: vẫn chạy, gửi hàng mới
NAV = [("🏠 Hôm nay", "m:home"), ("💰 Tiền của tôi", "m:tien"), ("🎯 Kế hoạch", "m:kh"), ("💬 Hỏi", "m:hoi")]
MAIN = [NAV[:2], NAV[2:], [("➕ Thêm", "y:them"), ("📝 Cách ghi", "m:ghi"), ("⚙️ Cài đặt", "m:cd")]]
GREETING = ("👋 <b>Bot ghi chi tiêu và xây tài sản</b>\n"
            "Nhắn số tiền kèm nội dung để ghi, ví dụ: <b>cà phê 35k</b>. Việc khác cứ nhắn câu thường (mua vàng, gửi tiết "
            "kiệm, vay, trả nợ, hỏi còn nợ bao nhiêu…), bot hỏi lại nếu thiếu và xin xác nhận trước khi ghi. Gửi ảnh hóa "
            "đơn, chuyển khoản, lệnh quỹ, đơn mua vàng cũng được.\nBốn nút dưới ô chat: 🏠 Hôm nay · 💰 Tiền của tôi · "
            "🎯 Kế hoạch · 💬 Hỏi.")
HOW_TO = ("📝 <b>Cách ghi</b>\n"
          "• Nhắn số tiền kèm nội dung: cà phê 35k · đổ xăng 80000 · tiền nhà 5tr (1tr2 là 1.200.000đ)\n"
          "• Khoản thu: + lương 19tr\n"
          "• Ngày khác: hôm qua ăn tối 250k · 02/11 cắt tóc 100k\n"
          "• Tự chọn nhóm: đóng họ 1tr #trả nợ\n"
          "• Nhiều khoản: mỗi khoản một dòng; gõ không dấu cũng được\n"
          "• 📷 Gửi ảnh hóa đơn, màn hình chuyển khoản, lịch sử giao dịch ngân hàng\n"
          "• Trả nợ: trả nợ chú Tư 5tr (tự trừ vào sổ nợ /no)\n"
          "• Mua bán cổ phiếu, ETF: mua 500 E1VFVN30 giá 33,6 · bán 100 FPT giá 120\n"
          "• Hỏi: tháng này ăn uống hết bao nhiêu? · tôi còn nợ bao nhiêu? · quỹ lãi lỗ thế nào?\n"
          "• Việc khác nhắn câu thường, bot hỏi lại nếu thiếu và xin xác nhận trước khi ghi: mua 2 chỉ vàng nhẫn hết 27tr · "
          "gửi tiết kiệm VCB 50tr lãi 4,7% 6 tháng · vay anh Nam 10tr · nạp 2tr vào quỹ dự phòng · tài khoản Techcombank "
          "còn 14tr · chuyển 5tr từ VCB sang MoMo · hôm nay không tiêu gì\n"
          "• 🏦 Chọn tài khoản chính (💼 Tài sản → 🏦): bot tự cộng thu, trừ chi, trừ tiền nạp quỹ, góp đầu tư, trả nợ, "
          "nên luôn biết còn bao nhiêu. Lương về thì bấm ✅ Làm hết theo kế hoạch\n"
          "• 📷 Ảnh lệnh mua quỹ, đơn mua vàng, kết quả bán cổ phiếu: bot đọc rồi hỏi lại trước khi ghi\n"
          "Xếp sai nhóm thì bấm ✏️ Đổi nhóm, lần sau bot tự nhớ. Khoản chưa rõ nhóm thì bot hỏi luôn.\n"
          "Khai báo nhiều thứ một lần: dán nhiều lệnh, mỗi lệnh một dòng.")
GUIDE = ("📖 <b>Mọi lệnh</b> (dễ nhất là bấm /menu)\n"
         "\n📊 <b>Chi tiêu</b>\n"
         "/baocao báo cáo, có nút chọn kỳ · /homnay · /tuan · /thang (/thang 10)\n"
         "/bieudo biểu đồ · /dubao chi hằng ngày còn được tiêu bao nhiêu · /nhanxet nhận xét của AI\n"
         "/tietkiem chi lặt vặt so với trước khi dùng bot, chuỗi ngày ghi chép (/tietkiem khongtieu: hôm nay không "
         "tiêu gì)\n"
         "/hoi hỏi bằng câu thường · /lichsu 10 khoản gần nhất · /xoa xóa khoản vừa ghi\n"
         "/chuaxep xếp nhóm khoản chưa rõ · /xuat file Excel (/xuat 10)\n"
         "\n💼 <b>Tài sản</b>\n"
         "/taisan tài sản ròng, khai báo (/taisan huongdan) · /suckhoe khám sức khỏe tài chính\n"
         "\n💳 <b>Nợ</b>\n"
         "/no sổ nợ: còn bao nhiêu, mỗi tháng trả, bao giờ xong (/no huongdan)\n"
         "\n🎯 <b>Kế hoạch</b>\n"
         "/kehoach lộ trình xây tài sản · /kehoach chia: chia lương tháng này\n"
         "/duphong quỹ dự phòng · /luong ngày nhận lương (/luong 5 19tr)\n"
         "/dautu đầu tư quỹ mở hằng tháng: tháng này nên mua bao nhiêu, nhắc hạn đặt lệnh (/dautu huongdan)\n"
         "\n⚙️ <b>Cài đặt</b>\n"
         "/nhom tự tạo nhóm, thêm từ khóa · /ngansach ngân sách tháng\n"
         "\n" + HOW_TO)
SETTINGS = ("⚙️ <b>Cài đặt</b>\n"
            "Bấm nút để đổi. Gõ lệnh cũng được: /nhom, /ngansach, /luong 5 19tr, /duphong muctieu 6, /dautu gop 4tr, "
            "/dubao nhom ăn uống, đi chợ")


def bottom_keyboard():
    """Hàng nút cố định dưới ô chat (bấm là gửi chữ trên nút)."""
    labels = list(BOTTOM)
    return {"keyboard": [[{"text": x} for x in labels[:2]], [{"text": x} for x in labels[2:]]],
            "resize_keyboard": True, "is_persistent": True,
            "input_field_placeholder": "Nhắn khoản chi, ví dụ: cà phê 35k"}


MONEY_ROWS = [[("🏦 Tài khoản chính", "ts:chinh"), ("🔁 Chuyển tiền", "y:them:chuyen_tk")],
              [("🔄 Đối chiếu tháng", "dc:xem")],
              [("💼 Chi tiết, giá mới", "ts:xem"), ("📊 Biểu đồ", "ts:bd")],
              [("🛟 Quỹ dự phòng", "dp:xem"), ("💳 Sổ nợ", "no:xem")],
              [("📈 Đầu tư quỹ", "dt:xem"), ("🩺 Sức khỏe", "ts:sk")],
              [("➕ Thêm", "y:them"), BACK]]


def gain(rows):
    priced = [r for r in rows if r[4]]
    cost = sum(r[4] for r in priced)
    if not cost:
        return ""
    change = (sum(r[3] for r in priced) - cost) / cost * 100
    if abs(change) < 0.05:
        return " ⚪"
    return f" {'🟢' if change > 0 else '🔴'}{change:+.1f}%".replace(".", ",").replace("-", "−")


QUESTIONS = [("Hôm nay còn được tiêu bao nhiêu?", "tieu"), ("Tháng này tiêu vào đâu?", "thang"),
             ("So với tháng trước thế nào?", "so"), ("Còn nợ bao nhiêu, bao giờ xong?", "no"),
             ("Quỹ đầu tư lãi lỗ thế nào?", "quy"), ("Tài chính của tôi có ổn không?", "sk"),
             ("Nhận xét chi tiêu tháng này", "nx")]
