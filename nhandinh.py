"""Nhận định trong phiên cho bot bản tin: ngành hút tiền, khuyến nghị của các công ty chứng khoán (CTCK), tin tài
chính, rồi AI (Gemini, dùng chung cấu hình AI với bot chi tiêu) tổng hợp thành vài dòng.

Nguồn (thử ngày 05/11/2026):
- Khuyến nghị CTCK: VNDirect finfo (HSC, VNDirect, UBS, Yuanta, Vietcap, MBS...), có giá mục tiêu; ~100 khuyến
  nghị mỗi 30 ngày.
- Ngành: phân ngành ICB cấp 3 của VNDirect; giá, giá trị giao dịch, khối ngoại của ~430 mã HOSE từ Vietcap.
- Tin: RSS CafeF, Vietstock (cổ phiếu, nhận định thị trường, phân tích cơ bản), VnExpress kinh doanh.

Mọi con số do code tính. AI chỉ được dùng dữ liệu đưa vào; dòng nào nhắc mã không có trong dữ liệu thì bị bỏ.
Đây là thông tin tổng hợp để tham khảo, không phải lời khuyên đầu tư.
"""
import html
import re
import sys
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import chungkhoan
import kho
from bantin import VN_TZ, vn_num

FINFO = "https://api-finfo.vndirect.com.vn/v4"
FEEDS = [("CafeF", "https://cafef.vn/thi-truong-chung-khoan.rss"),
         ("CafeF", "https://cafef.vn/doanh-nghiep.rss"),
         ("Vietstock", "https://vietstock.vn/830/chung-khoan/co-phieu.rss"),
         ("Vietstock", "https://vietstock.vn/1636/nhan-dinh-phan-tich/nhan-dinh-thi-truong.rss"),
         ("Vietstock", "https://vietstock.vn/582/nhan-dinh-phan-tich/phan-tich-co-ban.rss"),
         ("VnExpress", "https://vnexpress.net/rss/kinh-doanh.rss")]
RATING = {"BUY": "MUA", "STRONG_BUY": "MUA MẠNH", "OUTPERFORM": "KHẢ QUAN", "ADD": "TĂNG TỶ TRỌNG",
          "ACCUMULATE": "TÍCH LŨY", "HOLD": "GIỮ", "NEUTRAL": "TRUNG LẬP", "UNDERPERFORM": "KÉM KHẢ QUAN",
          "REDUCE": "GIẢM TỶ TRỌNG", "SELL": "BÁN"}
SHORT_NAMES = {"Dịch vụ Đầu tư Bất Động Sản": "Bất động sản", "Ga, nước & dịch vụ công cộng gia dụng": "Tiện ích",
               "Dược phẩm & công nghệ sinh học": "Dược phẩm", "Dụng cụ, dịch vụ & Phân phối Dầu": "Dịch vụ dầu khí",
               "Phần mềm & Dịch vụ máy tính": "Công nghệ thông tin", "Dịch vụ tài chính": "Chứng khoán, tài chính",
               "Kim loại công nghiệp": "Thép, kim loại", "Xây dựng & Vật liệu": "Xây dựng, vật liệu",
               "Giao thông công nghiệp": "Vận tải, cảng", "Sản xuất thực phẩm": "Thực phẩm",
               "Dụng cụ điện & Điện tử": "Thiết bị điện", "Sản xuất dầu khí": "Dầu khí"}
BUTTONS = [[("🔥 Ngành", "nd:nganh"), ("🎯 Khuyến nghị", "nd:kn"), ("📰 Tin", "nd:tin")],
           [("🔄 Cập nhật nhận định", "nd:moi")]]
NOT_ADVICE = ("<i>Tổng hợp tự động từ khuyến nghị của các CTCK (qua VNDirect), giá Vietcap, tin CafeF/Vietstock/"
              "VnExpress; AI có thể sai. Chỉ để tham khảo, không phải lời khuyên đầu tư.</i>")
