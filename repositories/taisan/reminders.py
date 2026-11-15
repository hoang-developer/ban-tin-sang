"""Nhắc đáo hạn sổ tiết kiệm: mỗi sổ, mỗi ngày đáo hạn nhắc một lần."""
from infrastructure import kho
from repositories import keys


def claim_maturity(item_id, maturity):
    """True nếu đây là lần đầu nhắc sổ này cho ngày đáo hạn đó (đánh dấu đã nhắc 10 ngày)."""
    return kho.put_new(keys.saving_maturity_reminder(item_id, maturity), True, 10 * 86400)
