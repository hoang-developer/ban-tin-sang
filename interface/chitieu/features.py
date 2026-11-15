"""Truy cập các chức năng khác của bot chi tiêu khi cần (nạp muộn để né import vòng): mỗi hàm trả module giao diện của
chức năng đó."""


def taisan():
    from interface.taisan import assets as module  # tài sản, mua bán cổ phiếu, khám sức khỏe tài chính
    return module

def duphong():
    from interface.duphong import reserve as module  # quỹ dự phòng
    return module

def phantich():
    from interface.phantich import analysis as module  # dự báo, hỏi bằng câu thường, biểu đồ, nhận xét
    return module

def sono():
    from interface.no import debt as module  # sổ nợ
    return module

def kehoach():
    from interface.kehoach import plan as module  # lộ trình tài chính, chia lương
    return module

def menu():
    from interface.menu import screens as module  # menu nút bấm, tổng quan, hướng dẫn
    return module

def dautu():
    from interface.dautu import fund as module  # đầu tư quỹ mở hằng tháng (Value Averaging)
    return module

def tietkiem():
    from interface.tietkiem import progress as module  # tiết kiệm từ khi dùng bot, chuỗi ngày ghi chép
    return module

def troly():
    import troly as module  # hiểu câu nói thường, hỏi lại khi thiếu, thẻ xác nhận
    return module
