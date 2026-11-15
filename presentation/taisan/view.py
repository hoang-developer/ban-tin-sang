"""Màn hình tài sản: tổng quan, sửa/xóa, biểu đồ, tài khoản chính. Chữ, nút và cấu hình biểu đồ dựng từ số liệu đã tính."""
import html
from datetime import date

from presentation.chitieu.view import BACK
from domain.common.format import short as short_vnd, vnd
from domain.taisan.kinds import TYPES
from domain.taisan.text import gold_name, qty_text, short
from presentation.phantich.view import PALETTE


USAGE = ("💼 <b>Khai báo tài sản</b> (số tiền viết kiểu 25tr, 1tỷ2):\n"
         "• Tiền, tài khoản: /taisan tien VCB 25tr (cùng tên thì cập nhật số dư)\n"
         "• Tiết kiệm: /taisan tietkiem VCB 100tr 4,7% 6 thang 01/08/2026\n"
         "• Cổ phiếu: /taisan cp FPT 1000 95 (số lượng, giá vốn nghìn đồng)\n"
         "• ETF: /taisan etf E1VFVN30 1000 30 (ETF VN30 của Dragon Capital)\n"
         "• Quỹ mở: /taisan quy VCBF-FIF 1200 15000 (số ccq, giá vốn)\n"
         "• Vàng: /taisan vang sjc 1 luong 140 · /taisan vang nhan 2 chi\n"
         "• Tiền số: /taisan coin btc 0,05 · Ngoại tệ: /taisan usd 1000\n"
         "• Khác: /taisan khac xe máy 30tr\n"
         "• Nợ, trả dần mỗi tháng: /no chú Tư 100tr, trả 5tr/tháng (sổ nợ tự trừ khi trả)\n"
         "Mua bán cổ phiếu, ETF: nhắn <b>mua 1000 FPT giá 95</b>, <b>mua 500 E1VFVN30 giá 33,6</b>, <b>bán 500 FPT giá 120</b>\n"
         "Xem: /taisan · Sửa, xóa: /taisan xoa · Khám sức khỏe tài chính: /suckhoe")
BUTTONS = [[("📊 Biểu đồ", "ts:bd"), ("🩺 Khám sức khỏe", "ts:sk")],
           [("🗂 Sửa, xóa", "ts:ds"), ("🔄 Cập nhật giá", "ts:xem")],
           [("🏦 Tài khoản chính", "ts:chinh"), ("➕ Thêm", "y:them"), BACK]]

def gain_text(gain, cost):
    """'🟢 +190k (+8%)' / '🔴 −146k (−10%)'."""
    pct = f" ({gain / cost * 100:+.0f}%)".replace("-", "−") if cost else ""
    return f"{'🟢 +' if gain >= 0 else '🔴 −'}{short(abs(gain))}{pct}"

def gold_lines(rows, gold):
    """Vàng: mỗi loại một bảng chữ đều cột (<pre>): mỗi lần mua một dòng (ngày, số chỉ, giá mua một chỉ, lãi/lỗ),
    dòng Tổng (vốn trung bình), dòng Hôm nay (giá cửa hàng mua vào). Chấm màu ở cuối dòng để không lệch cột."""
    lots = {}
    for _, rid, _, value, cost, _ in rows:
        g = gold[int(rid[1:])]
        lots.setdefault(g.kind, []).append((g, value, cost))

    def tr(x):
        return f"{x / 1e6:.2f}".replace(".", ",") + "tr"

    def signed(x):
        return ("+" if x >= 0 else "−") + short(abs(x))

    def pct(gain, cost):
        return f"{gain / cost * 100:+.0f}%".replace("-", "−")

    def row(when, chi, price, gain=None, cost=None):
        line = f"{when:<5} {qty_text(round(chi, 2)):>3} {price:>7}"
        if gain is not None:
            line += f" {signed(gain):>6} {pct(gain, cost):>4} {'🟢' if gain >= 0 else '🔴'}"
        return line

    out = []
    for kind, items in lots.items():
        table = [f"{'Ngày':<5} {'Chỉ':>3} {'Giá/chỉ':>7} {'Lãi/lỗ':>6} {'%':>4}"]
        for g, v, c in items:
            chi = g.chi
            when = f"{g.bought[8:]}/{g.bought[5:7]}" if g.bought else "—"
            table.append(row(when, chi, tr(c / chi), v - c, c) if c else row(when, chi, "?"))
        chi = sum(g.taels for g, _, _ in items) * 10
        value = sum(v for _, v, _ in items)
        priced = [(g, v, c) for g, v, c in items if c]
        if priced:
            cost = sum(c for _, _, c in priced)
            table.append(row("Tổng", chi, tr(cost / (sum(g.taels for g, _, _ in priced) * 10)),
                             sum(v for _, v, _ in priced) - cost, cost))
        if chi and value:
            table.append(f"{'Hôm nay':<9} {tr(value / chi):>7}")
        out.append(f"  {gold_name(kind)}\n<pre>" + "\n".join(table) + "</pre>")
    return out

