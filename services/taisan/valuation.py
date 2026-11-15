"""Định giá mọi tài sản, lưu tài sản ròng theo ngày, so với 30 ngày trước. Chi tiết từng dòng còn là chữ dựng sẵn
(tách sang presentation khi các màn hình tài sản được chia)."""
import sys
from datetime import date, timedelta

from domain.common.format import vn_num
from domain.taisan import rules
from domain.taisan.kinds import TYPES
from domain.taisan.text import gold_amount, gold_name, qty_text, short
from repositories.dautu import fund as fund_repo
from repositories.taisan import assets as assets_repo
from repositories.vang import gold as gold_repo
from services.taisan import accounts
from services.taisan.prices import prices


def valuation(day, fresh=False):
    """Định giá mọi tài sản: dict gồm các dòng theo loại, tổng tài sản, tổng nợ, tài sản ròng, ghi chú giá."""
    data = assets_repo.load()
    items, gold = data["items"], gold_repo.load()
    by_kind = {}
    for it in items:
        by_kind.setdefault(it["loai"], []).append(it)
    quotes, notes = {}, []
    for kind in ("cp", "etf", "quy", "coin", "ngoaite"):
        codes = [it["ma"] for it in by_kind.get(kind, [])]
        quotes[kind], when, stale = prices(kind, codes, fresh)
        if codes and stale:
            notes.append(f"{TYPES[kind]}: nguồn giá lỗi, dùng giá lúc {when[11:16] + ' ' + when[8:10] + '/' + when[5:7] if when else '—'}")
    if gold:
        quotes["vang"], when, stale = prices("vang", ["sjc", "nhan"], fresh)
        if stale:
            notes.append("🥇 Vàng: nguồn giá lỗi, dùng giá gần nhất")
    rows = []  # (loại, mã dòng, tên, giá trị, giá vốn hoặc None, chi tiết)
    for it in items:
        kind, rid = it["loai"], str(it["id"])
        if kind == "no" and it["tien"] <= 0:
            continue  # khoản nợ đã trả xong: chỉ còn trong sổ nợ (/no)
        if kind == "tien" and it.get("chinh"):
            rows.append((kind, rid, it["ten"], accounts.main_balance(it, day), None, "chính, ước tính"))
        elif kind in ("tien", "khac", "no"):
            rows.append((kind, rid, it["ten"], it["tien"], None, ""))
        elif kind == "tietkiem":
            interest, maturity = rules.accrued(it, day)
            term = f"{it['ky']} tháng" if it.get("ky") else "không kỳ hạn"
            due = (f", đáo hạn {maturity:%d/%m/%Y}" + (" (đã tới hạn)" if maturity <= day else "")) if maturity else ""
            rows.append((kind, rid, it["ten"], it["tien"] + interest, it["tien"],
                         f"{short(it['tien'])} · {qty_text(it['lai'])}%/năm {term}{due}"))
        else:
            price = quotes.get(kind, {}).get(it["ma"])
            cost = it["sl"] * it["gia_von"] if it.get("gia_von") else None
            value = it["sl"] * price if price else (cost or 0)
            unit = {"cp": "cp", "etf": "ccq", "quy": "ccq", "coin": it["ma"].upper(), "ngoaite": it["ma"]}[kind]
            detail = f"{qty_text(it['sl'])} {unit} × {vn_num(price, 0) + 'đ' if price else 'chưa có giá'}"
            rows.append((kind, rid, it["ma"].upper(), value, cost, detail))
    for o in pending_orders():  # tiền đã chuyển đi mua quỹ, chưa thành ccq: vẫn là tài sản
        if o.get("tu"):
            rows.append(("quy", f"lenh{o['id']}", f"{o['quy']} đang chuyển", o["tien"], o["tien"],
                         f"đã bán {o['tu']} {o['ban'][8:]}/{o['ban'][5:7]}, chờ mua"))
        else:
            rows.append(("quy", f"lenh{o['id']}", f"{o['quy']} chờ khớp", o["tien"], o["tien"],
                         f"lệnh {o['dat'][8:]}/{o['dat'][5:7]}, khớp phiên {o['phien'][8:]}/{o['phien'][5:7]}"))
    for i, g in enumerate(gold):
        price = quotes.get("vang", {}).get(g.kind)
        value = g.taels * price if price else 0
        cost = g.taels * g.price * 1e6 if g.price else None
        rows.append(("vang", f"v{i}", gold_name(g.kind), value, cost, gold_amount(g.taels)))
    assets = sum(r[3] for r in rows if r[0] != "no")
    debts = sum(r[3] for r in rows if r[0] == "no")
    return {"rows": rows, "assets": assets, "debts": debts, "net": assets - debts, "notes": notes,
            "lailo": data.get("lailo", [])}

def pending_orders():
    """Lệnh mua quỹ (/dautu) đã đặt, chưa khớp."""
    try:
        cfg = fund_repo.load()
    except Exception as e:
        print(f"[lỗi] lệnh quỹ chờ khớp: {e!r}", file=sys.stderr)
        return []
    main = cfg.get("ma", "Quỹ")
    out = []
    for o in cfg.get("lenh", []):
        if o.get("loai", "mua") == "mua" and o.get("trang_thai") == "cho":
            out.append({**o, "quy": o.get("quy") or main})
        elif o.get("loai") == "doi" and o.get("trang_thai") == "chuyen":  # đã bán quỹ chờ, chưa mua quỹ chính
            out.append({**o, "quy": main, "tu": o.get("quy")})
    return out

def snapshot(day, v):
    """Lưu tài sản ròng của ngày (để xem tăng giảm theo thời gian, vẽ biểu đồ)."""
    kinds = {}
    for kind, _, _, value, _, _ in v["rows"]:
        kinds[kind] = kinds.get(kind, 0) + value
    assets_repo.save_snapshot(day.isoformat(), {"rong": round(v["net"]), "loai": {k: round(x) for k, x in kinds.items()}})

def history():
    return assets_repo.history()

def compare_line(day, net):
    """So tài sản ròng với lần lưu gần 30 ngày trước nhất (hoặc lần sớm nhất nếu chưa đủ 30 ngày)."""
    past = [(k, v) for k, v in history() if k < day.isoformat()]
    if not past:
        return ""
    target = (day - timedelta(days=30)).isoformat()
    k, v = min(past, key=lambda x: abs((date.fromisoformat(x[0]) - date.fromisoformat(target)).days))
    if not v["rong"]:
        return ""
    change = (net - v["rong"]) / abs(v["rong"]) * 100
    return f" ({'↑' if change >= 0 else '↓'}{abs(change):.1f}% so với {k[8:]}/{k[5:7]})".replace(".", ",")
