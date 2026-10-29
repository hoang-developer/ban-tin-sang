"""Bot Telegram trả lời lệnh, chạy trên Vercel (cách cài: README).

GET  /api/telegram: cài webhook về đúng địa chỉ này rồi báo tình trạng (mở bằng trình duyệt sau khi deploy)
POST /api/telegram: Telegram gửi tin nhắn tới đây
"""
import hashlib
import hmac
import json
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # để import các file ở thư mục gốc

from bantin import send_telegram  # noqa: E402
from lenh import MENU, answer  # noqa: E402


def webhook_secret(token):
    # Suy ra từ token để khỏi phải tạo thêm biến; không có token thì không giả được
    return hashlib.sha256(token.encode()).hexdigest()[:32]


def telegram(token, method, **params):
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/{method}",
                                 data=json.dumps(params).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())["result"]


def owner_chat():
    return os.environ.get("TELEGRAM_CHAT_ID", "").strip()  # dán trên điện thoại hay dính dấu cách


def handle_update(update, token):
    message = update.get("message") or {}
    chat_id = (message.get("chat") or {}).get("id")
    text = message.get("text") or ""
    if str(chat_id) != owner_chat():
        # Bot riêng: chỉ trả lời chat của chủ. Người gõ lệnh thì được biết chat ID của mình,
        # để chủ bot cài sai TELEGRAM_CHAT_ID còn biết đường sửa.
        if chat_id and text.startswith("/"):
            send_telegram(token, chat_id, f"Bot này là bot riêng. Chat ID của bạn: {chat_id}\n"
                                          "Nếu bạn là chủ bot: đặt TELEGRAM_CHAT_ID trên Vercel đúng "
                                          "số này rồi Redeploy.")
        return
    if text.startswith("/"):
        try:  # hiện "đang nhập…" trong lúc lấy dữ liệu, /bantin mất cả chục giây
            telegram(token, "sendChatAction", chat_id=chat_id, action="typing")
        except Exception as e:
            print(f"[lỗi] sendChatAction: {e!r}", file=sys.stderr)
    try:
        reply = answer(text)
    except Exception as e:
        print(f"[lỗi] trả lời {text!r}: {e!r}", file=sys.stderr)
        reply = "⚠️ Bot gặp lỗi khi lấy dữ liệu, thử lại sau nhé."
    if reply:
        send_telegram(token, chat_id, reply)


def setup(token, host):
    url = f"https://{host}/api/telegram"
    telegram(token, "setWebhook", url=url, secret_token=webhook_secret(token),
             allowed_updates=["message"])
    telegram(token, "setMyCommands", commands=MENU)
    info = telegram(token, "getWebhookInfo")
    lines = [f"Đã cài webhook: {info['url']}",
             f"Tin nhắn đang chờ: {info.get('pending_update_count', 0)}"]
    if info.get("last_error_message"):
        lines.append(f"Lỗi gần nhất từ Telegram: {info['last_error_message']}")
    return lines


def status_page(token, environ):
    missing = [k for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID") if not os.environ.get(k, "").strip()]
    if missing:
        return f"Thiếu biến môi trường trên Vercel: {', '.join(missing)}. Thêm vào rồi Redeploy."
    host = os.environ.get("VERCEL_PROJECT_PRODUCTION_URL") or environ.get("HTTP_HOST")
    try:
        lines = setup(token, host)
    except Exception as e:
        return f"Không cài được webhook: {e!r}"
    return "\n".join(lines + [f"Chỉ trả lời chat ID: {owner_chat()}",
                              "", "Xong! Vào Telegram gõ /stock để thử."])


def respond(start_response, status, text):
    body = text.encode("utf-8")
    start_response(status, [("Content-Type", "text/plain; charset=utf-8"),
                            ("Content-Length", str(len(body)))])
    return [body]


def app(environ, start_response):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if environ["REQUEST_METHOD"] != "POST":
        return respond(start_response, "200 OK", status_page(token, environ))
    secret = environ.get("HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN", "").encode()
    if not token or not hmac.compare_digest(secret, webhook_secret(token).encode()):
        return respond(start_response, "403 Forbidden", "sai secret")
    try:
        length = int(environ.get("CONTENT_LENGTH") or 0)
        handle_update(json.loads(environ["wsgi.input"].read(length)), token)
    except (Exception, SystemExit) as e:  # send_telegram báo lỗi bằng SystemExit
        print(f"[lỗi] {e!r}", file=sys.stderr)
    # Luôn trả 200, kẻo Telegram gửi lại mãi một tin nhắn gây lỗi
    return respond(start_response, "200 OK", "ok")
