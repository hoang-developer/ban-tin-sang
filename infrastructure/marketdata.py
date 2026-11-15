"""Nguồn giá vàng (SJC, PNJ), lịch sử chỉ số chứng khoán (VNDirect, SSI) và tin RSS."""
import sys
import time
import urllib.parse
import xml.etree.ElementTree as ET

from infrastructure.web import fetch, fetch_json

PNJ_GOLD_URL = "https://edge-api.pnj.io/ecom-frontend/v1/get-gold-price?zone=00"
SJC_URL = "https://sjc.com.vn/GoldPrice/Services/PriceService.ashx"


def sjc_gold():
    """Bảng giá vàng SJC Hà Nội: JSON gốc {"data": [...], "latestDate": ...}."""
    body = urllib.parse.urlencode({"method": "GetCurrentGoldPricesByBranch", "BranchId": 2}).encode()
    return fetch_json(SJC_URL, data=body)


def pnj_gold():
    """Bảng giá vàng PNJ: {mã sản phẩm: dòng giá}; giá tính nghìn đồng/chỉ."""
    return {r["masp"]: r for r in fetch_json(PNJ_GOLD_URL)["data"]}


def index_history(vnd_symbol, ssi_symbol, days=15):
    """(mốc thời gian, giá đóng cửa) theo ngày; VNDirect trước, lỗi thì SSI."""
    now = int(time.time())
    start = now - days * 86400
    try:
        d = fetch_json("https://dchart-api.vndirect.com.vn/dchart/history"
                       f"?resolution=D&symbol={vnd_symbol}&from={start}&to={now}")
        if d.get("c"):
            return d["t"], d["c"]
    except Exception as e:
        print(f"[lỗi] VNDirect {vnd_symbol}: {e!r}", file=sys.stderr)
    if not ssi_symbol:
        raise RuntimeError(f"không có dữ liệu {vnd_symbol}")
    d = fetch_json("https://iboard-api.ssi.com.vn/statistics/charts/history"
                   f"?resolution=1D&symbol={ssi_symbol}&from={start}&to={now}")["data"]
    return d["t"], d["c"]


def feed_items(url, count):
    """Các mục <item> đầu của một nguồn RSS (tối đa count)."""
    return ET.fromstring(fetch(url)).findall(".//item")[:count]
