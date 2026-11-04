"""Bot ghi chi tiêu, một bot Telegram riêng chạy trên Vercel (cách cài: README, mục Bot chi tiêu).

GET  /api/chitieu: cài webhook cho bot chi tiêu rồi báo tình trạng (mở bằng trình duyệt sau khi deploy)
POST /api/chitieu: Telegram gửi tin nhắn, lượt bấm nút của bot chi tiêu tới đây
"""
import hmac
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # để import các file ở thư mục gốc

import kho  # noqa: E402
import sochitieu as chitieu  # noqa: E402 (file lõi đặt tên khác file này để khỏi import nhầm)
import tg  # noqa: E402
from bantin import VN_TZ  # noqa: E402


def handle_message(message, tok):
    chat_id = (message.get("chat") or {}).get("id")
    text = message.get("text") or ""
    if str(chat_id) not in chitieu.owner_chats():
        if chat_id and text.startswith("/"):
            tg.send(chat_id, f"Bot này là bot riêng. Chat ID của bạn: {chat_id}\n"
                             "Nếu bạn là chủ bot: thêm số này vào CHITIEU_CHAT_ID trên Vercel rồi Redeploy.",
                    tok=tok)
        return
    if not text:
        return
    try:  # hiện "đang nhập…": khoản lạ phải hỏi AI có khi mất chục giây
        tg.call("sendChatAction", tok, chat_id=chat_id, action="typing")
    except Exception as e:
        print(f"[lỗi] sendChatAction: {e!r}", file=sys.stderr)
    try:
        reply = chitieu.answer(text, datetime.now(VN_TZ))
    except Exception as e:
        print(f"[lỗi] trả lời {text!r}: {e!r}", file=sys.stderr)
        reply = "⚠️ Bot gặp lỗi, thử lại sau nhé."
    tg.send_reply(chat_id, reply, tok)


def handle_button(query, tok):
    chat_id = ((query.get("message") or {}).get("chat") or {}).get("id")
    if str(chat_id) not in chitieu.owner_chats():
        tg.call("answerCallbackQuery", tok, callback_query_id=query["id"])
        return
    tg.handle_button(query, chitieu.on_button, datetime.now(VN_TZ), tok)


def status_page(environ, tok):
    if not tok:
        return ("Chưa có biến CHITIEU_BOT_TOKEN trên Vercel. Tạo bot qua @BotFather, thêm token vào biến đó "
                "rồi Redeploy (xem README, mục Bot chi tiêu).\n"
                + chitieu.ai_status(test="thu=1" in environ.get("QUERY_STRING", "")))
    if not chitieu.owner_chats():
        return "Thiếu TELEGRAM_CHAT_ID (hoặc CHITIEU_CHAT_ID) trên Vercel. Thêm vào rồi Redeploy."
    host = os.environ.get("VERCEL_PROJECT_PRODUCTION_URL") or environ.get("HTTP_HOST")
    try:
        tg.call("setWebhook", tok, url=f"https://{host}/api/chitieu",
                secret_token=tg.derived_secret("webhook", tok), allowed_updates=["message", "callback_query"])
        tg.call("setMyCommands", tok, commands=chitieu.MENU)
        info = tg.call("getWebhookInfo", tok)
        me = tg.call("getMe", tok)
    except Exception as e:
        return f"Không cài được webhook: {e!r}"
    lines = [f"Bot chi tiêu: @{me.get('username')}", f"Đã cài webhook: {info['url']}",
             f"Tin nhắn đang chờ: {info.get('pending_update_count', 0)}"]
    if info.get("last_error_message"):
        lines.append(f"Lỗi gần nhất từ Telegram: {info['last_error_message']}")
    lines += [f"Chỉ trả lời chat ID: {', '.join(chitieu.owner_chats())}",
              f"Kho dữ liệu: {'đã kết nối' if kho.ready() else 'chưa có (xem README)'}",
              chitieu.ai_status(test="thu=1" in environ.get("QUERY_STRING", "")), "", f"Xong! Vào Telegram nhắn @{me.get('username')}: cà phê 35k"]
    return "\n".join(lines)


def respond(start_response, status, text):
    body = text.encode("utf-8")
    start_response(status, [("Content-Type", "text/plain; charset=utf-8"),
                            ("Content-Length", str(len(body)))])
    return [body]


def app(environ, start_response):
    tok = chitieu.token()
    if environ["REQUEST_METHOD"] != "POST":
        return respond(start_response, "200 OK", status_page(environ, tok))
    secret = environ.get("HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN", "").encode()
    if not tok or not hmac.compare_digest(secret, tg.derived_secret("webhook", tok).encode()):
        return respond(start_response, "403 Forbidden", "sai secret")
    try:
        length = int(environ.get("CONTENT_LENGTH") or 0)
        update = json.loads(environ["wsgi.input"].read(length))
        if "callback_query" in update:
            handle_button(update["callback_query"], tok)
        else:
            handle_message(update.get("message") or {}, tok)
    except Exception as e:
        print(f"[lỗi] {e!r}", file=sys.stderr)
    # Luôn trả 200, kẻo Telegram gửi lại mãi một tin nhắn gây lỗi
    return respond(start_response, "200 OK", "ok")
