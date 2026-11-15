"""Đo bot hiểu tin nhắn tới đâu: chạy bộ câu questions.CAU qua đúng đường xử lý của bot (luật trước, AI sau) nhưng
không ghi gì, rồi so với việc mong đợi.

- plan(text): bot sẽ làm những việc gì với câu này (danh sách việc), không ghi sổ, không gửi tin.
- run(tu, n, nhom): chấm một đoạn bộ câu (trang tình trạng: ?danhgia=1&tu=0&n=8). Dùng ngữ cảnh mẫu (DEMO_CONTEXT,
  DEMO_FACTS) và ngày cố định DAY, không dùng dữ liệu thật; AI thật (Gemini) nên giới hạn số lượt mỗi ngày.
"""
import re
import sys
from datetime import date, datetime

from infrastructure import kho
from repositories import keys
import sochitieu as ct

DAY = date(2026, 11, 20)  # thứ Sáu
LIMIT = 80  # số lượt ?danhgia= mỗi ngày (mỗi lượt vài câu, mỗi câu tối đa một lần gọi AI)
DEMO_CONTEXT = ("Khoản nợ đang có: bác Vân; thẻ Techcombank trả góp\n"
                "Tài khoản, ví đang có: VCB; Techcombank (tài khoản chính); MoMo; tiền mặt; DNSE\n"
                "Sổ tiết kiệm đang có: TCB; MB\n"
                "Đang cho vay: Hùng; em gái\n"
                "Vàng đang có: nhẫn 0,5 chỉ\n"
                "Quỹ mở đang đầu tư định kỳ: VMEEF; quỹ chờ: VFF")
DEMO_NAMES = ["bác Vân", "thẻ Techcombank trả góp", "VCB", "Techcombank", "MoMo", "tiền mặt", "DNSE", "TCB", "MB", "Hùng",
              "em gái"]
DEMO_FACTS = """Hôm nay thứ Sáu 20/11/2026. Lương 19tr về ngày 5.
Tháng 11: đã thu 19tr · đã chi 3,2tr (không tính trả nợ) · hôm nay đã chi 205k
Mỗi ngày được tiêu: hôm nay còn 217k, mức 422k/ngày (thu 19tr − trả nợ 6,39tr − quỹ dự phòng 4,4tr − đầu tư 5tr = 3,21tr chi tiêu/tháng, còn 11 ngày)
Kế hoạch chia lương tháng 11: trả nợ 6,39tr ✅ đã trả · quỹ dự phòng 4,4tr (đã nạp 3tr) · đầu tư VMEEF 5tr (đã để 0đ) · còn thiếu 2,4tr
Tài khoản: Techcombank (chính) ~19,83tr · MoMo 450k · tiền mặt 800k · DNSE 21k
Quỹ dự phòng 15tr / mục tiêu 60tr (6 tháng chi thiết yếu 10tr) · cần 4,09tr/tháng để đủ trước 10/2027
Nợ còn 271,2tr: bác Vân 263tr (không lãi, 2tr/tháng, xong ~10/2037) · thẻ Techcombank trả góp 8,2tr (4,39tr/tháng, xong ~01/2027)
Đầu tư quỹ VMEEF: 66,9 ccq ≈ 1,01tr, lãi 8k (+0,8%) · kế hoạch tháng 11: 12,12tr · cuối tháng dự kiến mua ~5tr · hạn đặt lệnh 14:40 30/11 · quỹ chờ VFF 0đ
Cổ phiếu 106,34tr, lỗ 42,21tr (−28,4%): SSI 5.160 cp (−29%) · HPG 100 cp (−2%)
Vàng: nhẫn 0,5 chỉ ≈ 6,67tr, lãi 77k (+1,2%)
Tài sản ròng −137,34tr (tài sản 133,86tr, nợ 271,2tr)
Chi trung bình 3 tháng qua: 9,8tr/tháng · nhóm nhiều nhất tháng này: ăn uống 1,4tr, đi lại 620k"""


def money_rule(text):
    """Câu "mua VMEEF 3tr" (luật của dautu.from_text, không ghi): việc hoặc None."""
    t = ct.plain(text).split()
    found = ct.parse_amount(text)
    if len(t) < 3 or t[0] != "mua" or not found:
        return None
    code = next((c for c in t[1:3] if c in ("vmeef", "vff")), None)
    return {"viec": "quy", "ma": code.upper(), "tien": found[0]} if code else None


def as_list(a):
    if not a:
        return []
    if a.get("viec") == "_nhieu":
        return list(a.get("ds") or [])
    return [a]


