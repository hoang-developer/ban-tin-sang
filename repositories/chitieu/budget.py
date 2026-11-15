"""BudgetRepo: ngân sách tháng theo nhóm (khóa keys.BUDGET): {mã nhóm | "tong": hạn mức}. Hiện mới có phần đọc;
các màn hình đang ghi ngân sách chuyển sang đây khi chức năng chitieu được tách (plan.md)."""
from repositories import keys, store


def load():
    return store.get(keys.BUDGET, {}) or {}
