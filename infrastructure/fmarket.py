"""Cổng ra Fmarket: tìm quỹ, lịch sử NAV, chi tiết quỹ (phiên giao dịch kế tiếp, top 10 mã, phí). Chỉ gọi và đọc kết quả,
không nhớ gì (nhớ tạm ở repositories/dautu/market.py)."""
from infrastructure import web

FMARKET = "https://api.fmarket.vn/res"


def find_fund(code):
    """(id, tên quỹ) trên Fmarket theo mã (VMEEF, VESAF, SSISCA...); None nếu không thấy."""
    body = {"types": ["NEW_FUND", "TRADING_FUND"], "issuerIds": [], "sortOrder": "DESC", "sortField": "navTo6Months",
            "page": 1, "pageSize": 100, "isIpo": False, "fundAssetTypes": [], "bondRemainPeriods": [],
            "searchField": code, "isBuyByReward": False, "thirdAppIds": []}
    for r in web.http_json(f"{FMARKET}/products/filter", body)["data"]["rows"]:
        if (r.get("shortName") or "").upper() == code.upper():
            return r["id"], r.get("name") or code
    return None


def nav_history(product_id, to_date):
    """[(ngày ISO, NAV)] khoảng 400 phiên gần nhất tới to_date (YYYYMMDD)."""
    rows = web.http_json(f"{FMARKET}/product/get-nav-history",
                         {"isAllData": 1, "productId": product_id, "fromDate": None, "toDate": to_date})["data"]
    return sorted((p["navDate"], float(p["nav"])) for p in rows if p.get("nav"))[-400:]


def fund_detail(product_id):
    """{"phien": phiên giao dịch kế tiếp, "top": [{"ma", "nganh", "tyle"}], "top_luc": lúc cập nhật danh mục}."""
    d = web.http_json(f"{FMARKET}/products/{product_id}")["data"]
    return {"phien": d.get("productTradingSession"), "top": [
        {"ma": h.get("stockCode"), "nganh": h.get("industry"), "tyle": h.get("netAssetPercent")}
        for h in d.get("productTopHoldingList") or []],
        "top_luc": (d.get("productFund") or {}).get("updateAssetHoldingTime")}


def fund_navs():
    """{mã quỹ: NAV mới nhất} của 100 quỹ đầu danh sách Fmarket."""
    body = {"types": ["NEW_FUND", "TRADING_FUND"], "issuerIds": [], "sortOrder": "DESC", "sortField": "navTo6Months",
            "page": 1, "pageSize": 100, "isIpo": False, "fundAssetTypes": [], "bondRemainPeriods": [],
            "searchField": "", "isBuyByReward": False, "thirdAppIds": []}
    rows = web.http_json(f"{FMARKET}/products/filter", body)["data"]["rows"]
    return {r["shortName"].upper(): float(r["nav"]) for r in rows if r.get("shortName") and r.get("nav")}
