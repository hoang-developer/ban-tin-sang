"""Chính sách rủi ro khi ghi tiền: một chỗ quyết một việc có tiền được làm ngay, phải hỏi lại bằng thẻ, hay phải xác nhận
hai lần (quyết định A, docs/ke-hoach-tro-ly.md). Thuần: nhận tín hiệu đã đọc sẵn, không gọi AI, không đọc kho.

- GHI_NGAY: khoản chi nhỏ và rõ (một số tiền, không phải dự định/câu hỏi, ngày không ở tương lai), tới QUICK_LIMIT;
  khoản thu gõ "+" (đã rõ chiều); việc AI hiểu không đổi tài sản (thu, trả nợ) cũng tới QUICK_LIMIT. Ghi xong vẫn có
  nút ❌ Xóa.
- HOI_LAI: còn lại đều qua thẻ ("Mình hiểu là…", "Khoản lớn…"): chi trên QUICK_LIMIT, nhiều số tiền trong một dòng
  (không biết số nào là tiền), ngày ở tương lai, dự định/giả định/câu hỏi (domain/chitieu/guard.py), số đọc từ ảnh,
  mọi việc đổi tài sản, nợ, đầu tư (CONFIRM_JOBS).
- XAC_NHAN_KEP: một khoản ghi vào sổ chi/thu từ DOUBLE_LIMIT trở lên (thường là gõ thừa số 0): bấm ✅ hai lần.

Việc chọn ai hiểu câu (luật hay AI, troly.assistant.wants) không nằm ở đây: hiểu bằng đường nào thì kết quả cũng qua
chính sách này trước khi ghi.
"""
from dataclasses import dataclass

from domain.chitieu.parse import parse_date
from domain.chitieu.kinds import INCOME
from domain.common.money import money_count

GHI_NGAY, HOI_LAI, XAC_NHAN_KEP = "ghi_ngay", "hoi_lai", "xac_nhan_kep"
ORDER = (GHI_NGAY, HOI_LAI, XAC_NHAN_KEP)  # mức sau chặt hơn mức trước
LUAT, AI, ANH = "luat", "ai", "anh"  # nguồn: luật của code, AI hiểu câu, AI đọc ảnh
CHI, THU = "chi", "thu"

QUICK_LIMIT = 2_000_000  # khoản chi tới mức này thì ghi ngay
DOUBLE_LIMIT = 50_000_000  # một khoản chi/thu từ mức này: xác nhận hai lần
SIDE_BUY_MONTHS = 3  # mua quỹ chờ từ 3 tháng tiền góp: gợi ý rải dần sang quỹ chính

# Việc của trợ lý đổi tài sản, nợ, đầu tư, ngân sách: luôn qua thẻ (trước là cờ xac_nhan trong JOBS)
CONFIRM_JOBS = frozenset({"du_phong", "tiet_kiem", "tai_khoan", "vang", "co_phieu", "quy", "quy_cho", "chuyen_tk",
                          "ban_vang", "tat_toan", "ban_quy", "thu_no", "xoa_tai_san", "doi_xong", "no_moi", "cho_vay",
                          "ngan_sach", "ngay_luong"})
LEDGER_JOBS = frozenset({"chi", "thu", "tra_no"})  # việc ghi thẳng vào sổ chi/thu


@dataclass(frozen=True)
class Signal:
    """Những gì đã biết về một khoản trước khi ghi."""
    amount: int = 0
    direction: str = CHI  # CHI | THU
    explicit: bool = False  # chiều đã rõ: dòng gõ "+" là thu
    future: bool = False  # ngày sau hôm nay
    many_numbers: bool = False  # nhiều số tiền có đơn vị trong cùng một dòng
    source: str = LUAT
    reason: str = None  # lý do không phải khoản đã xảy ra (guard.skip_reason)
    job: str = None  # việc của trợ lý; None: một dòng sổ chi/thu


def decide(s):
    """GHI_NGAY | HOI_LAI | XAC_NHAN_KEP cho một khoản."""
    if s.job and s.job not in LEDGER_JOBS:
        return HOI_LAI if s.job in CONFIRM_JOBS or s.source == ANH else GHI_NGAY
    if abs(s.amount) >= DOUBLE_LIMIT:
        return XAC_NHAN_KEP
    if s.reason or s.future or s.many_numbers or s.source == ANH:
        return HOI_LAI
    if s.direction == THU and s.explicit:
        return GHI_NGAY
    return GHI_NGAY if s.amount <= QUICK_LIMIT else HOI_LAI


def strictest(levels):
    """Mức chặt nhất trong các mức (một tin nhiều dòng: dòng nào cần hỏi thì cả tin chờ hỏi)."""
    return max(levels, key=ORDER.index, default=GHI_NGAY)


def line_signal(line, day, entry, source=LUAT, reason=None):
    """Tín hiệu của một dòng tin nhắn ghi sổ ("cà phê 35k", "+ lương 20tr", "05/11 tiền nhà 3tr"). entry: khoản đọc
    bằng luật từ dòng đó (chitieu parse_line, theo nhóm của người dùng), None nếu không có số tiền. Khoản thu do luật
    nhận ra (dấu "+" hay từ khóa nhóm Thu nhập như "lương") là chiều đã rõ."""
    if not entry:
        return None
    income = entry["nhom"] == INCOME
    _, rest = parse_date(line.strip().lstrip("+").strip(), day)
    return Signal(amount=abs(entry["tien"]), direction=THU if income else CHI, explicit=income,
                  future=entry["ngay"] > day.isoformat(), many_numbers=money_count(rest) >= 2, source=source,
                  reason=reason)


def text_level(text, day, read, source=LUAT, reason=None):
    """Mức của cả tin (mỗi dòng một khoản): mức chặt nhất của các dòng có số tiền. read(dòng) -> khoản hoặc None."""
    signals = [line_signal(line, day, read(line), source, reason) for line in text.splitlines() if line.strip()]
    return strictest(decide(s) for s in signals if s)


def issue(s):
    """Vì sao một dòng sổ phải chờ: "kep" (số rất lớn) | "nhieu_so" | "tuong_lai" | "lon" | None nếu ghi ngay được.
    Dòng có lý do của guard (dự định, câu hỏi) do guard trả lời riêng."""
    level = decide(s)
    if level == GHI_NGAY:
        return None
    if level == XAC_NHAN_KEP:
        return "kep"
    return "nhieu_so" if s.many_numbers else "tuong_lai" if s.future else "lon"


def held_lines(text, day, read):
    """Các dòng phải chờ xác nhận trước khi ghi: [(dòng, số tiền bot đọc được, issue)], cho thẻ hỏi lại."""
    out = []
    for line in text.splitlines():
        s = line_signal(line, day, read(line)) if line.strip() else None
        why = issue(s) if s else None
        if why:
            out.append((line.strip(), s.amount, why))
    return out


def big_side_buy(amount, monthly):
    """Mua quỹ chờ một khoản từ SIDE_BUY_MONTHS tháng tiền góp trở lên: nên gợi ý rải dần sang quỹ chính."""
    return bool(monthly) and amount >= SIDE_BUY_MONTHS * monthly
