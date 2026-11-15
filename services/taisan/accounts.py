"""Tài khoản chính: nơi lương về, tiền tiêu và tiền chuyển đi các ngăn khác.
Số dư = số dư thật lúc chốt + thu − chi ghi sổ sau lúc chốt (khoản có số thứ tự lớn hơn mốc, ngày từ ngày chốt)
± tiền chuyển qua lại với các ngăn khác (quỹ dự phòng, quỹ chờ đầu tư, sổ tiết kiệm, vàng, cổ phiếu...).
Tính lại mỗi lần xem nên sửa, xóa khoản chi cũng tự đúng. Chưa chọn tài khoản chính thì mọi thứ như trước."""
import html
from datetime import date

from domain.common.text import plain
from domain.taisan import rules
from domain.taisan.text import short
from infrastructure import clock
from repositories.chitieu import ledger as ledger_repo
from repositories.taisan import assets as assets_repo

can_be_main = rules.can_be_main
same_name = rules.same_name


def today():
    return clock.now_vn().date()


def main_account(data=None):
    data = data if data is not None else assets_repo.load()
    return next((it for it in data["items"] if it["loai"] == "tien" and it.get("chinh")), None)


def pin_balance(it, amount):
    """Chốt số dư thật: tính lại từ đây (các khoản ghi trước lúc này đã nằm trong số dư)."""
    it.update(tien=int(amount), moc=ledger_repo.last_id(), moc_ngay=today().isoformat(), chuyen=[])

def main_flows(it, day=None):
    """(thu, chi) ghi sổ từ lúc chốt số dư tài khoản chính."""
    since = it.get("moc_ngay")
    day = day or today()
    if not since or since > day.isoformat():
        return 0, 0
    return rules.main_flows(it, day, ledger_repo.between(date.fromisoformat(since), day))


def main_balance(it, day=None):
    income, spend = main_flows(it, day)
    return rules.main_balance(it, income, spend)

def move_main(data, delta, note, day=None):
    """Tiền vào (delta > 0) hoặc ra (delta < 0) tài khoản chính vì chuyển sang ngăn khác (chưa lưu, người gọi lưu
    data). Trả dòng báo, None nếu chưa chọn tài khoản chính."""
    it = main_account(data)
    delta = int(round(delta))
    if not it or not delta:
        return None
    day = day or today()
    moves = it.setdefault("chuyen", [])
    moves.append({"ngay": day.isoformat(), "tien": delta, "ghi": note[:40]})
    if len(moves) > 150:  # gộp các lần cũ vào số chốt cho gọn
        it["tien"] += sum(x["tien"] for x in moves[:-100])
        it["chuyen"] = moves[-100:]
    left = main_balance(it, day)
    return f"🏦 {html.escape(it['ten'])} {'−' if delta < 0 else '+'}{short(abs(delta))} → ~{short(left)}"

def find_account(data, name):
    """Tài khoản tiền theo tên: trùng tên, không thì tên này chứa tên kia ("VCB" và "Vietcombank VCB")."""
    accounts = [it for it in data["items"] if it["loai"] == "tien"]
    key = plain(name or "").strip()
    if not key:
        return None
    exact = next((it for it in accounts if same_name(it["ten"], name)), None)
    if exact:
        return exact
    near = [it for it in accounts if key in plain(it["ten"]) or plain(it["ten"]).strip() in key]
    return near[0] if len(near) == 1 else None

def set_main(data, it):
    for other in data["items"]:
        if other is not it and other.get("chinh"):
            other["tien"] = main_balance(other)  # tài khoản cũ giữ số dư ước tính tới lúc này, thôi tự trừ
            for key in ("chinh", "moc", "moc_ngay", "chuyen"):
                other.pop(key, None)
    it["chinh"] = True
    pin_balance(it, it["tien"])

def pick_main(item_id):
    data = assets_repo.load()
    it = next((x for x in data["items"] if str(x["id"]) == str(item_id) and can_be_main(x)), None)
    if not it:
        return None
    set_main(data, it)
    assets_repo.save(data)
    return it
