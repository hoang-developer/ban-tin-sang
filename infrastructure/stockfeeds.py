"""Nguồn giá chứng khoán: VPS, VCI (Vietcap) và Google News RSS. Gọi nhanh: nguồn nào chậm quá 8 giây thì bỏ."""
import gzip
import json
import urllib.parse
import urllib.request

from infrastructure.web import UA

VPS = "https://bgapidatafeed.vps.com.vn"
VCI = "https://trading.vietcap.com.vn/api/price/symbols"
TIMEOUT = 8  # lệnh cần trả lời nhanh, nguồn nào chậm quá thì bỏ


def get(url, payload=None):
    headers = {"User-Agent": UA}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        body = r.read()
    return gzip.decompress(body) if body[:2] == b"\x1f\x8b" else body  # VCI luôn nén gzip


def get_json(url, payload=None):
    return json.loads(get(url, payload))


def vci_quotes(symbols):
    """Giá các mã từ VCI: danh sách dòng gốc."""
    return get_json(f"{VCI}/getList", {"symbols": list(symbols)})


def vps_quote(symbol):
    """Giá một mã từ VPS (dự phòng): danh sách dòng gốc."""
    return get_json(f"{VPS}/getliststockdata/{symbol}")


def vps_indices(codes):
    """Chi tiết các chỉ số từ VPS theo mã chỉ số bên VPS."""
    return get_json(f"{VPS}/getlistindexdetail/{','.join(codes)}")


def vci_group(group):
    """Các mã trong một rổ (VN30, HOSE...) từ VCI."""
    return get_json(f"{VCI}/getByGroup?group={group}")


def google_news_xml(query):
    """Kết quả tìm Google News (RSS, tiếng Việt) dạng bytes."""
    q = urllib.parse.quote(query)
    return get(f"https://news.google.com/rss/search?q={q}&hl=vi&gl=VN&ceid=VN:vi")
