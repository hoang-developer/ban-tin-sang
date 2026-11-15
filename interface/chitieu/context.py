"""Ngữ cảnh lượt xử lý của bot chi tiêu: các hàm xếp nhóm, hiển thị, báo cáo tự lấy cấu hình nhóm hiện tại của người dùng
(đọc một lần mỗi lượt), để các lệnh và màn hình gọi gọn như trước."""
from domain.chitieu import classify as classify_rules
from domain.chitieu import income as income_rules
from domain.chitieu import parse as parse_rules
from domain.chitieu import period as periods
from domain.chitieu import refs
from domain.chitieu import text as chitieu_text
from domain.chitieu.kinds import INCOME
from domain.common import format as format_text
from infrastructure import clock
from presentation.chitieu import view as cview
from repositories.chitieu import groups as groups_repo
from services.chitieu import budget as budget_service
from services.chitieu import report as report_service

config, reset, save_config = groups_repo.config, groups_repo.reset, groups_repo.save


def today():
    return clock.now_vn().date()


def name(code, cfg=None):
    """Tên nhóm kèm biểu tượng ('🍜 Ăn uống'), kể cả nhóm đã ẩn; mã lạ thì là Khác."""
    return classify_rules.name(code, config() if cfg is None else cfg)


bare = classify_rules.bare


def groups(cfg=None):
    """Các nhóm đang dùng, theo thứ tự hiện trên nút: mã -> (tên, từ khóa tự thêm, từ khóa có sẵn)."""
    return classify_rules.groups(config() if cfg is None else cfg)


def rules(learned=None, cfg=None):
    """Bảng so khớp (mẫu có dấu, mẫu không dấu, điểm, mã): cụm từ đã học > từ khóa tự thêm > có sẵn."""
    return classify_rules.rules(learned, config() if cfg is None else cfg)


pick = classify_rules.pick


def classify(note, learned=None, cfg=None):
    """Mã nhóm của ghi chú. Cụm từ đã học (người dùng sửa nhóm) thắng từ khóa."""
    return classify_rules.classify(note, learned, config() if cfg is None else cfg)


def find_group(text, include_hidden=False, cfg=None):
    """Tên nhóm người dùng gõ ('ăn uống', 'di lai', 'ăn', 'trả nợ') -> mã, None nếu không có nhóm nào."""
    return classify_rules.find_group(text, config() if cfg is None else cfg, include_hidden)


parse_date = parse_rules.parse_date


def read_tag(line):
    """'#nhóm' trong dòng: (mã nhóm, tên nhóm chưa có, dòng đã bỏ phần #nhóm)."""
    return parse_rules.read_tag(line, config())


def parse_line(line, day, learned=None):
    """Một dòng tin nhắn -> khoản chi/thu (chưa có id), None nếu không có số tiền."""
    return parse_rules.parse_line(line, day, learned, config())


short = chitieu_text.short
vnd = format_text.vnd
ref, button_ref = refs.ref, refs.button_ref
period, full_month = periods.period, periods.full_month
income_kind, income_kinds, INCOME_KINDS = income_rules.income_kind, income_rules.income_kinds, income_rules.INCOME_KINDS
SORT_TITLE, REPORT_BUTTONS, BACK, CHI_BUTTONS = cview.SORT_TITLE, cview.REPORT_BUTTONS, cview.BACK, cview.CHI_BUTTONS


def entry_text(e, day):
    return cview.entry_text(e, day, config())


def budget_label(code):
    return cview.budget_label(code, config())


def budget_lines(codes, day):
    """Tiến độ ngân sách tháng của các nhóm vừa ghi (và ngân sách tổng)."""
    return cview.budget_lines(budget_service.progress(codes, day), config())


def budget_status(day):
    """Tiến độ mọi ngân sách đã đặt (từng nhóm và tổng) trong tháng này."""
    return cview.budget_lines(budget_service.all_progress(day), config())


def entries_message(entries, day, sorting=False, focus=None, extra=()):
    """Tin báo các khoản vừa ghi, kèm nút ✏️ đổi nhóm và ❌ xóa từng khoản."""
    notes = [] if sorting else budget_lines([e["nhom"] for e in entries if e["nhom"] != INCOME], day)
    return cview.entries_message(entries, day, config(), notes, sorting, focus, extra)


def picker(reference, keep="↩️ Thôi"):
    """Nút chọn nhóm cho một khoản."""
    return cview.picker(reference, config(), keep)


def with_picker(rows, reference, keep="↩️ Thôi"):
    """Thay hàng nút của một khoản bằng nút chọn nhóm, ngay tại chỗ."""
    return cview.with_picker(rows, reference, config(), keep)


def report(kind, day):
    """(nội dung báo cáo, số khoản chi) của một kỳ."""
    return cview.report_text(report_service.report_data(kind, day), config())
