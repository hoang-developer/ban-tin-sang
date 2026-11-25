"""Bán, rút, thu về: tiền về tài khoản chính (nếu có), phần lãi ghi vào Thu nhập. Câu báo còn nằm trong module này
(tách sang presentation khi các màn hình tài sản được chia)."""
import html

from domain.chitieu.kinds import INCOME
from domain.common.dates import add_months
from domain.common.format import vnd
from domain.common.text import plain
from domain.taisan import rules
from domain.taisan.text import gain_line, gold_name, qty_text
from domain.vang.gold import holdings_chi, sell_fifo
from repositories.chitieu import ledger as ledger_repo
from repositories.taisan import assets as assets_repo
from repositories.vang import gold as gold_repo
from services.taisan import accounts
from services.taisan.prices import prices


def realize(data, now, code, qty, price, gain, note):
    """Ghi lãi/lỗ đã chốt; lãi dương thì ghi khoản thu (không cộng tài khoản chính lần nữa)."""
    data.setdefault("lailo", []).append({"ngay": now.date().isoformat(), "ma": code, "sl": qty, "gia": price,
                                         "lai": round(gain)})
    data["lailo"] = data["lailo"][-200:]
    if gain > 0:
        ledger_repo.save({"id": ledger_repo.next_id(), "ngay": now.date().isoformat(), "gio": now.strftime("%H:%M"),
                 "tien": round(gain), "ghichu": note, "nhom": INCOME, "khong_tk": True})

def sell_gold(chi, received, now, kind=None, to_main=True):
    """Bán vàng: lấy dần từ các lần mua cũ nhất (cùng loại nếu có nói). chi=None: bán hết. Trả câu báo."""
    gold = gold_repo.load()
    have = holdings_chi(gold, kind)
    if not any(not kind or g.kind == kind for g in gold) or have <= 0:
        return "Ví vàng đang trống, chưa có gì để bán"
    chi = have if chi is None else chi
    if chi > have + 1e-6:
        return f"Ví chỉ có {qty_text(round(have, 2))} chỉ{' ' + gold_name(kind).lower() if kind else ''}, không bán được {qty_text(chi)} chỉ"
    sale = sell_fifo(gold, chi, kind)
    cost = sale.cost
    gold_repo.save(sale.lots)
    data = assets_repo.load()
    gain = received - cost if cost else 0
    if cost:
        realize(data, now, "Vàng", chi, received / chi, gain, f"lãi bán {qty_text(chi)} chỉ vàng")
    moved = accounts.move_main(data, received, f"bán {qty_text(chi)} chỉ vàng", now.date()) if to_main else None
    assets_repo.save(data)
    return "\n".join([f"🥇 Bán {qty_text(round(chi, 2))} chỉ vàng = <b>{vnd(round(received))}</b>"
                      + (f" · vốn {vnd(round(cost))} → {gain_line(gain, cost)}" if cost else "")]
                     + ([moved] if moved else []))

def close_saving(name, received, now, to_main=True):
    """Tất toán sổ tiết kiệm: nhận về `received` (None: gốc + lãi tới hôm nay). Trả câu báo."""
    data = assets_repo.load()
    it = rules.find_item(data, name, ("tietkiem",))
    if not it:
        books = [x["ten"] for x in data["items"] if x["loai"] == "tietkiem"]
        return (f"Không thấy sổ «{html.escape(name or '')}»" + (f". Đang có: {html.escape(', '.join(books))}" if books
                                                                  else ". Chưa có sổ tiết kiệm nào"))
    total, _, early, maturity = rules.payout(it, now.date())
    guessed = not received  # số nhận về do bot tính (người dùng không nói)
    received = round(received if received else total)
    gain = received - it["tien"]
    data["items"] = [x for x in data["items"] if x is not it]
    if gain > 0:
        realize(data, now, f"Sổ {it['ten']}", 1, received, gain, f"lãi tiết kiệm {it['ten']}")
        data["lailo"].pop()  # lãi tiết kiệm là thu nhập, không phải lãi/lỗ mua bán
    moved = accounts.move_main(data, received, f"tất toán sổ {it['ten']}", now.date()) if to_main else None
    assets_repo.save(data)
    return "\n".join([f"🐷 Tất toán sổ {html.escape(it['ten'])}: gốc {vnd(it['tien'])} → nhận <b>{vnd(received)}</b>"
                      + (f" (lãi {vnd(gain)})" if gain else "")]
                     + ([f"⚠️ Rút trước hạn ({maturity:%d/%m/%Y}) nên bot chỉ tính lãi không kỳ hạn. Ngân hàng trả khác thì nhắn "
                         f"«tất toán sổ {html.escape(it['ten'])} nhận về <số tiền>»"] if early and guessed else [])
                     + ([moved] if moved else []))

def early_close_date(name, day):
    """Ngày đáo hạn nếu sổ tên `name` chưa tới hạn (tất toán lúc này là rút trước hạn, chỉ được lãi không kỳ hạn); None nếu không."""
    it = rules.find_item(assets_repo.load(), name, ("tietkiem",))
    if not it:
        return None
    _, _, early, maturity = rules.payout(it, day)
    return maturity if early else None


