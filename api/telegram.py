"""Bot Telegram trả lời lệnh, chạy trên Vercel (cách cài: README).

GET  /api/telegram: cài webhook về đúng địa chỉ này rồi báo tình trạng (mở bằng trình duyệt sau khi deploy)
POST /api/telegram: Telegram gửi tin nhắn, vị trí, lượt bấm nút tới đây
"""
import hmac
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # để import các file ở thư mục gốc

import kho  # noqa: E402
import tg  # noqa: E402
from bantin import VN_TZ  # noqa: E402
from lenh import MENU, answer, answer_location, on_button  # noqa: E402


def send_reply(chat_id, reply):
    text, buttons = reply if isinstance(reply, tuple) else (reply, None)
    tg.send(chat_id, text, buttons)


def handle_message(message):
    chat_id = (message.get("chat") or {}).get("id")
    text = message.get("text") or ""
    location = message.get("location")
    if str(chat_id) != tg.owner_chat():
        # Bot riêng: chỉ trả lời chat của chủ. Người gõ lệnh thì được biết chat ID của mình,
        # để chủ bot cài sai TELEGRAM_CHAT_ID còn biết đường sửa.
        if chat_id and text.startswith("/"):
            tg.send(chat_id, f"Bot này là bot riêng. Chat ID của bạn: {chat_id}\n"
                             "Nếu bạn là chủ bot: đặt TELEGRAM_CHAT_ID trên Vercel đúng số này rồi Redeploy.")
        return
    if not (text.startswith("/") or location):
        return
    try:  # hiện "đang nhập…" trong lúc lấy dữ liệu, /bantin mất cả chục giây
        tg.call("sendChatAction", chat_id=chat_id, action="typing")
    except Exception as e:
        print(f"[lỗi] sendChatAction: {e!r}", file=sys.stderr)
    try:
        reply = answer_location(location["latitude"], location["longitude"]) if location else answer(text)
    except Exception as e:
        print(f"[lỗi] trả lời {text or location!r}: {e!r}", file=sys.stderr)
        reply = "⚠️ Bot gặp lỗi khi lấy dữ liệu, thử lại sau nhé."
    if reply:
        send_reply(chat_id, reply)


def handle_button(query):
    message = query.get("message") or {}
    chat_id = (message.get("chat") or {}).get("id")
    if str(chat_id) != tg.owner_chat():
        tg.call("answerCallbackQuery", callback_query_id=query["id"])
        return
    try:
        toast, action = on_button(query.get("data") or "", message, datetime.now(VN_TZ))
    except Exception as e:
        print(f"[lỗi] nút {query.get('data')!r}: {e!r}", file=sys.stderr)
        toast, action = "⚠️ Bot gặp lỗi, thử lại sau nhé", None
    # Trả lời ngay cho nút thôi quay, việc chậm (cập nhật bản tin...) làm sau
    tg.call("answerCallbackQuery", callback_query_id=query["id"], **({"text": toast} if toast else {}))
    if not action:
        return
    how, make = action
    try:
        reply = make()
    except Exception as e:
        print(f"[lỗi] nút {query.get('data')!r}: {e!r}", file=sys.stderr)
        reply = "⚠️ Bot gặp lỗi khi lấy dữ liệu, thử lại sau nhé."
        how = "send"
    if how == "send":
        send_reply(chat_id, reply)
    elif how == "buttons":
        tg.edit_buttons(chat_id, message["message_id"], reply)
    else:
        text, buttons = reply if isinstance(reply, tuple) else (reply, None)
        tg.edit(chat_id, message["message_id"], text, buttons)


def setup(host):
    url = f"https://{host}/api/telegram"
    tg.call("setWebhook", url=url, secret_token=tg.derived_secret("webhook"),
            allowed_updates=["message", "callback_query"])
    tg.call("setMyCommands", commands=MENU)
    info = tg.call("getWebhookInfo")
    lines = [f"Đã cài webhook: {info['url']}",
             f"Tin nhắn đang chờ: {info.get('pending_update_count', 0)}"]
    if info.get("last_error_message"):
        lines.append(f"Lỗi gần nhất từ Telegram: {info['last_error_message']}")
    return lines


def status_page(environ):
    missing = [k for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID") if not os.environ.get(k, "").strip()]
    if missing:
        return f"Thiếu biến môi trường trên Vercel: {', '.join(missing)}. Thêm vào rồi Redeploy."
    host = os.environ.get("VERCEL_PROJECT_PRODUCTION_URL") or environ.get("HTTP_HOST")
    try:
        lines = setup(host)
    except Exception as e:
        return f"Không cài được webhook: {e!r}"
    lines.append(f"Chỉ trả lời chat ID: {tg.owner_chat()}")
    if kho.ready():
        try:
            last = kho.get("tick_cuoi")
            lines += ["Kho dữ liệu: đã kết nối",
                      f"Lịch chạy: {'lần gần nhất ' + last if last else 'chưa chạy lần nào (xem /caidat)'}"]
        except Exception as e:
            lines.append(f"Kho dữ liệu: lỗi {e!r}")
    else:
        lines.append("Kho dữ liệu: chưa có (xem README, mục Kho dữ liệu)")
    return "\n".join(lines + ["", "Xong! Vào Telegram gõ /stock để thử."])


def respond(start_response, status, text):
    body = text.encode("utf-8")
    start_response(status, [("Content-Type", "text/plain; charset=utf-8"),
                            ("Content-Length", str(len(body)))])
    return [body]


def app(environ, start_response):
    token = tg.token()
    if environ["REQUEST_METHOD"] != "POST":
        return respond(start_response, "200 OK", status_page(environ))
    secret = environ.get("HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN", "").encode()
    if not token or not hmac.compare_digest(secret, tg.derived_secret("webhook").encode()):
        return respond(start_response, "403 Forbidden", "sai secret")
    try:
        length = int(environ.get("CONTENT_LENGTH") or 0)
        update = json.loads(environ["wsgi.input"].read(length))
        if "callback_query" in update:
            handle_button(update["callback_query"])
        else:
            handle_message(update.get("message") or {})
    except Exception as e:
        print(f"[lỗi] {e!r}", file=sys.stderr)
    # Luôn trả 200, kẻo Telegram gửi lại mãi một tin nhắn gây lỗi
    return respond(start_response, "200 OK", "ok")
