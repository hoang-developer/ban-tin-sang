"""Một định nghĩa dòng tiền cho mọi màn hình: khoản trong sổ là thu, chi, hay trả gốc nợ. Thuần.

Trước đây mỗi màn hình tự lọc theo cách riêng (27 chỗ so nhóm với Thu nhập): báo cáo, ngân sách tính trả nợ là chi, còn kế
hoạch và màn Hôm nay thì không, nên quẹt thẻ 10tr rồi trả thẻ 10tr thì /thang báo chi 20tr còn /menu báo 10tr.

- Thu: nhóm Thu nhập.
- Trả gốc nợ: khoản gắn với một khoản nợ (trường "no"), thuộc nhóm Trả nợ, hoặc ghi chú là trả nợ, đóng thẻ, trả góp
  (classify.is_debt_payment). Thẻ tín dụng tính là chi lúc quẹt, nên lúc trả thẻ không tính là chi lần nữa.
- Chi: còn lại. Hoàn tiền là khoản chi số âm ở nhóm gốc (e["hoan"]), nên cộng thẳng là ra chi thật.
"""
from domain.chitieu import classify
from domain.chitieu.kinds import INCOME

THU, CHI, TRA_GOC = "thu", "chi", "tra_goc"


def debt_group_of(cfg):
    """Mã nhóm Trả nợ của người dùng (nhóm tự tạo tên "Trả nợ"), None nếu chưa có."""
    return classify.find_group("trả nợ", cfg or {})


def kind(e, debt_group=None):
    """"thu" | "chi" | "tra_goc" của một khoản trong sổ."""
    if e["nhom"] == INCOME:
        return THU
    if e.get("no") or (debt_group and e["nhom"] == debt_group) or classify.is_debt_payment(e.get("ghichu")):
        return TRA_GOC
    return CHI


def spending(entries, debt_group=None):
    """Các khoản chi thật (không thu, không trả gốc nợ); hoàn tiền là khoản số âm."""
    return [e for e in entries if kind(e, debt_group) == CHI]


def spent(entries, debt_group=None):
    """Tổng chi thật."""
    return sum(e["tien"] for e in spending(entries, debt_group))


def income(entries):
    """Tổng thu."""
    return sum(e["tien"] for e in entries if e["nhom"] == INCOME)


def repaid(entries, debt_group=None):
    """Tổng trả gốc nợ (không tính là chi)."""
    return sum(e["tien"] for e in entries if kind(e, debt_group) == TRA_GOC)