def overview_view(v, day, compare, gold):
    """Màn hình tổng quan tài sản: (chữ, nút), hoặc hướng dẫn nếu chưa có gì. compare: câu so với 30 ngày trước."""
    if not v["rows"]:
        return USAGE
    lines = [f"💼 <b>Tài sản ròng: {vnd(round(v['net']))}</b>{compare}",
             f"Tài sản {short(v['assets'])}" + (f" · nợ {short(v['debts'])}" if v["debts"] else "")]
    for kind, label in TYPES.items():
        rows = [r for r in v["rows"] if r[0] == kind]
        if not rows:
            continue
        value = sum(r[3] for r in rows)
        costs = [r for r in rows if r[4] is not None]
        head = f"\n{label}: <b>{short(value)}</b>"
        if kind != "no" and v["assets"]:
            head += f" ({value / v['assets'] * 100:.0f}%)"
        if costs and kind != "tietkiem":
            gain = sum(r[3] - r[4] for r in costs)
            base = sum(r[4] for r in costs)
            head += f" · {'🟢 lãi' if gain >= 0 else '🔴 lỗ'} {short(abs(gain))}" + (
                f" ({gain / base * 100:+.1f}%)".replace(".", ",").replace("-", "−") if base else "")
        elif kind == "tietkiem":
            head += f" · lãi tới nay {short(sum(r[3] - r[4] for r in rows))}"
        lines.append(head)
        if kind == "vang":  # vàng: gộp theo loại, giá theo chỉ, mỗi lần mua một dòng có giá mua
            lines += gold_lines(rows, gold)
            continue
        for _, _, name, value, cost, detail in rows:
            if not value and not cost:
                continue  # đã bán hết, quỹ chờ trống: không hiện dòng 0đ
            line = f"  • {html.escape(name)}: {short(value)}"
            if detail:
                line += f" · {html.escape(detail)}"
            if cost and kind != "tietkiem" and "chưa có giá" not in detail:
                change = (value - cost) / cost * 100
                line += f" {'🟢' if change >= 0 else '🔴'}{change:+.0f}%".replace("-", "−")
            lines.append(line)
    realized = [x for x in v["lailo"] if x["ngay"][:4] == str(day.year)]
    if realized:
        total = sum(x["lai"] for x in realized)
        lines.append(f"\n💰 Lãi/lỗ đã chốt năm {day.year}: <b>{'+' if total >= 0 else '−'}{vnd(round(abs(total)))}</b>"
                     f" ({len(realized)} lần bán)")
    lines += [f"<i>⚠️ {html.escape(n)}</i>" for n in v["notes"]]
    return "\n".join(lines), BUTTONS

def edit_list_view(v):
    if not v["rows"]:
        return USAGE
    lines = ["🗂 <b>Bấm ❌ để xóa</b> (sửa: khai báo lại cùng tên/mã là được cập nhật)"]
    buttons = []
    for i, (kind, rid, name, value, _, _) in enumerate([r for r in v["rows"] if not r[1].startswith("lenh")], 1):
        lines.append(f"{i}. {TYPES[kind].split()[0]} {html.escape(name)}: {short(value)}")
        buttons.append((f"❌ {i}", f"ts:x:{rid}"))
    return "\n".join(lines), [buttons[i:i + 5] for i in range(0, len(buttons), 5)] + [[("↩️ Xong", "ts:xem")]]

