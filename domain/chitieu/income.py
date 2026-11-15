"""Loại thu nhập theo ghi chú: lương, thưởng, đầu tư, làm thêm, khác."""
import re

from domain.common.text import plain

INCOME_KINDS = [("📈 Đầu tư", ["lãi bán", "cổ tức", "lãi tiết kiệm", "tiền lãi", "lãi"]), ("💼 Lương", ["lương"]),
                ("🎁 Thưởng", ["thưởng"]), ("🧑‍💻 Làm thêm", ["làm thêm", "freelance", "hoa hồng", "dự án", "bán hàng",
                                                             "kinh doanh", "cho thuê"])]


def income_kind(note):
    """Loại thu nhập theo ghi chú: lương, thưởng, đầu tư (lãi bán cổ phiếu, cổ tức, lãi tiết kiệm), làm thêm, khác."""
    bare = plain(note or "")
    for label, words in INCOME_KINDS:
        if any(re.search(rf"(?<!\w){re.escape(plain(w))}(?!\w)", bare) for w in words):
            return label
    return "💰 Khác"


def income_kinds(items):
    sums = {}
    for e in items:
        sums[income_kind(e["ghichu"])] = sums.get(income_kind(e["ghichu"]), 0) + e["tien"]
    return sorted(sums.items(), key=lambda x: -x[1])
