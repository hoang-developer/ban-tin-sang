"""Dựng bot chi tiêu chạy thử trong bộ nhớ: kho Redis giả, đồng hồ giả, Fmarket giả (NAV thật của VMEEF, VFF trong
tests/data), giá cổ phiếu và vàng giả, AI giả (trả JSON soạn sẵn theo từng câu), Telegram giả (gom tin đã gửi).
Dùng: from tests import harness as h; h.reset(); h.say("cà phê 35k"); h.press("y:ok:1")."""
import json
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["CHITIEU_BOT_TOKEN"] = "test"
os.environ["TELEGRAM_CHAT_ID"] = "1"
os.environ["GEMINI_API_KEY"] = "test"
os.environ.pop("AI_API_KEY", None)

import kho  # noqa: E402

STORE = {}


def command(*args):
    op, key, *rest = [str(a) for a in args]
    op = op.upper()
    if op == "GET":
        return STORE.get(key)
    if op == "SET":
        if "NX" in rest and key in STORE:
            return None
        STORE[key] = rest[0]
        return "OK"
    if op == "DEL":
        STORE.pop(key, None)
        return 1
    if op == "INCR":
        STORE[key] = str(int(STORE.get(key, "0")) + 1)
        return int(STORE[key])
    if op == "EXPIRE":
        return 1
    table = json.loads(STORE.get(key, "{}"))
    if op == "HSET":
        table[rest[0]] = rest[1]
        STORE[key] = json.dumps(table)
        return 1
    if op == "HGET":
        return table.get(rest[0])
    if op == "HDEL":
        gone = table.pop(rest[0], None)
        STORE[key] = json.dumps(table)
        return 1 if gone is not None else 0
    if op == "HGETALL":
        return [x for pair in table.items() for x in pair]
    if op == "HINCRBY":
        table[rest[0]] = str(int(table.get(rest[0], 0)) + int(rest[1]))
        STORE[key] = json.dumps(table)
        return int(table[rest[0]])
    raise NotImplementedError(op)


kho.command = command
kho.ready = lambda: True

import bantin  # noqa: E402
import dautu  # noqa: E402
import sochitieu as ct  # noqa: E402
import taisan as ts  # noqa: E402
import tg  # noqa: E402

VN_TZ = bantin.VN_TZ
CLOCK = {"now": datetime(2026, 11, 13, 9, 0, tzinfo=VN_TZ)}
CHAT = 1
SENT = []  # tin bot tự gửi (việc theo giờ)
ct.today = lambda: CLOCK["now"].date()
dautu.now_vn = lambda: CLOCK["now"]
ts.now_vn = lambda: CLOCK["now"]
tg.send_reply = lambda chat, reply, tok=None: SENT.append(reply)
tg.send = lambda chat, text, buttons=None, tok=None: SENT.append((text, buttons))


def load_nav(code):
    return [(date.fromisoformat(d), v) for d, v in json.load(open(ROOT / "tests" / "data" / f"nav_{code}.json"))]


NAV = {"VMEEF": load_nav("vmeef"), "VFF": load_nav("vff")}
FUND_ID = {"VMEEF": 68, "VFF": 21}


def published(code, now):
    """NAV phiên d có trên Fmarket từ 17h ngày d."""
    return [(d, v) for d, v in NAV[code] if d < now.date() or (d == now.date() and now.hour >= 17)]


def next_session(code, now):
    """(phiên khớp kế tiếp, lúc đóng sổ lệnh): đóng sổ 14:40 ngày làm việc trước phiên."""
    for d, _ in NAV[code]:
        prev = d - timedelta(days=1)
        while prev.weekday() >= 5:
            prev -= timedelta(days=1)
        close = datetime(prev.year, prev.month, prev.day, 14, 40, tzinfo=VN_TZ)
        if close > now:
            return d, close
    raise RuntimeError("hết dữ liệu NAV thử")


def fake_fmarket(url, body=None):
    now = CLOCK["now"]
    if url.endswith("/products/filter"):
        code = (body or {}).get("searchField", "").upper()
        return {"data": {"rows": [{"id": FUND_ID[code], "shortName": code, "name": f"QUỸ {code}"}] if code in FUND_ID else []}}
    code = next((c for c, i in FUND_ID.items() if url.endswith(f"/products/{i}") or (body or {}).get("productId") == i), None)
    if "get-nav-history" in url:
        return {"data": [{"navDate": d.isoformat(), "nav": v} for d, v in published(code, now)]}
    if code:
        trading, close = next_session(code, now)
        return {"data": {"productTradingSession": {"tradingTimeString": trading.strftime("%d/%m/%Y"),
                                                   "closedOrderBookTimeString": close.strftime("%H:%M %d/%m/%Y")},
                         "productTopHoldingList": [{"stockCode": "HPG", "industry": "Thép", "netAssetPercent": 8.5}],
                         "productFund": {"updateAssetHoldingTime": "09/2026"}}}
    raise RuntimeError(f"địa chỉ chưa giả lập: {url}")