def pie_chart(v):
    """Biểu đồ tròn tỷ trọng các loại tài sản (không tính nợ); None nếu chưa có tài sản nào."""
    sums = {}
    for kind, _, _, value, _, _ in v["rows"]:
        if kind != "no" and value > 0:
            sums[kind] = sums.get(kind, 0) + value
    if not sums:
        return None
    order = sorted(sums.items(), key=lambda x: -x[1])
    colors = {k: PALETTE[i] for i, k in enumerate(TYPES)}
    return {"type": "doughnut", "data": {
        "labels": [f"{TYPES[k].split(' ', 1)[1]} {short_vnd(x)} ({x / v['assets'] * 100:.0f}%)" for k, x in order],
        "datasets": [{"data": [round(x) for _, x in order], "backgroundColor": [colors[k] for k, _ in order]}]},
        "options": {"plugins": {"datalabels": {"display": False}, "legend": {"position": "right", "labels": {"font": {"size": 16}}},
                                "title": {"display": True, "font": {"size": 22},
                                          "text": f"Tài sản ròng {vnd(round(v['net']))}"}}}}


def line_chart(past):
    """Biểu đồ đường tài sản ròng theo ngày. past: [(ngày ISO, {"rong", ...})]."""
    return {"type": "line", "data": {"labels": [f"{k[8:]}/{k[5:7]}" for k, _ in past],
                                     "datasets": [{"label": "Tài sản ròng (triệu đồng)", "fill": True,
                                                   "data": [round(x["rong"] / 1e6, 1) for _, x in past],
                                                   "borderColor": "#2f9e44", "backgroundColor": "#2f9e4433"}]},
            "options": {"locale": "vi-VN", "plugins": {"datalabels": {"display": False}, "title": {
                "display": True, "font": {"size": 20}, "text": "Tài sản ròng theo thời gian (triệu đồng)"}}}}


def chart_caption(v):
    return f"💼 <b>Tài sản ròng</b>: {vnd(round(v['net']))}"

def main_line_text(it, balance):
    """'🏦 VCB ~12,3tr' cho màn hình tổng quan; None nếu chưa chọn."""
    return f"🏦 {html.escape(it['ten'])} còn ~<b>{short(balance)}</b>"

def main_view(it, income, spend, balance):
    """Màn hình tài khoản chính: số dư ước tính, thu/chi từ lúc chốt, các lần chuyển tiền gần nhất."""
    moves = it.get("chuyen", [])
    out = sum(-x["tien"] for x in moves if x["tien"] < 0)
    back = sum(x["tien"] for x in moves if x["tien"] > 0)
    since = date.fromisoformat(it["moc_ngay"])
    lines = [f"🏦 <b>{html.escape(it['ten'])} ~{vnd(round(balance))}</b> (tài khoản chính)",
             f"📌 Chốt {since:%d/%m}: {vnd(it['tien'])}",
             f"💰 Thu +{short(income) if income else '0đ'} · 💸 chi −{short(spend) if spend else '0đ'}"]
    if out or back:
        lines.append(f"🔁 Chuyển đi −{short(out)}" + (f" · về +{short(back)}" if back else ""))
        lines += [f"   {x['ngay'][8:]}/{x['ngay'][5:7]} {'−' if x['tien'] < 0 else '+'}{short(abs(x['tien']))} "
                  f"{html.escape(x['ghi'])}" for x in moves[-5:][::-1]]
    lines.append("<i>Lệch với app ngân hàng thì bấm cập nhật số dư thật</i>")
    return "\n".join(lines), [[("✏️ Cập nhật số dư thật", "y:them:tai_khoan:chinh")],
                              [("🔁 Đổi tài khoản chính", "ts:chon"), ("💼 Tài sản", "m:ts"), BACK]]

def choose_main_view(options):
    """Màn hình chọn tài khoản chính. options: [(mục, số dư đang hiện)] của các tài khoản có thể chọn."""
    lines = ["🏦 <b>Chọn tài khoản chính</b> (lương về, hay tiêu)",
             "Bot tự cộng thu, trừ chi, trừ tiền chuyển sang quỹ, đầu tư, tiết kiệm, trả nợ."]
    if not options:
        lines.append("Chưa có tài khoản: nhắn «tài khoản Techcombank còn 14tr» hoặc bấm nút.")
        return "\n".join(lines), [[("➕ Thêm tài khoản", "y:them:tai_khoan"), BACK]]
    rows = [[(("✅ " if it.get("chinh") else "") + f"{it['ten']} ({short(shown)})",
              f"ts:chinh:{it['id']}")] for it, shown in options[:6]]
    return "\n".join(lines), rows + [[("➕ Tài khoản khác", "y:them:tai_khoan"), BACK]]
