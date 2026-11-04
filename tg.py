"""Gọi Telegram Bot API: gửi, sửa, ghim tin nhắn có nút bấm, gửi file."""
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
import uuid


class TelegramError(Exception):
    def __init__(self, code, description):
        super().__init__(f"{code}: {description}")
        self.code, self.description = code, description


def token():
    return os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()  # dán trên điện thoại hay dính dấu cách


def owner_chat():
    return os.environ.get("TELEGRAM_CHAT_ID", "").strip()


def derived_secret(purpose, tok=None):
    """Khóa bí mật suy ra từ token bot (webhook, lịch chạy...), khỏi phải tạo thêm biến môi trường.

    Không có token thì không giả được; đổi token thì khóa cũng đổi theo.
    """
    return hashlib.sha256(f"{purpose}:{tok or token()}".encode()).hexdigest()[:32]


def post(method, body, content_type, tok=None):
    req = urllib.request.Request(f"https://api.telegram.org/bot{tok or token()}/{method}",
                                 data=body, headers={"Content-Type": content_type})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())["result"]
    except urllib.error.HTTPError as e:
        raise TelegramError(e.code, json.loads(e.read() or b"{}").get("description", "")) from None


def call(method, tok=None, **params):
    return post(method, json.dumps(params).encode(), "application/json", tok)


def send_document(chat_id, filename, data, caption="", tok=None):
    """Gửi file (bytes) vào chat, ví dụ bảng chi tiêu CSV."""
    boundary = uuid.uuid4().hex
    parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
             for k, v in (("chat_id", chat_id), ("caption", caption)) if v]
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="document"; filename="{filename}"\r\n'
                 f"Content-Type: application/octet-stream\r\n\r\n".encode() + data + b"\r\n")
    body = b"".join(parts) + f"--{boundary}--\r\n".encode()
    return post("sendDocument", body, f"multipart/form-data; boundary={boundary}", tok)


def keyboard(buttons):
    """[[(nhãn, dữ liệu), ...], ...] -> nút bấm dưới tin; dữ liệu là chuỗi gửi về khi bấm."""
    return {"inline_keyboard": [[{"text": text, "callback_data": data} for text, data in row]
                                for row in buttons or []]}


def send(chat_id, text, buttons=None, tok=None):
    extra = {"reply_markup": keyboard(buttons)} if buttons else {}
    return call("sendMessage", tok, chat_id=chat_id, text=text, parse_mode="HTML",
                link_preview_options={"is_disabled": True}, **extra)


def edit(chat_id, message_id, text, buttons=None, tok=None):
    try:
        return call("editMessageText", tok, chat_id=chat_id, message_id=message_id, text=text,
                    parse_mode="HTML", link_preview_options={"is_disabled": True},
                    reply_markup=keyboard(buttons))
    except TelegramError as e:
        if "message is not modified" in e.description:  # nội dung y hệt, không phải lỗi
            return None
        raise


def edit_buttons(chat_id, message_id, buttons, tok=None):
    return call("editMessageReplyMarkup", tok, chat_id=chat_id, message_id=message_id,
                reply_markup=keyboard(buttons))


def send_reply(chat_id, reply, tok=None):
    """Gửi câu trả lời của một lệnh: tin HTML, (tin, nút bấm), hoặc {"file", "name", "caption"}."""
    if isinstance(reply, dict):
        return send_document(chat_id, reply["name"], reply["file"], reply.get("caption", ""), tok)
    text, buttons = reply if isinstance(reply, tuple) else (reply, None)
    return send(chat_id, text, buttons, tok)


def handle_button(query, on_button, now, tok=None):
    """Lượt bấm nút: on_button(dữ liệu, tin, giờ) trả (thông báo nhỏ, việc tiếp theo).

    Trả lời ngay cho nút thôi quay, rồi mới làm việc chậm: "edit" sửa chính tin, "send" gửi tin mới,
    "buttons" chỉ thay nút.
    """
    message = query.get("message") or {}
    chat_id = (message.get("chat") or {}).get("id")
    try:
        toast, action = on_button(query.get("data") or "", message, now)
    except Exception as e:
        print(f"[lỗi] nút {query.get('data')!r}: {e!r}", file=sys.stderr)
        toast, action = "⚠️ Bot gặp lỗi, thử lại sau nhé", None
    call("answerCallbackQuery", tok, callback_query_id=query["id"], **({"text": toast} if toast else {}))
    if not action:
        return
    how, make = action
    try:
        reply = make()
    except Exception as e:
        print(f"[lỗi] nút {query.get('data')!r}: {e!r}", file=sys.stderr)
        reply, how = "⚠️ Bot gặp lỗi khi lấy dữ liệu, thử lại sau nhé.", "send"
    if how == "send":
        send_reply(chat_id, reply, tok)
    elif how == "buttons":
        edit_buttons(chat_id, message["message_id"], reply, tok)
    else:
        text, buttons = reply if isinstance(reply, tuple) else (reply, None)
        edit(chat_id, message["message_id"], text, buttons, tok)