SHORT_NOTE = "<i>🤖 AI tổng hợp từ khuyến nghị CTCK, giá, tin · tham khảo, không phải lời khuyên đầu tư</i>"
OFF = "nhandinh:tat"  # có khóa này thì không tự gửi nhận định trong phiên
TICKER = re.compile(r"(?<![A-Za-z0-9])[A-Z][A-Z0-9]{2}(?![A-Za-z0-9])")


def now_vn():
    return datetime.now(VN_TZ)


def remembered(key, seconds, fetch):
    """Dữ liệu ít đổi (danh sách ngành, mã HOSE, khuyến nghị): giữ trong kho một lúc; không có kho thì lấy luôn."""
    if kho.ready():
        try:
            saved = kho.get(key)
            if saved is not None:
                return saved
        except Exception as e:
            print(f"[lỗi] đọc kho {key}: {e!r}", file=sys.stderr)
    value = fetch()
    if kho.ready():
        try:
            kho.put(key, value, seconds)
        except Exception as e:
            print(f"[lỗi] ghi kho {key}: {e!r}", file=sys.stderr)
    return value


def industry_map():
    """{mã: tên ngành} theo phân ngành ICB cấp 3 của VNDirect (giữ 7 ngày)."""
    def fetch():
        rows = chungkhoan.get_json(f"{FINFO}/industry_classification?q=industryLevel:3&size=100")["data"]
        out = {}
        for r in rows:
            name = " ".join((r.get("vietnameseName") or "").split())
            for code in (r.get("codeList") or "").split(","):
                if code.strip():
                    out[code.strip()] = SHORT_NAMES.get(name, name)
        return out
    return remembered("nhandinh:nganh", 7 * 86400, fetch)


def hose_symbols():
    return remembered("nhandinh:hose", 86400, lambda: [x["symbol"] for x in chungkhoan.get_json(
        f"{chungkhoan.VCI}/getByGroup?group=HOSE")])


def recommendations(days=30):
    """{mã: [khuyến nghị mới nhất trước]} trong `days` ngày qua (giữ 3 giờ)."""
    since = (now_vn().date() - timedelta(days=days)).isoformat()

    def fetch():
        rows = chungkhoan.get_json(f"{FINFO}/recommendations?q=reportDate:gte:{since}&sort=reportDate:desc&size=500")
        out = {}
        for r in rows.get("data", []):
            out.setdefault(r["code"], []).append({k: r.get(k) for k in (
                "firm", "type", "reportDate", "reportPrice", "targetPrice", "avgTargetPrice")})
        return out
    return remembered(f"nhandinh:kn:{days}:{since}", 3 * 3600, fetch)


def text_of(node, tag):
    return re.sub(r"<[^>]+>", " ", html.unescape(node.findtext(tag) or "")).strip()


def feed(source, url):
    items = []
    for item in ET.fromstring(chungkhoan.get(url)).iter("item"):
        title = " ".join(text_of(item, "title").split())
        if title:
            items.append({"nguon": source, "tieu_de": title, "link": (item.findtext("link") or "").strip(),
                          "luc": chungkhoan.published_at(item.findtext("pubDate")),
                          "tom_tat": " ".join(text_of(item, "description").split())[:220]})
    return items


def news(hours=18):
    """Tin tài chính mới trong `hours` giờ qua, mới nhất trước, bỏ tin trùng tiêu đề."""
    with ThreadPoolExecutor(len(FEEDS)) as ex:
        results = list(ex.map(lambda f: safe(feed, *f), FEEDS))
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    seen, out = set(), []
    for item in sorted((x for r in results if r for x in r), key=lambda x: x["luc"] or cutoff, reverse=True):
        key = item["tieu_de"].lower()
        if key not in seen and (item["luc"] is None or item["luc"] >= cutoff):
            seen.add(key)
            out.append(item)
    return out[:40]


def safe(fn, *args):
    try:
        return fn(*args)
    except Exception as e:
        print(f"[lỗi] {fn.__name__}{args[:1]}: {e!r}", file=sys.stderr)
        return None