def plan(text, day=DAY, people=DEMO_CONTEXT, facts=DEMO_FACTS):
    """Đường đi của câu trong sochitieu.respond (luật trước, AI sau), không ghi gì: danh sách việc."""
    troly = ct.troly()
    t = text.strip()
    if t.startswith("/"):
        return [{"viec": "lenh"}]
    trade = ct.taisan().parse_trade(t)
    if trade:
        side, qty, code, price = trade
        return [{"viec": "co_phieu", "chieu": side, "ma": code, "sl": qty, "gia": price}]
    fund = money_rule(t)
    if fund:
        return [fund]
    bare = ct.plain(t)
    if len(bare) <= 40 and not ct.parse_amount(t) and troly.NO_SPEND.search(bare):
        return [{"viec": "khong_tieu"}]
    question = ct.phantich().is_question(t)
    if question and not (ct.ai_key() and troly.beyond_spending(t)):
        return [{"viec": "hoi"}]
    if question or troly.wants(t, DEMO_NAMES):
        a = troly.ask_ai(t, day, people=people, facts=facts if question else None)  # như bot thật: số liệu chỉ đi kèm câu hỏi
        out = []
        for one in as_list(a):
            if one.get("viec") == "chi" and not one.get("tien"):  # AI bảo là khoản chi: bot ghi bằng luật
                e = ct.parse_line(t, day, {})
                one = {"viec": "chi", **({"tien": e["tien"], "ngay": e["ngay"]} if e else {})}
            out.append(one)
        return out
    e = ct.parse_line(t, day, {})
    if not e:
        return [{"viec": "khac"}]
    return [{"viec": "thu" if e["nhom"] == ct.INCOME else "chi", "tien": e["tien"], "ngay": e["ngay"]}]


def same(field, want, got):
    if got is None:
        return False
    if isinstance(want, bool):
        return bool(got) == want
    if isinstance(want, (int, float)):
        try:
            got = float(got)
        except (TypeError, ValueError):
            return False
        if field == "gia" and got >= 1000:
            got /= 1000  # luật đọc giá ra đồng, AI đưa nghìn đồng
        return abs(got - want) <= max(1, abs(want) * 0.01)
    return ct.plain(str(want)) in ct.plain(str(got)) or ct.plain(str(got)) in ct.plain(str(want))


def matches(want, got):
    if want["viec"] != got.get("viec"):
        return False
    for field, value in want.items():
        if field == "viec":
            continue
        if field == "chua":
            answer = ct.plain(got.get("cau") or "").replace(" ", "")
            if not all(ct.plain(x).replace(" ", "") in answer for x in value):
                return False
        elif not same(field, value, got.get(field)):
            return False
    return True


def score(expected, got):
    """Câu đúng khi mỗi việc mong đợi khớp một việc bot làm, và bot không làm thêm việc nào."""
    left = list(got)
    for want in expected:
        hit = next((g for g in left if matches(want, g)), None)
        if hit is None:
            return False
        left.remove(hit)
    return not left


def short(a):
    keep = {k: v for k, v in a.items() if not k.startswith("_")}
    if "cau" in keep:
        keep["cau"] = keep["cau"][:120]
    return keep


def run(tu=0, n=8, nhom=None, budget=50):
    """Chấm câu [tu, tu+n) (lọc theo nhóm nếu có). Trả chữ: mỗi câu một dòng, dòng cuối là tổng."""
    from interface.danhgia import questions as danhgia_cau
    used = kho.command("INCR", keys.benchmark_usage(date.today()))
    kho.command("EXPIRE", keys.benchmark_usage(date.today()), 2 * 86400)
    if used > LIMIT:
        return f"Hôm nay đã chạy {LIMIT} lượt đo, mai chạy tiếp."
    rows = [c for c in danhgia_cau.CAU if not nhom or c[0] == nhom]
    started = datetime.now()
    lines, good, done = [], 0, 0
    for group, text, expected in rows[tu:tu + n]:
        if (datetime.now() - started).total_seconds() > budget:
            break
        try:
            got = plan(text)
        except Exception as e:
            print(f"[lỗi] đo câu {text!r}: {e!r}", file=sys.stderr)
            got = [{"viec": "loi", "cau": str(e)[:100]}]
        ok = score(expected, got)
        good += ok
        done += 1
        lines.append(f"{'OK' if ok else 'SAI'}\t{group}\t{text}\t{[short(a) for a in got]}")
    lines.append(f"TONG\t{good}/{done}\tcâu {tu}–{tu + done - 1} / {len(rows)}")
    return "\n".join(lines)


def page(query):
    """?danhgia=1&tu=0&n=8[&nhom=chi] trên trang tình trạng bot chi tiêu."""
    def num(key, default):
        try:
            return max(0, int((query.get(key) or [default])[0]))
        except ValueError:
            return default
    nhom = (query.get("nhom") or [None])[0]
    return run(num("tu", 0), min(num("n", 8), 15), nhom if nhom and re.fullmatch(r"[a-z_]+", nhom) else None)
