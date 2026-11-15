"""Đọc ảnh hóa đơn, chuyển khoản, lịch sử giao dịch: chuẩn hóa giao dịch AI đọc được, nhận ra chuyển giữa tài khoản của
chính chủ, hiểu ngày trên hóa đơn (tính thuần)."""
import re
from datetime import date, timedelta

from domain.common.text import norm, plain

KINDS = ("chi_tieu", "thu_nhap", "tra_no", "tra_the", "chuyen_noi_bo")
SKIP_WHY = {"tra_the": "trả thẻ tín dụng: các khoản quẹt thẻ ghi riêng rồi, ghi nữa là trùng",
            "chuyen_noi_bo": "chuyển giữa các tài khoản của bạn, không phải thu chi",
            "da_ghi": "đã ghi trước đó"}
MAX_TRANSACTIONS = 20
MAX_OWNERS = 5


def person(text):
    """Tên người (từ 2 chữ, toàn chữ cái) đã bỏ dấu, viết thường; '' nếu không giống tên người."""
    words = plain(re.sub(r"[^\w\s]", " ", text or "")).split()
    return " ".join(words) if len(words) >= 2 and all(w.isalpha() for w in words) else ""


def owner_names(known, txs):
    """Tên chủ tài khoản: các tên đã nhớ, cộng tên người ở các dòng trả thẻ tín dụng trong ảnh này (ai trả nợ
    thẻ tín dụng thì thường chính là chủ thẻ); giữ 5 tên gần nhất."""
    names = list(known)
    for tx in txs:
        who = person(tx["noi_ban"])
        if tx["kieu"] == "tra_the" and who and who not in names:
            names.append(who)
    return names[-MAX_OWNERS:]


def own_transfer(tx, names):
    """Tiền chuyển qua lại với chính chủ tài khoản: người gửi/nhận là chủ tài khoản, hoặc nội dung chỉ là
    "<tên chủ tài khoản> chuyển tiền". Có chữ lương, thưởng thì không phải."""
    note = " ".join(plain(tx["noi_dung"]).split())
    if not names or re.search(r"(?<!\w)(luong|thuong)(?!\w)", note):
        return False
    return person(tx["noi_ban"]) in names or any(note in (n, f"{n} chuyen tien", f"{n} chuyen khoan") for n in names)


def money_of(value):
    if isinstance(value, (int, float)):
        return max(0, round(value))
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())  # "29.000đ", "-4,390,000" -> số
    return int(digits) if digits else 0


def transactions(raw):
    """Giao dịch trong JSON AI trả về -> [{tien, chieu, ngay, noi_dung, noi_ban, diem, nhom, kieu}] (tối đa 20)."""
    items = raw.get("giao_dich")
    if not isinstance(items, list):  # kiểu cũ: một khoản nằm ngay ngoài cùng
        items = [raw] if raw.get("so_tien") else []
    txs = []
    for it in items[:MAX_TRANSACTIONS]:
        if not isinstance(it, dict) or not money_of(it.get("so_tien")):
            continue
        chieu = "thu" if it.get("chieu") == "thu" else "chi"
        kieu = it.get("kieu") if it.get("kieu") in KINDS else ("thu_nhap" if chieu == "thu" else "chi_tieu")
        if chieu == "thu" and kieu in ("chi_tieu", "tra_no", "tra_the"):
            kieu = "thu_nhap"
        if chieu == "chi" and kieu == "thu_nhap":
            kieu = "chi_tieu"
        txs.append({"tien": money_of(it.get("so_tien")), "chieu": chieu, "ngay": it.get("ngay"),
                    "noi_dung": norm(str(it.get("noi_dung") or ""))[:60], "noi_ban": str(it.get("noi_ban") or "")[:40],
                    "diem": money_of(it.get("diem")), "nhom": str(it.get("nhom") or ""), "kieu": kieu})
    return txs


def receipt_date(text, today):
    """'04/11/2026' -> date; không đọc được, ở tương lai hay quá 1 năm thì lấy hôm nay."""
    try:
        d, m, y = (int(x) for x in str(text).replace("-", "/").split("/")[:3])
        when = date(y, m, d)
    except (ValueError, TypeError):
        return today
    return when if today - timedelta(days=366) <= when <= today else today


def mark_own_transfers(txs, names):
    for tx in txs:
        if tx["kieu"] in ("thu_nhap", "chi_tieu") and own_transfer(tx, names):
            tx["kieu"] = "chuyen_noi_bo"


def prepare_list(txs, day, recorded):
    """Chuẩn bị danh sách nhiều giao dịch: ngày ISO, đã ghi chưa (recorded(ngay, tien, chieu) -> bool), mặc định chọn gì."""
    for tx in txs:
        tx["ngay"] = receipt_date(tx["ngay"], day).isoformat()
        tx["da_ghi"] = recorded(tx["ngay"], tx["tien"], tx["chieu"])
        tx["chon"] = tx["kieu"] in ("chi_tieu", "thu_nhap", "tra_no") and not tx["da_ghi"]