# ---- Tính số liệu --------------------------------------------------------------------

def board(quotes, names):
    """(các mã, các ngành) trong phiên. Ngành: % thay đổi theo vốn hóa, giá trị giao dịch, khối ngoại ròng."""
    stocks = []
    for code, q in quotes.items():
        if not q.get("ref") or not q.get("listed"):
            continue
        price = q["price"] or q["ref"]
        stocks.append({"ma": code, "nganh": names.get(code, "Khác"), "gia": price, "pct": (price / q["ref"] - 1) * 100,
                       "gtgd": q["value"] or 0, "nn": (q["f_buy"] or 0) - (q["f_sell"] or 0),
                       "von": q["listed"] * q["ref"], "von_nay": q["listed"] * price})
    sectors = {}
    for s in stocks:
        g = sectors.setdefault(s["nganh"], {"ten": s["nganh"], "von": 0, "von_nay": 0, "gtgd": 0, "nn": 0, "tang": 0,
                                           "giam": 0, "ma": []})
        g["von"] += s["von"]
        g["von_nay"] += s["von_nay"]
        g["gtgd"] += s["gtgd"]
        g["nn"] += s["nn"]
        g["tang"] += s["pct"] > 0
        g["giam"] += s["pct"] < 0
        g["ma"].append(s)
    rows = []
    for g in sectors.values():
        if g["ten"] == "Khác" or g["gtgd"] < 20e9:  # bỏ ngành quá ít giao dịch (dưới 20 tỷ)
            continue
        g["pct"] = (g["von_nay"] / g["von"] - 1) * 100 if g["von"] else 0
        g["ma"] = sorted(g["ma"], key=lambda s: -s["gtgd"])[:3]
        rows.append(g)
    return stocks, sorted(rows, key=lambda g: -g["pct"])


def rec_rows(recs, prices):
    """Mỗi mã có khuyến nghị: số CTCK, các CTCK, loại, giá mục tiêu TB, giá hiện tại, còn tăng (%)."""
    rows = []
    for code, items in recs.items():
        latest = items[0]
        target = (latest.get("avgTargetPrice") or latest.get("targetPrice") or 0) * 1000
        price = prices.get(code)
        rows.append({"ma": code, "so": len(items), "ctck": list(dict.fromkeys(i["firm"] for i in items))[:4],
                     "loai": RATING.get((latest.get("type") or "").upper(), latest.get("type") or ""),
                     "ngay": latest.get("reportDate") or "", "muc_tieu": target, "gia": price,
                     "con_tang": (target / price - 1) * 100 if target and price else None})
    return sorted(rows, key=lambda r: (-r["so"], -(r["con_tang"] or -999)))


def billions(x):
    return f"{vn_num(x / 1e9, 0)} tỷ"


def signed_billions(x):
    if abs(x) < 0.5e9:
        return "0 tỷ"
    return ("+" if x >= 0 else "−") + billions(abs(x))


def pct(x):
    return vn_num(x, 1, sign=True) + "%"


def gather(hours=18):
    """Lấy song song mọi dữ liệu cần cho nhận định."""
    with ThreadPoolExecutor(5) as ex:
        f_names = ex.submit(safe, industry_map)
        f_syms = ex.submit(safe, hose_symbols)
        f_index = ex.submit(safe, chungkhoan.index_rows)
        f_recs = ex.submit(safe, recommendations)
        f_news = ex.submit(safe, news, hours)
        names, syms = f_names.result() or {}, f_syms.result() or []
        quotes = safe(chungkhoan.quotes, syms) or {} if syms else {}
        recs = f_recs.result() or {}
        missing = [c for c in recs if c not in quotes]
        if missing:  # mã có khuyến nghị nhưng không ở HOSE (HNX, UPCoM)
            quotes_other = safe(chungkhoan.quotes, missing) or {}
        else:
            quotes_other = {}
        index = f_index.result() or {}
        items = f_news.result() or []
    stocks, sectors = board(quotes, names)
    prices = {c: (q["price"] or q["ref"]) for c, q in {**quotes_other, **quotes}.items() if q.get("ref")}
    return {"index": index, "stocks": stocks, "sectors": sectors, "recs": rec_rows(recs, prices), "news": items,
            "symbols": set(syms) | set(recs) | set(quotes_other)}


