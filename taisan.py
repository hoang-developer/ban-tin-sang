"""Tài sản, mua bán cổ phiếu và khám sức khỏe tài chính cho bot chi tiêu.

- /taisan: khai báo tiền, tiết kiệm, cổ phiếu, quỹ mở, vàng, tiền số, ngoại tệ, tài sản khác, nợ; bot tự lấy
  giá và tính tài sản ròng. Vàng dùng chung ví vàng (/vivang) của bot bản tin.
- Nhắn "mua 1000 FPT giá 95" / "bán 500 FPT giá 120": cập nhật danh mục, tính thuế, lãi/lỗ, ghi lãi vào Thu nhập.
- /suckhoe: khám sức khỏe tài chính từ số liệu của chính bạn; AI chỉ viết nhận xét, không khuyên mua bán mã nào.
"""
import html
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from calendar import monthrange
from datetime import date, datetime, timedelta

import chungkhoan
import kho
import phantich as pt
import sochitieu as ct
from bantin import VN_TZ, gold_prices, vn_num

K_ASSETS = "chitieu:taisan"  # {"items": [...], "dem": số đã cấp, "lailo": [lãi/lỗ đã bán]}
K_HISTORY = "chitieu:taisan:lichsu"  # hash: ngày -> {"rong": tài sản ròng, "loai": {loại: giá trị}}
K_GOLD = "vivang"  # ví vàng của bot bản tin: [{"loai": "sjc"|"nhan", "luong": lượng, "gia": triệu/lượng}]
K_SALARY = "chitieu:luong"  # {"ngay": ngày nhận lương, "tien": số tiền}
SELL_TAX = 0.001  # thuế thu nhập cá nhân khi bán chứng khoán: 0,1% giá trị bán
BROKER_FEE = 0.0  # DNSE miễn phí giao dịch; công ty khác thường thu 0,1–0,35% mỗi chiều
TYPES = {"tien": "🏦 Tiền, tài khoản", "tietkiem": "🐷 Tiết kiệm", "etf": "🧺 ETF", "cp": "📈 Cổ phiếu", "quy": "💹 Quỹ mở",
         "vang": "🥇 Vàng", "coin": "🪙 Tiền số", "ngoaite": "💵 Ngoại tệ", "khac": "🏠 Tài sản khác", "no": "💳 Nợ"}
COINS = {"btc": "bitcoin", "eth": "ethereum", "usdt": "tether", "bnb": "binancecoin", "sol": "solana",
         "xrp": "ripple", "ada": "cardano", "doge": "dogecoin", "ton": "the-open-network", "trx": "tron"}
FMARKET = "https://api.fmarket.vn/res/products/filter"
VCB_FX = "https://portal.vietcombank.com.vn/Usercontrols/TVPortal.TyGia/pXML.aspx"
BUTTONS = [[("📊 Biểu đồ", "ts:bd"), ("🩺 Khám sức khỏe", "ts:sk")],
           [("🗂 Sửa, xóa", "ts:ds"), ("🔄 Cập nhật giá", "ts:xem")],
           [("➕ Thêm", "y:them"), ct.BACK]]
NOT_ADVICE = "<i>Chỉ để tham khảo, không phải lời khuyên mua bán chứng khoán hay đầu tư.</i>"


def qty_text(x):
    """1000 -> '1.000'; 0.05 -> '0,05'; 1234.5 -> '1.234,5'."""
    x = float(x)
    if x.is_integer():
        return vn_num(x, 0)
    whole, frac = vn_num(x, 6).split(",")
    return f"{whole},{frac.rstrip('0')}"


