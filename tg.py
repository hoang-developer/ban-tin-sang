"""Gọi Telegram Bot API: gửi, sửa, ghim tin nhắn có nút bấm."""
import hashlib
import json
import os
import urllib.error
import urllib.request


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


def call(method, tok=None, **params):
    req = urllib.request.Request(f"https://api.telegram.org/bot{tok or token()}/{method}",
                                 data=json.dumps(params).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())["result"]
    except urllib.error.HTTPError as e:
        raise TelegramError(e.code, json.loads(e.read() or b"{}").get("description", "")) from None


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
