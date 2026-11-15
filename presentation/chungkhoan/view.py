"""Chữ của lệnh /stock: tổng quan phiên, chi tiết một mã, tin theo mã."""
import html

from domain.chungkhoan.rules import session_label
from domain.common.dates import WEEKDAYS
from domain.common.format import vn_num


def dong(x):
    """53000 -> '53.000'; chưa có giá -> '–'."""
    return vn_num(x, 0) if x else "–"


def ty(vnd):
    """Tiền đồng -> '332 tỷ' (dưới 10 tỷ thì lấy 1 số lẻ)."""
    return f"{vn_num(vnd / 1e9, 1 if abs(vnd) < 1e10 else 0)} tỷ"


def volume(shares):
    if shares >= 1e6:
        return f"{vn_num(shares / 1e6)} triệu cp"
    return f"{vn_num(shares, 0)} cp"


def change(now, ref, decimals):
    diff = now - ref
    pct = diff / ref * 100 if ref else 0
    return f"{vn_num(diff, decimals, sign=True)} ({vn_num(pct, sign=True)}%)"


def color(now, ref):
    return "🟢" if now > ref else "🔴" if now < ref else "🟡"


def index_lines(table):
    lines = []
    for name, (now, ref, value, up, down, same) in table.items():
        lines.append(f"{color(now, ref)} {name}: <b>{vn_num(now)}</b>  {change(now, ref, 2)}\n"
                     f"      GT {ty(value)} · ▲{up} ▼{down} ■{same}")
    return lines


def mover_lines(up, down, net):
    def row(qs):
        return " · ".join(f"<b>{q['symbol']}</b> {vn_num((q['price'] / q['ref'] - 1) * 100, sign=True)}%"
                          for q in qs)

    lines = []
    if up:
        lines.append(f"🟢 Tăng mạnh: {row(up)}")
    if down:
        lines.append(f"🔴 Giảm mạnh: {row(down)}")
    lines.append(f"🌏 Khối ngoại {'mua' if net >= 0 else 'bán'} ròng {ty(abs(net))}")
    return lines


def summary(now, index_part, movers):
    """Tổng quan phiên: index_part là các dòng chỉ số, movers là các dòng rổ VN30 (None nếu lỗi)."""
    parts = [f"📈 <b>Chứng khoán – {WEEKDAYS[now.weekday()]} {now:%d/%m}, {now:%H:%M}</b>\n"
             f"<i>{session_label(now)}</i>",
             "\n".join(index_part)]
    if movers:
        parts.append("<b>Trong rổ VN30</b>\n" + "\n".join(movers))
    parts.append("<i>Xem một mã: /stock FPT</i>")
    return "\n\n".join(parts)


def performance_lines(perf):
    changes, low, high = perf
    parts = [f"{label} {vn_num(pct, 1, sign=True)}%" for label, pct in changes]
    return [" · ".join(parts), f"52 tuần: thấp {dong(low)} – cao {dong(high)} <i>(giá đã điều chỉnh)</i>"]


def news_lines(items):
    lines = [f'• <a href="{html.escape(link)}">{html.escape(title, quote=False)}</a>' for title, link in items]
    return lines or ["<i>Không có tin trong 7 ngày qua</i>"]


def detail(symbol, q, perf, articles):
    """Chi tiết một mã; q là giá (dict), None nếu không có mã, hoặc Exception nếu không lấy được."""
    if isinstance(q, Exception):
        return f"⚪ <b>{symbol}</b>: không lấy được giá, thử lại sau nhé"
    if not q:
        return f"❓ Không tìm thấy mã <b>{symbol}</b>"

    price = q["price"] or q["ref"]  # chưa khớp lệnh nào thì lấy giá tham chiếu
    if q["ceiling"] and price >= q["ceiling"]:
        icon = "🟣"
    elif q["floor"] and price <= q["floor"]:
        icon = "🔵"
    else:
        icon = color(price, q["ref"])
    head = " · ".join(x for x in [f"<b>{symbol}</b>", q["exchange"], html.escape(q["name"] or "")] if x)
    lines = [head,
             f"{icon} <b>{dong(price)}</b>  {change(price, q['ref'], 0)}"
             + ("" if q["price"] else "  <i>(chưa khớp lệnh)</i>"),
             f"Tham chiếu {dong(q['ref'])} · Trần {dong(q['ceiling'])} · Sàn {dong(q['floor'])}"]
    if q["volume"]:
        net = q["f_buy"] - q["f_sell"]
        lines += [f"Mở {dong(q['open'])} · Cao {dong(q['high'])} · Thấp {dong(q['low'])}",
                  f"KL {volume(q['volume'])}" + (f" · GT {ty(q['value'])}" if q["value"] else ""),
                  f"Khối ngoại: mua {ty(q['f_buy'])} · bán {ty(q['f_sell'])} · "
                  f"{'mua' if net >= 0 else 'bán'} ròng {ty(abs(net))}"]
    for label, book in [("Dư mua", q["bids"]), ("Dư bán", q["asks"])]:
        if book:
            lines.append(f"{label}: " + " · ".join(f"{dong(p)} ({vn_num(v, 0)})" for p, v in book))

    stats = (performance_lines(perf) if perf else []) + ([f"Vốn hóa {ty(q['listed'] * price)}"] if q["listed"] else [])
    parts = ["\n".join(lines)]
    if stats:
        parts.append("<b>📊 Biến động giá</b>\n" + "\n".join(stats))
    parts.append("<b>📰 Tin 7 ngày qua</b>\n"
                 + "\n".join(news_lines(articles) if articles is not None else ["<i>Không lấy được tin</i>"]))
    return "\n\n".join(parts)
