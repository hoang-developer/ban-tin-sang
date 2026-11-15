"""AI tổng hợp nhận định trong phiên: chỉ dùng dữ liệu đưa vào, dòng nào nhắc mã ngoài dữ liệu thì bị bỏ."""
import html
import re
import sys

from domain.nhandinh.rules import TICKER, billions, market_line, pct, rec_line, signed_billions
from domain.common.format import vn_num
from infrastructure import ai

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
          "🎯 2–3 dòng: mỗi dòng một mã đáng chú ý: % hôm nay và một lý do ngắn (số CTCK khuyến nghị, không liệt kê "
          "tên CTCK; mục tiêu, còn tăng %; hoặc tin). Ví dụ: 🎯 MWG +1,3%: 4 CTCK khuyến nghị MUA, mục tiêu 109k "
          "(+45%)\n"
          "⚠️ 1 dòng: rủi ro chính (ngành/mã giảm mạnh, khối ngoại bán, tin xấu).")
PREFIXES = ("🔥", "🎯", "⚠️", "⚠")


def ai_lines(data):
    """Các dòng AI viết, đã lọc: đúng dạng, chỉ nhắc mã có trong dữ liệu; [] nếu không có AI hoặc AI lỗi."""
    if not ai.key():
        return []
    try:
        answer, _ = ai.chat(SYSTEM, ai_input(data), max_tokens=3000)
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