# ---- Hiển thị số liệu ----------------------------------------------------------------

def market_line(data):
    vni = data["index"].get("VN-Index")
    if not vni:
        return "VN-Index: chưa lấy được số liệu"
    point, ref, value, up, down, _ = vni
    return (f"VN-Index <b>{vn_num(point, 2)}</b> ({pct((point / ref - 1) * 100)}) · GTGD HOSE {billions(value)}"
            f" · ↑{up} ↓{down}")


def sector_lines(data, top=8, bottom=3):
    rows = data["sectors"]
    if not rows:
        return ["Chưa lấy được số liệu ngành"]

    def line(g):
        members = ", ".join(f"{s['ma']} {pct(s['pct'])}" for s in g["ma"])
        return (f"{'🟢' if g['pct'] > 0 else '🔴' if g['pct'] < 0 else '⚪'} <b>{html.escape(g['ten'])}</b> {pct(g['pct'])}"
                f" · {billions(g['gtgd'])} · NN {signed_billions(g['nn'])} · ↑{g['tang']} ↓{g['giam']}\n   {members}")
    lines = [line(g) for g in rows[:top]]
    if bottom and len(rows) > top:
        lines.append("…")
        lines += [line(g) for g in rows[max(top, len(rows) - bottom):]]
    money = sorted(rows, key=lambda g: -g["gtgd"])[:3]
    lines.append("💰 Hút tiền nhất: " + " · ".join(f"{html.escape(g['ten'])} {billions(g['gtgd'])}" for g in money))
    return lines


def rec_line(r):
    target = f"mục tiêu TB {vn_num(r['muc_tieu'], 0)}" if r["muc_tieu"] else "chưa có giá mục tiêu"
    now = f" · giá {vn_num(r['gia'], 0)}" if r["gia"] else ""
    upside = f" → còn {pct(r['con_tang'])}" if r["con_tang"] is not None else ""
    return (f"<b>{r['ma']}</b> {r['loai']} · {html.escape(', '.join(r['ctck']))} ({r['so']} lần, mới nhất "
            f"{r['ngay'][8:10]}/{r['ngay'][5:7]}) · {target}{now}{upside}")