STOCKS = {"HAG": 12000, "FPT": 95000, "E1VFVN30": 33600}
ts.http_json = fake_fmarket
ts.SOURCES["quy"] = (lambda codes=None: {c: published(c, CLOCK["now"])[-1][1] for c in NAV}, 0)
ts.SOURCES["cp"] = ts.SOURCES["etf"] = (lambda codes: {c: STOCKS[c] for c in codes if c in STOCKS}, 0)
ts.SOURCES["vang"] = (lambda codes=None: {"sjc": 138e6, "nhan": 136e6}, 0)


class FakeAI:
    """AI giả: replies[câu người dùng] = dict (trả thành JSON) hoặc chuỗi; không có thì báo lỗi như AI đang bận."""

    def __init__(self):
        self.replies, self.calls, self.photo = {}, [], None

    def chat(self, system, user, max_tokens=2000, image=None, timeout=25, budget=45):
        text = user if isinstance(user, str) else user[0]["text"]
        self.calls.append((system, text))
        if image is not None and self.photo is not None:  # câu trả lời soạn sẵn cho lần đọc ảnh kế tiếp
            return json.dumps(self.photo, ensure_ascii=False), "ai-gia"
        if text not in self.replies:
            raise RuntimeError("AI giả: đang bận")
        reply = self.replies[text]
        return (reply if isinstance(reply, str) else json.dumps(reply, ensure_ascii=False)), "ai-gia"


AI = FakeAI()
ct.ai_chat = AI.chat


def reset(now=None):
    """Xóa sạch kho, AI giả, tin đã gửi; đặt lại đồng hồ."""
    STORE.clear()
    SENT.clear()
    AI.replies.clear()
    AI.calls.clear()
    AI.photo = None
    os.environ["GEMINI_API_KEY"] = "test"
    CLOCK["now"] = now or datetime(2026, 11, 13, 9, 0, tzinfo=VN_TZ)
    ct.reset()


def at(year, month, day, hour=9, minute=0):
    CLOCK["now"] = datetime(year, month, day, hour, minute, tzinfo=VN_TZ)


def parts(reply):
    """(chữ đã bỏ thẻ <b>, <i>, [dữ liệu các nút]) của một câu trả lời."""
    if isinstance(reply, dict):
        reply = reply["messages"][-1] if "messages" in reply else (reply.get("caption", ""), None)
    text, rows = reply if isinstance(reply, tuple) else (reply, None)
    return re.sub(r"</?[bi]>", "", text or ""), [data for row in rows or [] for _, data in row]


def say(text):
    """Người dùng nhắn một tin: (chữ bot trả lời, dữ liệu các nút)."""
    return parts(ct.answer(text, CLOCK["now"], CHAT))


def press(data, text=""):
    """Người dùng bấm một nút: (thông báo nhỏ, chữ sau khi bấm, dữ liệu các nút)."""
    toast, action = ct.on_button(data, {"chat": {"id": CHAT}, "text": text}, CLOCK["now"])
    body, buttons = parts(action[1]()) if action else ("", [])
    return toast, body, buttons


def button(buttons, prefix):
    """Nút đầu tiên có dữ liệu bắt đầu bằng prefix."""
    return next(b for b in buttons if b.startswith(prefix))


def month_entries():
    return ct.load(CLOCK["now"].strftime("%Y-%m"))


def run_jobs():
    """Chạy việc theo giờ của phần đầu tư ở giờ hiện tại; trả các tin bot gửi: [(chữ, dữ liệu các nút)]."""
    import lich
    SENT.clear()
    lich.dau_tu(CLOCK["now"], str(CHAT))
    return [parts(reply) for reply in SENT]


def send_photo(caption=""):
    """Người dùng gửi một ảnh (AI giả trả AI.photo): (chữ bot trả lời, dữ liệu các nút)."""
    import docanh
    docanh.download = lambda file_id, tok: b"anh"
    message = {"chat": {"id": CHAT}, "caption": caption,
               "photo": [{"file_id": "f1", "file_unique_id": f"u{len(AI.calls)}"}]}
    return parts(docanh.photo(message, "test", CLOCK["now"]))
