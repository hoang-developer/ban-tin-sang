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


_memo = None  # trong một lượt xử lý tin (memo()): nhớ kết quả GET/HGETALL, ghi khóa nào thì quên khóa đó
READS = ("GET", "HGETALL")


class memo:
    """with kho.memo(): ... — trong khối này đọc lại một khóa thì dùng kết quả đã đọc (một tin nhắn có thể đọc sổ
    tháng, tài sản... vài chục lần). Mọi lệnh ghi đi qua command nên kết quả nhớ luôn khớp với những gì lượt này đã
    ghi; ra khỏi khối thì quên hết, lượt sau đọc mới."""

    def __enter__(self):
        global _memo
        _memo = {}

    def __exit__(self, *exc):
        global _memo
        _memo = None


def command(*args):
    if _memo is None or len(args) < 2:
        return send(*args)
    op, key = str(args[0]).upper(), str(args[1])
    if op in READS:
        if (op, key) not in _memo:
            _memo[(op, key)] = send(*args)
        value = _memo[(op, key)]
        return list(value) if isinstance(value, list) else value
    for read in READS:  # lệnh ghi (hay lệnh lạ): quên khóa này
        _memo.pop((read, key), None)
    return send(*args)


def send(*args):
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