def news_line(item, now=None):
    now = now or datetime.now(timezone.utc)
    ago = ""
    if item["luc"]:
        minutes = int((now - item["luc"]).total_seconds() // 60)
        ago = f" · {minutes // 60} giờ trước" if minutes >= 60 else f" · {max(minutes, 1)} phút trước"
    return f"• <a href=\"{html.escape(item['link'])}\">{html.escape(item['tieu_de'])}</a> ({item['nguon']}{ago})"


def nganh_text(data=None):
    data = data or gather()
    return "\n".join([f"🔥 <b>Ngành trên HOSE</b> · {now_vn():%H:%M %d/%m}", market_line(data),
                      "<i>% theo vốn hóa · giá trị giao dịch · khối ngoại ròng · số mã tăng/giảm</i>"]
                     + sector_lines(data) + [NOT_ADVICE])


def khuyennghi(args):
    if args:
        code = args[0].upper()
        items = recommendations(180).get(code, [])
        if not items:
            return f"Không có khuyến nghị nào cho {html.escape(code)} trong 180 ngày qua (nguồn VNDirect)"
        q = (safe(chungkhoan.quotes, [code]) or {}).get(code)
        price = (q["price"] or q["ref"]) if q else None
        lines = [f"🎯 <b>Khuyến nghị cho {code}</b> (180 ngày)" + (f" · giá {vn_num(price, 0)}" if price else "")]
        for i in items[:10]:
            target = (i.get("targetPrice") or 0) * 1000
            upside = f" ({pct((target / price - 1) * 100)})" if target and price else ""
            lines.append(f"• {i['reportDate'][8:10]}/{i['reportDate'][5:7]}/{i['reportDate'][:4]} {html.escape(i['firm'])}: "
                         f"{RATING.get((i.get('type') or '').upper(), i.get('type'))} · mục tiêu "
                         f"{vn_num(target, 0) if target else '—'}{upside}")
        return "\n".join(lines + [NOT_ADVICE])
    data = gather()
    rows = data["recs"]
    if not rows:
        return "Chưa lấy được khuyến nghị của các CTCK, thử lại sau"
    return "\n".join([f"🎯 <b>Khuyến nghị của các CTCK, 30 ngày qua</b> ({len(rows)} mã)",
                      "<i>Nhiều CTCK cùng khuyến nghị xếp trước; còn tăng = giá mục tiêu TB so với giá hiện tại</i>"]
                     + [rec_line(r) for r in rows[:15]] + ["Xem một mã: /khuyennghi FPT", NOT_ADVICE])


def tin_text(data=None):
    data = data or gather()
    if not data["news"]:
        return "Chưa lấy được tin tài chính, thử lại sau"
    return "\n".join([f"📰 <b>Tin tài chính mới</b> · {now_vn():%H:%M %d/%m}"]
                     + [news_line(i) for i in data["news"][:15]])


# ---- AI tổng hợp -----------------------------------------------------------------------

def ai_input(data):
    """Dữ liệu chữ thường gửi cho AI (không thẻ HTML), gọn để AI đọc nhanh."""
    lines = ["THỊ TRƯỜNG: " + re.sub(r"<[^>]+>", "", market_line(data))]
    for name, row in data["index"].items():
        if name != "VN-Index":
            lines.append(f"{name}: {vn_num(row[0], 2)} ({pct((row[0] / row[1] - 1) * 100)})")
    stocks = data["stocks"]
    if stocks:
        nn = sum(s["nn"] for s in stocks)
        lines.append(f"Khối ngoại ròng HOSE: {signed_billions(nn)}")
        lines.append("NGÀNH (tăng mạnh nhất trước): " + " | ".join(
            f"{g['ten']} {pct(g['pct'])}, GTGD {billions(g['gtgd'])}, NN {signed_billions(g['nn'])}, mã: "
            + ", ".join(f"{s['ma']} {pct(s['pct'])}" for s in g["ma"]) for g in data["sectors"][:6]))
        lines.append("NGÀNH HÚT TIỀN NHẤT (GTGD): " + " | ".join(
            f"{g['ten']} {billions(g['gtgd'])} ({pct(g['pct'])}, NN {signed_billions(g['nn'])})"
            for g in sorted(data["sectors"], key=lambda g: -g["gtgd"])[:4]))
        lines.append("NGÀNH GIẢM MẠNH: " + " | ".join(f"{g['ten']} {pct(g['pct'])}" for g in data["sectors"][-3:]))
        liquid = [s for s in stocks if s["gtgd"] >= 20e9]
        lines.append("MÃ GTGD LỚN NHẤT: " + ", ".join(f"{s['ma']} {pct(s['pct'])} {billions(s['gtgd'])}"
                                                      for s in sorted(stocks, key=lambda s: -s["gtgd"])[:10]))
        lines.append("TĂNG MẠNH (GTGD từ 20 tỷ): " + ", ".join(f"{s['ma']} {pct(s['pct'])}"
                                                            for s in sorted(liquid, key=lambda s: -s["pct"])[:8]))
        lines.append("GIẢM MẠNH (GTGD từ 20 tỷ): " + ", ".join(f"{s['ma']} {pct(s['pct'])}"
                                                            for s in sorted(liquid, key=lambda s: s["pct"])[:5]))
        lines.append("NGOẠI MUA RÒNG: " + ", ".join(f"{s['ma']} {signed_billions(s['nn'])}"
                                                   for s in sorted(stocks, key=lambda s: -s["nn"])[:5]))
        lines.append("NGOẠI BÁN RÒNG: " + ", ".join(f"{s['ma']} {signed_billions(s['nn'])}"
                                                   for s in sorted(stocks, key=lambda s: s["nn"])[:5]))
    if data["recs"]:
        lines.append("KHUYẾN NGHỊ CỦA CÁC CTCK (30 ngày): " + " | ".join(
            re.sub(r"<[^>]+>", "", rec_line(r)) for r in data["recs"][:15]))
    if data["news"]:
        lines.append("TIN (mới nhất trước):\n" + "\n".join(
            f"- [{i['nguon']}] {i['tieu_de']}" + (f": {i['tom_tat']}" if i["tom_tat"] else "") for i in data["news"][:25]))
    return "\n".join(lines)


SYSTEM = ("Bạn là chuyên viên tổng hợp thông tin chứng khoán Việt Nam cho một nhà đầu tư cá nhân. Chỉ dùng DỮ LIỆU "
          "được cung cấp (số liệu phiên, ngành, khuyến nghị của các công ty chứng khoán, tin tức). Không bịa số, không "
          "bịa mã, không dự đoán giá, không tự đưa khuyến nghị mua bán của riêng bạn. Mỗi mã nhắc tới phải có trong "
          "dữ liệu. Viết RẤT NGẮN, tiếng Việt có dấu, không markdown, tối đa 5 dòng, mỗi dòng dưới 20 chữ, số viết gọn "
          "(109k, 1.643 tỷ, +45%), không nhắc lại VN-Index:\n"
          "🔥 1 dòng: 2–3 ngành hot nhất (ưu tiên vừa tăng vừa hút tiền hoặc khối ngoại mua), mỗi ngành: % và tiền "
          "vào. Ví dụ: 🔥 Chứng khoán +0,7% (1.643 tỷ, ngoại mua 372 tỷ) · BĐS +1,8% (544 tỷ)\n"
          "🎯 2–3 dòng: mỗi dòng một mã đáng chú ý: % hôm nay và một lý do ngắn (CTCK nào khuyến nghị, mục tiêu, "
          "còn tăng %; hoặc tin). Ví dụ: 🎯 MWG +1,3%: HSC, UBS khuyến nghị MUA, mục tiêu 109k (+45%)\n"
          "⚠️ 1 dòng: rủi ro chính (ngành/mã giảm mạnh, khối ngoại bán, tin xấu).")
PREFIXES = ("🔥", "🎯", "⚠️", "⚠")


def ai_lines(data):
    """Các dòng AI viết, đã lọc: đúng dạng, chỉ nhắc mã có trong dữ liệu; [] nếu không có AI hoặc AI lỗi."""
    import sochitieu as ct  # dùng chung cấu hình AI (GEMINI_API_KEY, OpenRouter dự phòng)
    if not ct.ai_key():
        return []
    try:
        answer, _ = ct.ai_chat(SYSTEM, ai_input(data), max_tokens=3000)
    except Exception as e:
        print(f"[lỗi] AI nhận định: {e!r}", file=sys.stderr)
        return []
    known = data["symbols"]
    mentioned = known & set(TICKER.findall(ai_input(data)))  # mã thật sự có trong dữ liệu đưa AI
    out = []
    for raw in answer.splitlines():
        line = raw.strip().lstrip("-*• ").strip()
        if not line.startswith(PREFIXES):
            continue
        tickers = {t for t in TICKER.findall(line) if t in known}
        if tickers - mentioned:  # nhắc mã không có trong dữ liệu: bỏ dòng, tránh AI bịa
            print(f"[nhận định] bỏ dòng có mã ngoài dữ liệu: {line}", file=sys.stderr)
            continue
        out.append(html.escape(line))
    return out[:5]


def session_name(now):
    t = (now.hour, now.minute)
    if t < (9, 0):
        return "trước phiên"
    if t < (11, 30):
        return "phiên sáng"
    if t < (13, 0):
        return "nghỉ trưa"
    if t < (14, 45):
        return "phiên chiều"
    return "sau phiên"


def headline(now, data):
    """Một dòng đầu: giờ, VN-Index, thanh khoản, khối ngoại ròng HOSE."""
    vni = data["index"].get("VN-Index")
    parts = [f"🧠 <b>Nhận định {now:%H:%M}</b>"]
    if vni:
        parts.append(f"VN-Index {vn_num(vni[0], 0)} ({pct((vni[0] / vni[1] - 1) * 100)})")
        parts.append(billions(vni[2]))
    if data["stocks"]:
        parts.append("ngoại " + signed_billions(sum(s["nn"] for s in data["stocks"])))
    return " · ".join(parts)


def short_fallback(data):
    """Không có AI: 3–4 dòng số liệu gọn."""
    today_pct = {s["ma"]: s["pct"] for s in data["stocks"]}
    hot = sorted((g for g in data["sectors"] if g["pct"] > 0), key=lambda g: -g["gtgd"])[:3]
    lines = []
    if hot:
        lines.append("🔥 " + " · ".join(f"{html.escape(g['ten'])} {pct(g['pct'])} ({billions(g['gtgd'])})" for g in hot))
    for r in data["recs"][:2]:
        move = f" {pct(today_pct[r['ma']])}" if r["ma"] in today_pct else ""
        target = f", mục tiêu {pt_short(r['muc_tieu'])}" if r["muc_tieu"] else ""
        upside = f" ({pct(r['con_tang'])})" if r["con_tang"] is not None else ""
        lines.append(f"🎯 {r['ma']}{move}: {html.escape(', '.join(r['ctck'][:2]))} khuyến nghị {r['loai']}{target}{upside}")
    if data["news"]:
        lines.append(news_line(data["news"][0]))
    return lines


def pt_short(x):
    """109461 -> '109k'."""
    return f"{round(x / 1000)}k"


def brief(now=None, data=None):
    """Tin nhận định ngắn (chữ, nút); chi tiết xem bằng các nút."""
    now = now or now_vn()
    data = data or gather()
    lines = [headline(now, data)]
    smart = ai_lines(data)
    if smart:
        lines += smart + [SHORT_NOTE]
    else:
        import sochitieu as ct
        lines += short_fallback(data)
        lines.append("<i>" + ("AI đang bận, chỉ có số liệu" if ct.ai_key() else "Bật AI (GEMINI_API_KEY) để có nhận định")
                     + " · tham khảo, không phải lời khuyên đầu tư</i>")
    return "\n".join(lines), BUTTONS


def nhandinh(args):
    word = (args[0].lower() if args else "")
    if word in ("tat", "tắt", "bat", "bật"):
        if not kho.ready():
            return "Cần kho dữ liệu để bật/tắt, gõ /caidat"
        if word in ("tat", "tắt"):
            kho.put(OFF, True)
            return "Đã tắt nhận định tự gửi trong phiên. Bật lại: /nhandinh bat"
        kho.delete(OFF)
        return "Đã bật: ngày giao dịch bot gửi nhận định lúc 10h15 và 13h45"
    return brief()


def on_button(arg):
    """Nút "nd:...": (thông báo nhỏ, việc tiếp theo) như lenh.on_button."""
    if arg == "moi":
        return "Đang tổng hợp lại…", ("edit", brief)
    if arg == "nganh":
        return None, ("send", nganh_text)
    if arg == "kn":
        return None, ("send", lambda: khuyennghi([]))
    if arg == "tin":
        return None, ("send", tin_text)
    return None, None


def scheduled(now):
    """Nhận định tự gửi trong phiên: (chữ, nút) hoặc None nếu đã tắt, hay hôm nay không giao dịch."""
    if kho.ready() and kho.get(OFF):
        return None
    data = gather()
    vni = data["index"].get("VN-Index")
    if not vni or not vni[2]:  # chưa có giao dịch (ngày nghỉ lễ)
        return None
    return brief(now, data)
