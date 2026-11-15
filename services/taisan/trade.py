"""Mua bán cổ phiếu, ETF bằng tin nhắn: cập nhật danh mục, tính thuế, lãi/lỗ, ghi lãi vào Thu nhập. Tiền đi/về tài
khoản DNSE nếu đã khai báo, không thì tài khoản chính. Câu báo còn nằm trong module này (tách sang presentation sau)."""
import html

from domain.chitieu.kinds import INCOME
from domain.common.format import vn_num, vnd
from domain.common.text import plain
from domain.taisan import rules
from domain.taisan.trade import BROKER_FEE, SELL_TAX, parse_trade
from repositories.chitieu import ledger as ledger_repo
from repositories.taisan import assets as assets_repo
from services.taisan import accounts
from services.taisan.prices import prices


def broker_cash(data):
    """Tài khoản tiền tên có chữ DNSE (tiền chờ trong tài khoản chứng khoán), None nếu chưa khai báo."""
    return next((it for it in data["items"] if it["loai"] == "tien" and "dnse" in plain(it["ten"])), None)


def trade(text, now, pay_main=True):
    """Xử lý tin mua/bán cổ phiếu; None nếu tin không phải mua bán cổ phiếu (để ghi như khoản chi thường).
    Tiền đi/về tài khoản DNSE nếu đã khai báo, không thì tài khoản chính (pay_main=False: tiền có sẵn, không trừ)."""
    found = parse_trade(text)
    if not found:
        return None
    side, qty, code, price = found
    data = assets_repo.load()
    kind = "etf" if rules.is_etf(code) else "cp"
    holding = next((it for it in data["items"] if it["loai"] in ("cp", "etf") and it["ma"] == code), None)
    cash = broker_cash(data)
    value = qty * price
    if side == "mua":
        listed, _, stale = prices(kind, [code])
        if code not in listed and not stale:
            return None  # không phải mã chứng khoán: để ghi như khoản chi
        paid = value * (1 + BROKER_FEE)
        if holding:
            total_cost = holding["sl"] * (holding.get("gia_von") or price) + paid
            holding["sl"] += qty
            holding["gia_von"] = total_cost / holding["sl"]
        else:
            holding = {"id": assets_repo.new_id(data), "loai": kind, "ma": code, "sl": qty, "gia_von": paid / qty}
            data["items"].append(holding)
        lines = [f"📈 Mua {vn_num(qty, 0)} {code} × {vnd(price)} = <b>{vnd(round(paid))}</b>",
                 f"Giữ {vn_num(holding['sl'], 0)} {code} · giá vốn {vnd(round(holding['gia_von']))}"]
        if cash:
            cash["tien"] -= round(paid)
            lines.append(f"🏦 Tiền tài khoản {html.escape(cash['ten'])}: còn {vnd(cash['tien'])}")
        elif pay_main:
            moved = accounts.move_main(data, -paid, f"mua {vn_num(qty, 0)} {code}", now.date())
            if moved:
                lines.append(moved)
        assets_repo.save(data)
        return "\n".join(lines)
    if not holding:
        return (f"Chưa có {code} trong danh mục nên chưa tính được lãi/lỗ. Khai báo trước: "
                f"/taisan cp {code} số_lượng giá_vốn (ví dụ /taisan cp {code} 1000 95)")
    if qty > holding["sl"]:
        return f"Bạn chỉ đang giữ {vn_num(holding['sl'], 0)} {code}, không bán được {vn_num(qty, 0)}"
    tax, fee = value * SELL_TAX, value * BROKER_FEE
    received = value - tax - fee
    cost = qty * (holding.get("gia_von") or price)
    gain = received - cost
    holding["sl"] -= qty
    if holding["sl"] == 0:
        data["items"] = [it for it in data["items"] if it is not holding]
    data.setdefault("lailo", []).append({"ngay": now.date().isoformat(), "ma": code, "sl": qty, "gia": price,
                                         "lai": round(gain)})
    data["lailo"] = data["lailo"][-200:]
    lines = [f"💰 Bán {vn_num(qty, 0)} {code} × {vnd(price)} = {vnd(round(value))}",
             f"Thuế 0,1% −{vnd(round(tax))}" + (f" · phí −{vnd(round(fee))}" if fee else "")
             + f" → về <b>{vnd(round(received))}</b>",
             f"Giá vốn {vnd(round(holding.get('gia_von') or price))} → "
             + (f"🟢 <b>lãi {vnd(round(gain))}</b>" if gain >= 0 else f"🔴 <b>lỗ {vnd(round(-gain))}</b>")
             + f" ({gain / cost * 100:+.1f}%)".replace(".", ",")]
    if gain > 0:  # phần lãi là thu nhập đầu tư; phần vốn chỉ là đổi cổ phiếu ra tiền
        entry = {"id": ledger_repo.next_id(), "ngay": now.date().isoformat(), "gio": now.strftime("%H:%M"),
                 "tien": round(gain), "ghichu": f"lãi bán {qty} {code}", "nhom": INCOME,
                 "khong_tk": True}  # tiền bán đã cộng cả vào tài khoản bên dưới, không cộng lần nữa
        ledger_repo.save(entry)
        lines.append("💰 Lãi đã ghi vào Thu nhập")
    lines.append(f"Còn {vn_num(holding['sl'], 0)} {code}" if holding["sl"] else f"Hết {code}")
    if cash:
        cash["tien"] += round(received)
        lines.append(f"🏦 Tiền tài khoản {html.escape(cash['ten'])}: {vnd(cash['tien'])}")
    elif pay_main:
        moved = accounts.move_main(data, received, f"bán {vn_num(qty, 0)} {code}", now.date())
        if moved:
            lines.append(moved)
    assets_repo.save(data)
    return "\n".join(lines)
