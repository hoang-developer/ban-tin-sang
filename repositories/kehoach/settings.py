"""PlanSettingsRepo: cài đặt chia lương của người dùng (khóa keys.PLAN_SETTINGS): {"tieu_du": phần dư được phép tiêu, 0..1}."""
from repositories import keys, store


def load():
    return store.get(keys.PLAN_SETTINGS, {}) or {}


def spend_share():
    """Phần dư (sau trả nợ, quỹ dự phòng, đầu tư và mức chi tiêu thường) được phép tiêu; mặc định 0 (để dành hết)."""
    try:
        return min(1.0, max(0.0, float(load().get("tieu_du", 0))))
    except (TypeError, ValueError):
        return 0.0


def save_spend_share(share):
    store.put(keys.PLAN_SETTINGS, {**load(), "tieu_du": share})
