"""Cổng ra tỷ giá ngoại tệ của Vietcombank (XML). Chỉ gọi và đọc kết quả."""
import urllib.request
import xml.etree.ElementTree as ET

VCB_FX = "https://portal.vietcombank.com.vn/Usercontrols/TVPortal.TyGia/pXML.aspx"


def fx_rates():
    """{mã ngoại tệ: giá đồng} Vietcombank mua chuyển khoản, không có thì mua tiền mặt."""
    req = urllib.request.Request(VCB_FX, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        root = ET.fromstring(r.read())
    rates = {}
    for row in root.iter("Exrate"):
        for field in ("Transfer", "Buy"):
            value = (row.get(field) or "").replace(",", "").strip()
            if value and value != "-":
                rates[row.get("CurrencyCode")] = float(value)
                break
    return rates
