"""Gọi HTTP JSON ra ngoài (một điểm duy nhất để bộ test giả lập các nguồn dữ liệu)."""
import json
import urllib.request


def http_json(url, body=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")


def fetch(url, data=None):
    """Tải nội dung thô (RSS, HTML, JSON chưa giải mã); data là dữ liệu POST dạng bytes."""
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


def fetch_json(url, data=None):
    return json.loads(fetch(url, data))
