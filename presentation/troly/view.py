"""Chữ và nút của trợ lý: ví dụ câu nói, menu ➕ Thêm."""
from presentation.chitieu.view import BACK

# Thêm bằng nút: các loại hỏi được từng trường. Cổ phiếu, quỹ, tiền số có sẵn thì vẫn khai báo bằng /taisan.
ADD_MENU = [[("🏦 Tài khoản, ví", "y:them:tai_khoan"), ("🐷 Sổ tiết kiệm", "y:them:tiet_kiem")],
            [("🥇 Vàng", "y:them:vang"), ("🤝 Cho vay", "y:them:cho_vay")],
            [("💳 Khoản nợ", "y:them:no_moi"), ("📈 Mua bán cổ phiếu", "y:them:co_phieu")],
            [("🔁 Chuyển giữa tài khoản", "y:them:chuyen_tk"), ("🏦 Tài khoản chính", "ts:chinh")],
            [("📖 Cổ phiếu, quỹ, tiền số có sẵn", "ts:hd"), BACK]]
EXAMPLES = ("• mua 2 chỉ vàng nhẫn hết 27tr\n• gửi tiết kiệm VCB 50tr lãi 4,7% 6 tháng\n• vay anh Nam 10tr, mỗi tháng trả "
            "2tr\n• nạp 2tr vào quỹ dự phòng\n• tài khoản Techcombank còn 14tr\n• tôi còn nợ bao nhiêu?")
