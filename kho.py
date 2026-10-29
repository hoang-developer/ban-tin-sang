"""Kho dữ liệu của bot: Upstash Redis gọi qua REST, cài từ Vercel Marketplace (xem README).

Mỗi khóa giữ một giá trị JSON: danh sách theo dõi, ngày cần nhắc, ví vàng, trạng thái cảnh báo...
"""
import json
import os
import urllib.request


class KhoError(Exception):
    pass


def config():
    """(địa chỉ REST, token) của Upstash, (None, None) nếu chưa kết nối."""
    for url_key, token_key in [("KV_REST_API_URL", "KV_REST_API_TOKEN"),
                               ("UPSTASH_REDIS_REST_URL", "UPSTASH_REDIS_REST_TOKEN")]:
        if os.environ.get(url_key) and os.environ.get(token_key):
            return os.environ[url_key], os.environ[token_key]
    # Lúc kết nối, Vercel cho đặt tiền tố riêng: <TIỀN_TỐ>_KV_REST_API_URL...
    for key, url in os.environ.items():
        if key.endswith("_REST_API_URL") and os.environ.get(key[:-3] + "TOKEN"):
            return url, os.environ[key[:-3] + "TOKEN"]
    return None, None


def ready():
    return config()[0] is not None


def command(*args):
    url, token = config()
    if not url:
        raise KhoError("Chưa có kho dữ liệu: cài Upstash Redis theo README rồi Redeploy")
    req = urllib.request.Request(url, data=json.dumps([str(a) for a in args]).encode(),
                                 headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=10) as r:
        res = json.loads(r.read())
    if "error" in res:
        raise KhoError(res["error"])
    return res["result"]


def get(key, default=None):
    value = command("GET", key)
    return default if value is None else json.loads(value)


def put(key, value, seconds=None):
    args = ["SET", key, json.dumps(value, ensure_ascii=False)]
    command(*(args + ["EX", seconds] if seconds else args))


def put_new(key, value, seconds):
    """Ghi nếu khóa chưa có (dùng làm khóa chạy, đánh dấu đã làm); True nếu ghi được."""
    return command("SET", key, json.dumps(value, ensure_ascii=False), "NX", "EX", seconds) == "OK"


def delete(key):
    command("DEL", key)
