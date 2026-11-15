"""Gọi HTTP JSON ra ngoài (một điểm duy nhất để bộ test giả lập các nguồn dữ liệu)."""
import json
import urllib.request


def http_json(url, body=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())