def gold_amount(taels):
    chi = round(taels * 10, 2)  # 0,02 lượng = 0,2 chỉ (vàng ép vỉ 0,1 chỉ)
    whole = int(chi // 10)
    rest = round(chi - whole * 10, 2)
    rest_text = f"{rest:g}".replace(".", ",")
    return " ".join(([f"{whole} lượng"] if whole else []) + ([f"{rest_text} chỉ"] if rest else [])) or "0 chỉ"


def now_vn():
    return datetime.now(VN_TZ)


def short(x):
    return ("−" if x < 0 else "") + pt.short(abs(x))


def load():
    data = kho.get(K_ASSETS, {}) or {}
    data.setdefault("items", [])
    return data


def save(data):
    kho.put(K_ASSETS, data)


def new_id(data):
    data["dem"] = data.get("dem", 0) + 1
    return data["dem"]


# ---- Giá: lấy từ nguồn, nhớ trong kho; nguồn lỗi thì dùng giá gần nhất ---------------

def http_json(url, body=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def stock_prices(codes):
    quotes = chungkhoan.quotes(codes)
    return {s: q["price"] or q["ref"] for s, q in quotes.items() if q["price"] or q["ref"]}


def gold_table(codes=None):
    p = gold_prices()  # triệu đồng/lượng, giá cửa hàng mua vào
    return {"sjc": p["sjc"][0] * 1e6, "nhan": p["nhan"][0] * 1e6}


def fund_navs(codes=None):
    body = {"types": ["NEW_FUND", "TRADING_FUND"], "issuerIds": [], "sortOrder": "DESC", "sortField": "navTo6Months",
            "page": 1, "pageSize": 100, "isIpo": False, "fundAssetTypes": [], "bondRemainPeriods": [],
            "searchField": "", "isBuyByReward": False, "thirdAppIds": []}
    rows = http_json(FMARKET, body)["data"]["rows"]
    return {r["shortName"].upper(): float(r["nav"]) for r in rows if r.get("shortName") and r.get("nav")}


def coin_prices(codes):
    """Giá tiền số (đồng): CoinGecko; bị chặn hay quá lượt thì lấy giá USD trên Coinbase × tỷ giá Vietcombank."""
    ids = {COINS.get(c, c): c for c in codes}
    try:
        data = http_json("https://api.coingecko.com/api/v3/simple/price?vs_currencies=vnd&ids=" + ",".join(ids))
        got = {ids[i]: float(v["vnd"]) for i, v in data.items() if v.get("vnd")}
        if got:
            return got
    except Exception as e:
        print(f"[lỗi] CoinGecko, chuyển sang Coinbase: {e!r}", file=sys.stderr)
    usd = prices("ngoaite", ["USD"])[0].get("USD")
    if not usd:
        raise RuntimeError("không có tỷ giá USD để đổi giá tiền số")
    got = {}
    for code in codes:
        try:
            got[code] = float(http_json(f"https://api.coinbase.com/v2/prices/{code.upper()}-USD/spot")["data"]["amount"]) * usd
        except Exception as e:
            print(f"[lỗi] Coinbase {code}: {e!r}", file=sys.stderr)
    return got


def fx_rates(codes=None):
    req = urllib.request.Request(VCB_FX, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        root = ET.fromstring(r.read())
    rates = {}
    for row in root.iter("Exrate"):
        for field in ("Transfer", "Buy"):  # giá Vietcombank mua chuyển khoản, không có thì mua tiền mặt
            value = (row.get(field) or "").replace(",", "").strip()
            if value and value != "-":
                rates[row.get("CurrencyCode")] = float(value)
                break
    return rates


SOURCES = {  # loại: (hàm lấy giá theo danh sách mã, số phút còn dùng được giá đã lưu)
    "cp": (stock_prices, 5), "etf": (stock_prices, 5), "vang": (gold_table, 30), "quy": (fund_navs, 120), "coin": (coin_prices, 30),
    "ngoaite": (fx_rates, 60)}


def prices(kind, codes, fresh=False):
    """(giá {mã: đồng}, lúc cập nhật, có phải giá cũ do nguồn lỗi). fresh=True thì bỏ qua giá đã lưu."""
    codes = sorted(set(codes))
    if not codes:
        return {}, None, False
    fetch, minutes = SOURCES[kind]
    key = f"chitieu:gia:{kind}"
    store = kho.get(key, {}) or {}
    saved, when = store.get("gia", {}), store.get("luc")
    if not fresh and when and all(c in saved for c in codes) and \
            (now_vn() - datetime.fromisoformat(when)).total_seconds() < minutes * 60:
        return saved, when, False
    try:
        got = fetch(codes)  # mã nguồn không có (mã sai) thì không có trong got; không phải lỗi nguồn
        when = now_vn().isoformat(timespec="minutes")
        saved = {**saved, **got}
        kho.put(key, {"gia": saved, "luc": when})
        return saved, when, False
    except Exception as e:
        print(f"[lỗi] giá {kind}: {e!r}", file=sys.stderr)
        return saved, when, True


# ---- Định giá -------------------------------------------------------------------------

def add_months(d, months):
    m = d.month - 1 + months
    year, month = d.year + m // 12, m % 12 + 1
    return date(year, month, min(d.day, monthrange(year, month)[1]))


def accrued(it, day):
    """(lãi tới hôm nay hoặc tới ngày đáo hạn, ngày đáo hạn hoặc None nếu không kỳ hạn) của sổ tiết kiệm."""
    start = date.fromisoformat(it["ngay"])
    maturity = add_months(start, it["ky"]) if it.get("ky") else None
    end = min(day, maturity) if maturity else day
    return it["tien"] * it["lai"] / 100 * max((end - start).days, 0) / 365, maturity


def gold_name(kind):
    return "Miếng SJC" if kind == "sjc" else "Nhẫn"


def valuation(day, fresh=False):
    """Định giá mọi tài sản: dict gồm các dòng theo loại, tổng tài sản, tổng nợ, tài sản ròng, ghi chú giá."""
    data = load()
    items, gold = data["items"], kho.get(K_GOLD, []) or []
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
        if kind in ("tien", "khac", "no"):
            rows.append((kind, rid, it["ten"], it["tien"], None, ""))
        elif kind == "tietkiem":
            interest, maturity = accrued(it, day)
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
    for i, g in enumerate(gold):
        price = quotes.get("vang", {}).get(g["loai"])
        value = g["luong"] * price if price else 0
        cost = g["luong"] * g["gia"] * 1e6 if g.get("gia") else None
        rows.append(("vang", f"v{i}", gold_name(g["loai"]), value, cost, gold_amount(g["luong"])))
    assets = sum(r[3] for r in rows if r[0] != "no")
    debts = sum(r[3] for r in rows if r[0] == "no")
    return {"rows": rows, "assets": assets, "debts": debts, "net": assets - debts, "notes": notes,
            "lailo": data.get("lailo", [])}


def snapshot(day, v):
    """Lưu tài sản ròng của ngày (để xem tăng giảm theo thời gian, vẽ biểu đồ)."""
    kinds = {}
    for kind, _, _, value, _, _ in v["rows"]:
        kinds[kind] = kinds.get(kind, 0) + value
    kho.command("HSET", K_HISTORY, day.isoformat(), json.dumps({"rong": round(v["net"]), "loai": {
        k: round(x) for k, x in kinds.items()}}))


def history():
    flat = kho.command("HGETALL", K_HISTORY) or []
    return sorted((k, json.loads(v)) for k, v in zip(flat[::2], flat[1::2]))


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


# ---- /taisan ---------------------------------------------------------------------------

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
FX_CODES = {"usd", "eur", "jpy", "gbp", "aud", "cad", "chf", "cny", "sgd", "krw", "thb", "hkd", "twd"}


def number(text):
    """'1.000' -> 1000; '0,05' -> 0.05; '95,5' -> 95.5."""
    text = text.strip()
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", text):
        return float(text.replace(".", ""))
    return float(text.replace(",", "."))


def stock_price(text):
    """Giá cổ phiếu/ccq: '95' hay '95k' là 95.000đ, '95500' là 95.500đ."""
    text = text.lower().rstrip("kđ")
    value = number(text)
    return value * 1000 if value < 1000 else value


def money_and_name(args):
    """'VCB 25tr' -> ('VCB', 25000000); None nếu không có số tiền."""
    text = " ".join(args)
    found = ct.parse_amount(text)
    if not found:
        return None
    amount, start, end = found
    name = " ".join((text[:start] + " " + text[end:]).split()).strip(" ,.:-") or "Chưa đặt tên"
    return name[:30], amount


def same_name(a, b):
    return ct.plain(a).strip() == ct.plain(b).strip()


def add_simple(data, kind, args):
    got = money_and_name(args)
    if not got:
        return None
    name, amount = got
    for it in data["items"]:
        if it["loai"] == kind and same_name(it["ten"], name):  # cùng tên: cập nhật
            it.update(tien=amount, ngay=ct.today().isoformat())
            return f"✅ Đã cập nhật {TYPES[kind]}: {html.escape(name)} {ct.vnd(amount)}"
    data["items"].append({"id": new_id(data), "loai": kind, "ten": name, "tien": amount,
                          "ngay": ct.today().isoformat()})
    return f"✅ Đã thêm {TYPES[kind]}: {html.escape(name)} {ct.vnd(amount)}"


def add_saving(data, args):
    text = " ".join(args)
    bare = ct.plain(text)
    rate = re.search(r"(\d+(?:[.,]\d+)?)\s*%", text)
    term = re.search(r"(?<!\w)(\d{1,2})\s*(?:thang|th|t)(?!\w)", bare)
    when = re.search(r"(?<![\d/])(\d{1,2})/(\d{1,2})(?:/(\d{4}))?(?![\d/])", text)
    rest = text
    for m in (rate, when):
        if m:
            rest = rest.replace(m[0], " ")
    if term:  # bỏ "6 tháng" ở chữ gốc (cùng vị trí với chữ đã bỏ dấu)
        rest = re.sub(r"(?<!\w)\d{1,2}\s*(?:tháng|thang|th|t)(?!\w)", " ", rest, count=1, flags=re.IGNORECASE)
    rest = re.sub(r"(?i)không kỳ hạn|khong ky han|kkh", " ", rest)
    got = money_and_name(rest.split())
    if not got or not rate:
        return None
    name, amount = got
    start = ct.today()
    if when:
        try:
            start = date(int(when[3]) if when[3] else start.year, int(when[2]), int(when[1]))
        except ValueError:
            return None
    months = 0 if re.search(r"khong ky han|kkh", bare) or not term else int(term[1])
    return add_saving_item(data, name, amount, number(rate[1]), months, start)


def add_saving_item(data, name, amount, rate, months, start):
    """Thêm một sổ tiết kiệm (chưa lưu): tên, tiền gốc, lãi %/năm, kỳ hạn tháng (0 là không kỳ hạn), ngày gửi."""
    data["items"].append({"id": new_id(data), "loai": "tietkiem", "ten": name[:30], "tien": amount,
                          "lai": rate, "ky": months, "ngay": start.isoformat()})
    due = f", đáo hạn {add_months(start, months):%d/%m/%Y}" if months else ", không kỳ hạn"
    return f"✅ Đã thêm sổ tiết kiệm {html.escape(name[:30])} {ct.vnd(amount)}, lãi {qty_text(rate)}%/năm{due}"


def is_etf(code):
    """Mã chứng chỉ quỹ ETF trên HOSE: E1VFVN30 (DCVFMVN30 của Dragon Capital), FUEVFVND, FUESSVFL..."""
    return code.upper().startswith(("E1VF", "FUE"))


def add_holding(data, kind, args):
    """cp/etf/quy/coin: mã, số lượng, giá vốn (không bắt buộc với coin). Mã đã có thì ghi đè (khai báo lại)."""
    if len(args) < 2 or (kind != "coin" and len(args) < 3):
        return None
    code = args[0].upper() if kind != "coin" else args[0].lower()
    try:
        qty = number(args[1])
        cost = (stock_price(args[2]) if kind in ("cp", "etf", "quy") else number(args[2])) if len(args) > 2 else None
    except ValueError:
        return None
    if qty <= 0:
        return None
    if kind in ("cp", "etf"):
        if not re.fullmatch(r"[A-Z0-9]{3,8}", code):
            return None
        kind = "etf" if is_etf(code) else "cp"  # "/taisan cp E1VFVN30 ..." cũng vào ETF
        listed, _, stale = prices(kind, [code])
        if code not in listed and not stale:
            return f"Không thấy mã {html.escape(code)} trên sàn"
    data["items"] = [it for it in data["items"] if not (it["loai"] in (kind, "cp", "etf") and it["ma"] == code)]
    data["items"].append({"id": new_id(data), "loai": kind, "ma": code, "sl": qty, "gia_von": cost})
    return (f"✅ Đã khai báo {TYPES[kind]} {html.escape(code.upper())}: {qty_text(qty)}"
            + (f", giá vốn {ct.vnd(cost)}" if cost else ""))


def add_fx(data, code, args):
    try:
        qty = number(args[0])
    except (IndexError, ValueError):
        return None
    code = code.upper()
    data["items"] = [it for it in data["items"] if not (it["loai"] == "ngoaite" and it["ma"] == code)]
    data["items"].append({"id": new_id(data), "loai": "ngoaite", "ma": code, "sl": qty, "gia_von": None})
    return f"✅ Đã khai báo ngoại tệ {code}: {qty_text(qty)}"


def add_gold(args):
    import lenh  # dùng chung cách nhập của /vivang bên bot bản tin
    try:
        kind = lenh.KINDS[args[0].lower()]
        taels = number(args[1]) * lenh.UNITS[args[2].lower()]
        paid = number(args[3]) if len(args) > 3 else None
    except (KeyError, IndexError, ValueError):
        return None
    if not 0 < taels <= 1000:
        return None
    items = kho.get(K_GOLD, []) or []
    items.append({"loai": kind, "luong": taels, "gia": paid})
    kho.put(K_GOLD, items)
    return f"✅ Đã thêm {lenh.amount_text(taels)} {gold_name(kind).lower()} vào ví vàng (dùng chung với bot bản tin)"


ALIASES = {"tien": "tien", "taikhoan": "tien", "tk": "tien", "vi": "tien", "tietkiem": "tietkiem", "so": "tietkiem",
           "sotietkiem": "tietkiem", "cp": "cp", "cophieu": "cp", "etf": "etf", "chungchiquy": "etf", "quy": "quy", "ccq": "quy", "vang": "vang",
           "coin": "coin", "crypto": "coin", "khac": "khac", "nha": "khac", "xe": "khac", "no": "no", "vay": "no"}


def taisan(args):
    if not kho.ready():
        return ct.NEED_STORE
    word = ct.plain(args[0]) if args else ""
    if word in ("xoa", "sua"):
        return edit_list()
    if word in ("bieudo", "bd"):
        return chart_reply(ct.today())
    if word in ("huongdan", "help", "?"):
        return USAGE
    kind = ALIASES.get(word) or ("ngoaite" if word in FX_CODES else None)
    if not args:
        return overview(ct.today())
    if not kind:
        return USAGE
    data = load()
    rest = args[1:]
    if kind == "vang":
        result = add_gold(rest)
    elif kind == "tietkiem":
        result = add_saving(data, rest)
    elif kind in ("cp", "etf", "quy", "coin"):
        result = add_holding(data, kind, rest)
    elif kind == "ngoaite":
        result = add_fx(data, word, rest)
    else:
        result = add_simple(data, kind, rest)
    if not result:
        return USAGE
    if result.startswith("✅") and kind != "vang":
        save(data)
    return result + "\nXem tổng: /taisan"


def overview(day, fresh=False):
    v = valuation(day, fresh)
    if not v["rows"]:
        return USAGE
    lines = [f"💼 <b>Tài sản ròng: {ct.vnd(round(v['net']))}</b>{compare_line(day, v['net'])}",
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
            head += f" · {'lãi' if gain >= 0 else 'lỗ'} {short(abs(gain))}" + (
                f" ({gain / base * 100:+.1f}%)".replace(".", ",") if base else "")
        elif kind == "tietkiem":
            head += f" · lãi tới nay {short(sum(r[3] - r[4] for r in rows))}"
        lines.append(head)
        for _, _, name, value, cost, detail in rows:
            line = f"  • {html.escape(name)}: {short(value)}"
            if detail:
                line += f" · {html.escape(detail)}"
            if cost and kind != "tietkiem" and "chưa có giá" not in detail:
                line += f" ({(value - cost) / cost * 100:+.0f}%)"
            lines.append(line)
    realized = [x for x in v["lailo"] if x["ngay"][:4] == str(day.year)]
    if realized:
        total = sum(x["lai"] for x in realized)
        lines.append(f"\n💰 Lãi/lỗ đã chốt năm {day.year}: <b>{'+' if total >= 0 else '−'}{ct.vnd(round(abs(total)))}</b>"
                     f" ({len(realized)} lần bán)")
    lines += [f"<i>⚠️ {html.escape(n)}</i>" for n in v["notes"]]
    lines.append("<i>Cổ phiếu theo giá khớp gần nhất, vàng theo giá cửa hàng mua vào, ngoại tệ theo giá Vietcombank "
                 "mua chuyển khoản</i>")
    snapshot(day, v)
    return "\n".join(lines), BUTTONS


def edit_list():
    v = valuation(ct.today())
    if not v["rows"]:
        return USAGE
    lines = ["🗂 <b>Bấm ❌ để xóa</b> (sửa: khai báo lại cùng tên/mã là được cập nhật)"]
    buttons = []
    for i, (kind, rid, name, value, _, _) in enumerate(v["rows"], 1):
        lines.append(f"{i}. {TYPES[kind].split()[0]} {html.escape(name)}: {short(value)}")
        buttons.append((f"❌ {i}", f"ts:x:{rid}"))
    return "\n".join(lines), [buttons[i:i + 5] for i in range(0, len(buttons), 5)] + [[("↩️ Xong", "ts:xem")]]


def remove(rid):
    if rid.startswith("v"):
        items = kho.get(K_GOLD, []) or []
        index = int(rid[1:])
        if index < len(items):
            items.pop(index)
            kho.put(K_GOLD, items)
            return True
        return False
    data = load()
    kept = [it for it in data["items"] if str(it["id"]) != rid]
    if len(kept) == len(data["items"]):
        return False
    data["items"] = kept
    save(data)
    return True


def chart_reply(day):
    v = valuation(day)
    sums = {}
    for kind, _, _, value, _, _ in v["rows"]:
        if kind != "no" and value > 0:
            sums[kind] = sums.get(kind, 0) + value
    if not sums:
        return "Chưa có tài sản nào để vẽ. " + USAGE
    order = sorted(sums.items(), key=lambda x: -x[1])
    colors = {k: pt.PALETTE[i] for i, k in enumerate(TYPES)}
    pie = {"type": "doughnut", "data": {
        "labels": [f"{TYPES[k].split(' ', 1)[1]} {pt.short(x)} ({x / v['assets'] * 100:.0f}%)" for k, x in order],
        "datasets": [{"data": [round(x) for _, x in order], "backgroundColor": [colors[k] for k, _ in order]}]},
        "options": {"plugins": {"datalabels": {"display": False}, "legend": {"position": "right", "labels": {"font": {"size": 16}}},
                                "title": {"display": True, "font": {"size": 22},
                                          "text": f"Tài sản ròng {ct.vnd(round(v['net']))}"}}}}
    try:
        images = [pt.chart_png(pie)]
        past = history()
        if len(past) >= 2:
            line = {"type": "line", "data": {"labels": [f"{k[8:]}/{k[5:7]}" for k, _ in past],
                                             "datasets": [{"label": "Tài sản ròng (triệu đồng)", "fill": True,
                                                           "data": [round(x["rong"] / 1e6, 1) for _, x in past],
                                                           "borderColor": "#2f9e44", "backgroundColor": "#2f9e4433"}]},
                    "options": {"locale": "vi-VN", "plugins": {"datalabels": {"display": False}, "title": {
                        "display": True, "font": {"size": 20}, "text": "Tài sản ròng theo thời gian (triệu đồng)"}}}}
            images.append(pt.chart_png(line, 900, 450))
    except Exception as e:
        print(f"[lỗi] vẽ biểu đồ tài sản: {e!r}", file=sys.stderr)
        return "⚠️ Chưa vẽ được biểu đồ (dịch vụ vẽ không trả lời), thử lại sau"
    return {"photos": images, "caption": f"💼 <b>Tài sản ròng</b>: {ct.vnd(round(v['net']))}"}


# ---- Mua bán cổ phiếu bằng tin nhắn ----------------------------------------------------

TRADE = re.compile(r"^\s*(mua|ban)\s+(\d[\d.,]*)\s*(?:cp|ccq|co phieu|cổ phiếu|chung chi quy)?\s+([A-Za-z0-9]{3,8})\s*"
                   r"(?:gia|giá|@)?\s*"
                   r"(\d[\d.,]*)\s*(k|nghin|nghìn|đ|d|dong|đồng)?\s*$", re.IGNORECASE)


def parse_trade(text):
    """'bán 500 FPT giá 120' -> ("ban", 500, "FPT", 120000); None nếu không phải lệnh mua bán cổ phiếu."""
    if "\n" in text.strip():
        return None
    m = TRADE.match(ct.plain(text))
    if not m:
        return None
    try:
        qty, price = number(m[2]), stock_price(m[4])
    except ValueError:
        return None
    raw_code = re.search(rf"(?i)(?<![\w]){m[3]}(?![\w])", text)
    code = m[3].upper()
    looks_like_stock = (raw_code and raw_code[0].isupper()) or re.search(r"(?i)\b(gia|giá|cp|cổ phiếu|co phieu)\b", text)
    if not looks_like_stock or qty <= 0 or not qty.is_integer():
        return None
    return m[1].lower(), int(qty), code, price


def broker_cash(data):
    """Tài khoản tiền tên có chữ DNSE (tiền chờ trong tài khoản chứng khoán), None nếu chưa khai báo."""
    return next((it for it in data["items"] if it["loai"] == "tien" and "dnse" in ct.plain(it["ten"])), None)


def trade(text, now):
    """Xử lý tin mua/bán cổ phiếu; None nếu tin không phải mua bán cổ phiếu (để ghi như khoản chi thường)."""
    found = parse_trade(text)
    if not found:
        return None
    side, qty, code, price = found
    data = load()
    kind = "etf" if is_etf(code) else "cp"
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
            holding = {"id": new_id(data), "loai": kind, "ma": code, "sl": qty, "gia_von": paid / qty}
            data["items"].append(holding)
        lines = [f"📈 Đã mua {vn_num(qty, 0)} {code} giá {ct.vnd(price)}: <b>{ct.vnd(round(paid))}</b>"
                 + (" (DNSE miễn phí giao dịch)" if not BROKER_FEE else ""),
                 f"Đang giữ {vn_num(holding['sl'], 0)} {code}, giá vốn {ct.vnd(round(holding['gia_von']))}"]
        if cash:
            cash["tien"] -= round(paid)
            lines.append(f"🏦 Tiền tài khoản {html.escape(cash['ten'])}: còn {ct.vnd(cash['tien'])}")
        save(data)
        return "\n".join(lines + ["<i>Mua cổ phiếu là đổi tiền sang tài sản, không tính là khoản chi</i>"])
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
    lines = [f"💰 Đã bán {vn_num(qty, 0)} {code} giá {ct.vnd(price)}: {ct.vnd(round(value))}",
             f"Thuế 0,1%: −{ct.vnd(round(tax))}" + (f" · phí: −{ct.vnd(round(fee))}" if fee else "")
             + f" → tiền về <b>{ct.vnd(round(received))}</b>",
             f"Giá vốn {ct.vnd(round(holding.get('gia_von') or price))} → "
             + (f"<b>lãi {ct.vnd(round(gain))}</b>" if gain >= 0 else f"<b>lỗ {ct.vnd(round(-gain))}</b>")
             + f" ({gain / cost * 100:+.1f}%)".replace(".", ",")]
    if gain > 0:  # phần lãi là thu nhập đầu tư; phần vốn chỉ là đổi cổ phiếu ra tiền
        entry = {"id": kho.command("INCR", ct.K_COUNTER), "ngay": now.date().isoformat(), "gio": now.strftime("%H:%M"),
                 "tien": round(gain), "ghichu": f"lãi bán {qty} {code}", "nhom": ct.INCOME}
        ct.save(entry)
        lines.append("Đã ghi phần lãi vào 💰 Thu nhập (đầu tư)")
    lines.append(f"Còn giữ {vn_num(holding['sl'], 0)} {code}" if holding["sl"] else f"Đã bán hết {code}")
    if cash:
        cash["tien"] += round(received)
        lines.append(f"🏦 Tiền tài khoản {html.escape(cash['ten'])}: {ct.vnd(cash['tien'])}")
    save(data)
    return "\n".join(lines)


# ---- Nhắc lương ------------------------------------------------------------------------

def luong(args):
    if not kho.ready():
        return ct.NEED_STORE
    usage = ("Nhắc ngày nhận lương: /luong 10 25tr (ngày 10 hằng tháng, 25 triệu)\nTới ngày, bot hỏi đã nhận chưa, "
             "bấm một nút là ghi vào Thu nhập. Bỏ nhắc: /luong xoa")
    if not args:
        s = kho.get(K_SALARY)
        return (f"💼 Đang nhắc lương ngày {s['ngay']} hằng tháng, {ct.vnd(s['tien'])}\n" + usage) if s else usage
    if ct.plain(args[0]) == "xoa":
        kho.delete(K_SALARY)
        return "Đã bỏ nhắc lương"
    found = ct.parse_amount(" ".join(args[1:])) if len(args) > 1 else None
    if not args[0].isdigit() or not 1 <= int(args[0]) <= 31 or not found:
        return usage
    kho.put(K_SALARY, {"ngay": int(args[0]), "tien": found[0]})
    return f"✅ Ngày {int(args[0])} hằng tháng bot sẽ hỏi đã nhận lương {ct.vnd(found[0])} chưa"


def salary_due(day):
    """(tin nhắc, nút) nếu hôm nay trong 3 ngày từ ngày lương mà tháng này chưa ghi lương; None nếu không."""
    s = kho.get(K_SALARY)
    if not s:
        return None
    payday = min(s["ngay"], monthrange(day.year, day.month)[1])
    if not 0 <= day.day - payday <= 3:
        return None
    month = ct.between(day.replace(day=1), day)
    if any(e["nhom"] == ct.INCOME and "luong" in ct.plain(e["ghichu"]) for e in month):
        return None
    return (f"💼 Hôm nay {'là ngày nhận lương' if day.day == payday else f'đã qua ngày lương {payday}'}. Đã nhận chưa?",
            [[(f"✅ Đã nhận {pt.short(s['tien'])}", f"ts:luong:{s['tien']}"), ("Chưa", "ts:chua")]])


def maturity_notes(day):
    """Sổ tiết kiệm đáo hạn trong 3 ngày tới (mỗi sổ nhắc một lần)."""
    notes = []
    for it in load()["items"]:
        if it["loai"] == "tietkiem" and it.get("ky"):
            interest, maturity = accrued(it, day)
            if 0 <= (maturity - day).days <= 3 and kho.put_new(f"chitieu:nhac:daohan:{it['id']}:{maturity}", True,
                                                               10 * 86400):
                notes.append(f"🐷 Sổ {html.escape(it['ten'])} {short(it['tien'])} đáo hạn ngày {maturity:%d/%m}"
                             f" (lãi khoảng {short(interest)}): nhớ tất toán hoặc gửi tiếp, rồi cập nhật /taisan")
    return notes


# ---- Khám sức khỏe tài chính -----------------------------------------------------------

def monthly_flows(day):
    """(chi trung bình/tháng, thu trung bình/tháng, số ngày có dữ liệu) trong tối đa 90 ngày qua."""
    items = ct.between(day - timedelta(days=89), day)
    if not items:
        return 0, 0, 0
    days = (day - date.fromisoformat(min(e["ngay"] for e in items))).days + 1
    spend = sum(e["tien"] for e in items if e["nhom"] != ct.INCOME)
    income = sum(e["tien"] for e in items if e["nhom"] == ct.INCOME)
    return spend / days * 30.4, income / days * 30.4, days


def health_checks(day):
    """[(điểm 0–20 hoặc None nếu thiếu dữ liệu, dấu, dòng mô tả)] và dữ liệu thô cho AI."""
    v = valuation(day)
    spend, income, days = monthly_flows(day)
    checks = []
    kinds = {}
    for kind, _, _, value, _, _ in v["rows"]:
        kinds[kind] = kinds.get(kind, 0) + value
    liquid = kinds.get("tien", 0) + kinds.get("tietkiem", 0)
    fund = None
    if any(it.get("duphong") for it in load()["items"]):  # đã lập quỹ dự phòng: dùng đúng số liệu của quỹ
        try:
            import duphong
            fund = duphong.status(day)
        except Exception as e:
            print(f"[lỗi] quỹ dự phòng trong khám sức khỏe: {e!r}", file=sys.stderr)
    if fund and fund["monthly"]:
        months = fund["covered"]
        score = 20 if months >= 6 else 15 if months >= 3 else 8 if months >= 1 else 0
        checks.append((score, "✅" if months >= 3 else "⚠️" if months >= 1 else "🚨",
                       f"Quỹ dự phòng: {vn_num(months, 1)} tháng chi thiết yếu (quỹ {short(fund['balance'])}, chi thiết "
                       f"yếu {short(fund['monthly'])}/tháng) · mục tiêu {fund['months']} tháng: /duphong"))
    elif spend and v["rows"] and days >= 14:  # ít ngày quá thì một khoản lớn làm sai cả tháng
        months = liquid / spend
        score = 20 if months >= 6 else 15 if months >= 3 else 8 if months >= 1 else 0
        checks.append((score, "✅" if months >= 3 else "⚠️" if months >= 1 else "🚨",
                       f"Quỹ dự phòng: {vn_num(months, 1)} tháng chi tiêu (tiền + tiết kiệm {short(liquid)}, chi TB "
                       f"{short(spend)}/tháng) · nên 3–6 tháng"))
    else:
        checks.append((None, "❔", "Quỹ dự phòng: chưa tính được (cần khai báo tiền, tiết kiệm bằng /taisan và ghi chi tiêu "
                                  "ít nhất 2 tuần)"))
    if income and days >= 20:
        rate = (income - spend) / income * 100
        score = 20 if rate >= 30 else 16 if rate >= 20 else 10 if rate >= 10 else 5 if rate >= 0 else 0
        checks.append((score, "✅" if rate >= 20 else "⚠️" if rate >= 0 else "🚨",
                       f"Để dành: {rate:.0f}% thu nhập ({days} ngày qua: thu TB {short(income)}/tháng, chi "
                       f"{short(spend)}/tháng) · nên từ 20%"))
    else:
        checks.append((None, "❔", "Để dành: chưa tính được (cần ghi thu nhập, ví dụ + lương 20tr, và ít nhất 20 ngày dữ liệu)"))
    if v["assets"]:
        import sono  # nợ: chấm theo tiền trả mỗi tháng so với thu nhập, tách nợ không lãi
        checks.append(sono.health_check(day, v, income if income and days >= 20 else None))
        warnings = []
        for kind, _, name, value, _, _ in v["rows"]:
            if kind in ("cp", "quy", "coin") and value / v["assets"] > 0.2:
                warnings.append(f"{html.escape(name)} chiếm {value / v['assets'] * 100:.0f}% tài sản")
        if kinds.get("coin", 0) / v["assets"] > 0.1:
            warnings.append(f"tiền số chiếm {kinds['coin'] / v['assets'] * 100:.0f}% (biến động rất mạnh)")
        top = max(((k, x) for k, x in kinds.items() if k != "no"), key=lambda x: x[1], default=None)
        if top and top[1] / v["assets"] > 0.7 and len(v["rows"]) > 1:
            warnings.append(f"{TYPES[top[0]].split(' ', 1)[1].lower()} chiếm {top[1] / v['assets'] * 100:.0f}% tài sản")
        score = 20 if not warnings else 12 if len(warnings) == 1 else 5
        checks.append((score, "✅" if not warnings else "⚠️", "Phân bổ: " + ("không dồn quá nhiều vào một chỗ"
                                                                          if not warnings else "; ".join(warnings))))
        losers = [f"{html.escape(name)} {(value - cost) / cost * 100:.0f}%" for kind, _, name, value, cost, _ in v["rows"]
                  if kind in ("cp", "etf", "quy", "coin", "vang") and cost and value and (value - cost) / cost <= -0.2]
        trend = compare_line(day, v["net"])
        score = 20 if not losers else 10
        checks.append((score, "✅" if not losers else "⚠️",
                       ("Lỗ sâu (từ 20%): " + ", ".join(losers) if losers else "Không khoản đầu tư nào lỗ sâu")
                       + (f" · tài sản ròng{trend}" if trend else "")))
    else:
        checks.append((None, "❔", "Nợ, phân bổ tài sản: chưa có dữ liệu (khai báo bằng /taisan)"))
    return checks, v, (spend, income, days)


def health(day):
    if not kho.ready():
        return ct.NEED_STORE
    checks, v, (spend, income, days) = health_checks(day)
    scored = [c for c in checks if c[0] is not None]
    if not scored:
        return "🩺 Chưa đủ dữ liệu để khám. " + USAGE
    score = round(sum(c[0] for c in scored) / (20 * len(scored)) * 100)
    label = "Tốt" if score >= 80 else "Khá" if score >= 60 else "Cần chú ý" if score >= 40 else "Yếu"
    lines = [f"🩺 <b>Khám sức khỏe tài chính: {score}/100 ({label})</b>"] + [f"{mark} {text}" for _, mark, text in checks]
    if v["rows"]:
        lines.insert(1, f"Tài sản ròng {short(v['net'])}" + (f" · nợ {short(v['debts'])}" if v["debts"] else ""))
    advice = []
    if ct.ai_key():
        facts = re.sub(r"<[^>]+>", "", html.unescape("\n".join(lines)))
        system = ("Bạn là trợ lý khám sức khỏe tài chính cá nhân, viết tiếng Việt có dấu, ngắn gọn, xưng \"bạn\". "
                  "Chỉ dựa vào số liệu được cho, không bịa số. Không khuyên mua hay bán mã cổ phiếu, quỹ, tiền số cụ "
                  "thể nào và không dự đoán giá. Trả lời không markdown: 2 dòng bắt đầu bằng \"• \" là nhận xét quan "
                  "trọng nhất; 2–3 dòng bắt đầu bằng \"✅ \" là việc nên làm cụ thể có con số (ví dụ để dành thêm "
                  "3tr/tháng thì sau 8 tháng đủ quỹ dự phòng 6 tháng).")
        try:
            answer, _ = ct.ai_chat(system, facts)
            for raw in answer.splitlines():
                raw = raw.strip()
                if raw.startswith(("•", "✅")) and len(advice) < 5:
                    advice.append(html.escape(raw))
        except Exception as e:
            print(f"[lỗi] AI khám sức khỏe: {e!r}", file=sys.stderr)
    if advice:
        lines += ["", "🤖 <b>Nhận xét và việc nên làm</b>"] + advice
    elif ct.ai_key():
        lines += ["", "<i>AI đang bận nên chưa có nhận xét, thử lại sau: /suckhoe</i>"]
    return "\n".join(lines + [NOT_ADVICE])


# ---- Nút bấm ---------------------------------------------------------------------------

def on_button(arg, message, now):
    """Nút "ts:...": (thông báo nhỏ, việc tiếp theo) như sochitieu.on_button."""
    day = now.date()
    if arg == "xem":
        return "Đang cập nhật giá…", ("edit", lambda: overview(day, fresh=True))
    if arg == "bd":
        return "Đang vẽ biểu đồ…", ("send", lambda: chart_reply(day))
    if arg == "sk":
        return "Đang khám, chờ chút…", ("send", lambda: health(day))
    if arg == "ds":
        return None, ("edit", edit_list)
    if arg == "hd":
        return None, ("send", lambda: USAGE)
    if arg.startswith("x:"):
        gone = remove(arg[2:])
        return ("Đã xóa" if gone else "Mục này đã xóa rồi"), ("edit", edit_list)
    if arg.startswith("luong:"):
        amount = int(arg[6:])
        entry = {"id": kho.command("INCR", ct.K_COUNTER), "ngay": day.isoformat(), "gio": now.strftime("%H:%M"),
                 "tien": amount, "ghichu": f"lương tháng {day.month}", "nhom": ct.INCOME}
        ct.save(entry)
        done = f"✅ Đã ghi lương tháng {day.month}: {ct.vnd(amount)} vào 💰 Thu nhập"
        hint = ct.salary_fund_hint([entry], day)  # gợi ý chia lương: trả nợ, chi tiêu, quỹ dự phòng
        return "Đã ghi lương", ("edit", lambda: (done + "\n" + hint[0], [hint[1]]) if hint else done)
    if arg == "chua":
        return "Mai bot hỏi lại", ("edit", lambda: "Chưa nhận lương: mai bot hỏi lại (tối đa 3 ngày)")
    return None, None
