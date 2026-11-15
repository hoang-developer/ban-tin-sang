"""Nhận định trong phiên: ngành, khuyến nghị của công ty chứng khoán, tính số liệu và chữ số liệu gọn (tính thuần)."""
import re
from datetime import datetime, timedelta, timezone

from domain.common.format import vn_num

RATING = {"BUY": "MUA", "STRONG_BUY": "MUA MẠNH", "OUTPERFORM": "KHẢ QUAN", "ADD": "TĂNG TỶ TRỌNG",
          "ACCUMULATE": "TÍCH LŨY", "HOLD": "GIỮ", "NEUTRAL": "TRUNG LẬP", "UNDERPERFORM": "KÉM KHẢ QUAN",
          "REDUCE": "GIẢM TỶ TRỌNG", "SELL": "BÁN"}
SHORT_NAMES = {"Dịch vụ Đầu tư Bất Động Sản": "Bất động sản", "Ga, nước & dịch vụ công cộng gia dụng": "Tiện ích",
               "Dược phẩm & công nghệ sinh học": "Dược phẩm", "Dụng cụ, dịch vụ & Phân phối Dầu": "Dịch vụ dầu khí",
               "Phần mềm & Dịch vụ máy tính": "Công nghệ thông tin", "Dịch vụ tài chính": "Chứng khoán, tài chính",
               "Kim loại công nghiệp": "Thép, kim loại", "Xây dựng & Vật liệu": "Xây dựng, vật liệu",
               "Giao thông công nghiệp": "Vận tải, cảng", "Sản xuất thực phẩm": "Thực phẩm",
               "Dụng cụ điện & Điện tử": "Thiết bị điện", "Sản xuất dầu khí": "Dầu khí"}
TICKER = re.compile(r"(?<![A-Za-z0-9])[A-Z][A-Z0-9]{2}(?![A-Za-z0-9])")


def industry_names(rows):
    """Dòng phân ngành VNDirect -> {mã: tên ngành gọn}."""
    out = {}
    for r in rows:
        name = " ".join((r.get("vietnameseName") or "").split())
        for code in (r.get("codeList") or "").split(","):
            if code.strip():
                out[code.strip()] = SHORT_NAMES.get(name, name)
    return out


def recommendations_by_code(rows):
    """Dòng khuyến nghị -> {mã: [khuyến nghị mới nhất trước]}."""
    out = {}
    for r in rows:
        out.setdefault(r["code"], []).append({k: r.get(k) for k in (
            "firm", "type", "reportDate", "reportPrice", "targetPrice", "avgTargetPrice")})
    return out


def merge_news(results, hours, now=None):
    """Tin các nguồn gộp lại: trong `hours` giờ qua, mới nhất trước, bỏ tin trùng tiêu đề (tối đa 40)."""
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(hours=hours)
    seen, out = set(), []
    for item in sorted((x for r in results if r for x in r), key=lambda x: x["luc"] or cutoff, reverse=True):
        key = item["tieu_de"].lower()
        if key not in seen and (item["luc"] is None or item["luc"] >= cutoff):
            seen.add(key)
            out.append(item)
    return out[:40]


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
        firms = list(dict.fromkeys(i["firm"] for i in items))
        rows.append({"ma": code, "so": len(firms), "ctck": firms,
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


def whole_pct(x):
    return f"{x:+.0f}%"


def pt_short(x):
    """Giá gọn: 109.461 -> '109k'; 53.600 -> '53,6k'; 33.000 -> '33k'."""
    if x >= 100_000:
        return f"{round(x / 1000)}k"
    return f"{x / 1000:.1f}".rstrip("0").rstrip(".").replace(".", ",") + "k"


def market_line(data):
    vni = data["index"].get("VN-Index")
    if not vni:
        return "VN-Index: chưa lấy được số liệu"
    point, ref, value, up, down, _ = vni
    return (f"VN-Index <b>{vn_num(point, 2)}</b> ({pct((point / ref - 1) * 100)}) · GTGD HOSE {billions(value)}"
            f" · ↑{up} ↓{down}")


def rec_line(r):
    """'MWG · 4 CTCK MUA · mục tiêu 109k (+45%)': số CTCK, không liệt kê tên."""
    target = ""
    if r["muc_tieu"]:
        target = f" · mục tiêu {pt_short(r['muc_tieu'])}" + (
            f" ({whole_pct(r['con_tang'])})" if r["con_tang"] is not None else "")
    return f"<b>{r['ma']}</b> · {r['so']} CTCK {r['loai']}{target}"


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