def renew_saving(item_id, day):
    """Tái tục sổ đã tới hạn: gốc mới = gốc + lãi tới hạn, cùng kỳ hạn và lãi suất, tính từ ngày đáo hạn (như ngân hàng tự tái
    tục). Trả câu báo."""
    data = assets_repo.load()
    it = next((x for x in data["items"] if x["loai"] == "tietkiem" and str(x["id"]) == str(item_id)), None)
    if not it:
        return "Sổ này không còn trong tài sản"
    _, maturity = rules.accrued(it, day)
    if not maturity or maturity > day:
        return "Sổ này chưa tới hạn"
    it.update(tien=round(it["tien"] + rules.accrued(it, day)[0]), ngay=maturity.isoformat())
    assets_repo.save(data)
    new_maturity = add_months(maturity, it["ky"])
    return (f"🔁 Đã tái tục sổ {html.escape(it['ten'])}: gốc mới <b>{vnd(it['tien'])}</b> (gốc + lãi tới hạn), {it['ky']} tháng, lãi "
            f"{qty_text(it['lai'])}%/năm tính từ {maturity:%d/%m/%Y}, đáo hạn {new_maturity:%d/%m/%Y}. Ngân hàng đổi lãi suất "
            "thì khai báo lại: /taisan tietkiem …")


def sell_fund(code, received, units, now, to_main=True):
    """Bán chứng chỉ quỹ: số ccq (None: tính theo NAV gần nhất), tiền nhận về. Trả câu báo."""
    data = assets_repo.load()
    it = rules.find_item(data, code, ("quy", "etf"))
    if not it:
        return f"Chưa có quỹ {html.escape((code or '').upper())} trong tài sản"
    if not units:
        nav = prices(it["loai"], [it["ma"]])[0].get(it["ma"])
        if not nav:
            return f"Chưa lấy được NAV {it['ma']}: nhắn kèm số ccq đã bán, ví dụ «bán 30 ccq {it['ma']} được 450k»"
        units = round(received / nav, 2)
    if units > it["sl"] + 1e-6:
        return f"Chỉ đang có {qty_text(it['sl'])} ccq {it['ma']}, không bán được {qty_text(units)}"
    cost = units * (it.get("gia_von") or 0)
    it["sl"] = round(it["sl"] - units, 2)
    if it["sl"] <= 0:
        data["items"] = [x for x in data["items"] if x is not it]
    gain = received - cost if cost else 0
    if cost:
        realize(data, now, it["ma"], units, received / units, gain, f"lãi bán {qty_text(units)} ccq {it['ma']}")
    moved = accounts.move_main(data, received, f"bán {qty_text(units)} ccq {it['ma']}", now.date()) if to_main else None
    assets_repo.save(data)
    return "\n".join([f"💹 Bán {qty_text(units)} ccq {it['ma']} = <b>{vnd(round(received))}</b>"
                      + (f" · vốn {vnd(round(cost))} → {gain_line(gain, cost)}" if cost else "")
                      + (f" · còn {qty_text(it['sl'])} ccq" if it["sl"] > 0 else "")] + ([moved] if moved else []))

def collect_loan(name, amount, now, to_main=True):
    """Người vay trả lại: trừ khoản phải thu "Cho X vay", hết thì xóa. Trả câu báo."""
    data = assets_repo.load()
    loans = [x for x in data["items"] if x["loai"] == "khac" and plain(x["ten"]).startswith("cho ")]
    key = plain(name or "")
    hit = [x for x in loans if key and key in plain(x["ten"])]
    if len(hit) != 1:
        return (f"Không thấy khoản cho «{html.escape(name or '')}» vay. Đang cho vay: "
                + (html.escape(", ".join(x["ten"] for x in loans)) if loans else "chưa có khoản nào"))
    it = hit[0]
    took = min(amount, it["tien"])
    it["tien"] -= took
    note = f"🤝 {html.escape(it['ten'])}: đã thu {vnd(took)}"
    if it["tien"] <= 0:
        data["items"] = [x for x in data["items"] if x is not it]
        note += " · ✅ trả hết"
    else:
        note += f" · còn {vnd(it['tien'])}"
    if amount > took:
        note += f" (thừa {vnd(amount - took)} so với số cho vay)"
    moved = accounts.move_main(data, took, f"{it['ten']} trả", now.date()) if to_main else None
    assets_repo.save(data)
    return note + (f"\n{moved}" if moved else "")

def remove_named(name):
    data = assets_repo.load()
    it = rules.removable(data, name)
    if not it:
        return f"Không thấy «{html.escape(name or '')}» trong tài sản"
    if it.get("chinh"):
        return "Đây là tài khoản chính: đổi tài khoản chính khác trước rồi mới xóa"
    data["items"] = [x for x in data["items"] if x is not it]
    assets_repo.save(data)
    return f"🗑 Đã xóa {html.escape(it.get('ten') or it.get('ma'))} khỏi tài sản"


def remove_by_id(rid):
    """Xóa một mục theo mã dòng trên màn hình (vàng "v<số>" hoặc mã mục). True nếu có xóa."""
    if rid.startswith("v"):
        return gold_repo.remove_at(int(rid[1:]))
    data = assets_repo.load()
    kept = [it for it in data["items"] if str(it["id"]) != rid]
    if len(kept) == len(data["items"]):
        return False
    data["items"] = kept
    assets_repo.save(data)
    return True
