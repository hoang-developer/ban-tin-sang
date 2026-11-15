"""Giá tài sản: lấy từ nguồn, nhớ trong kho; nguồn lỗi thì dùng giá gần nhất."""
import sys
from datetime import datetime

from services.chungkhoan import market as chungkhoan  # giá cổ phiếu
from services.bantin.data import gold_prices
from domain.taisan.kinds import COINS
from infrastructure import clock, crypto, fmarket, vietcombank
from repositories.taisan import assets as assets_repo


def stock_prices(codes):
    quotes = chungkhoan.quotes(codes)
    return {s: q["price"] or q["ref"] for s, q in quotes.items() if q["price"] or q["ref"]}


def gold_table(codes=None):
    p = gold_prices()  # triệu đồng/lượng, giá cửa hàng mua vào
    return {"sjc": p["sjc"][0] * 1e6, "nhan": p["nhan"][0] * 1e6}


def fund_navs(codes=None):
    return fmarket.fund_navs()


def coin_prices(codes):
    """Giá tiền số (đồng): CoinGecko; bị chặn hay quá lượt thì lấy giá USD trên Coinbase × tỷ giá Vietcombank."""
    ids = {COINS.get(c, c): c for c in codes}
    try:
        got = {ids[i]: v for i, v in crypto.coingecko_vnd(list(ids)).items()}
        if got:
            return got
    except Exception as e:
        print(f"[lỗi] CoinGecko, chuyển sang Coinbase: {e!r}", file=sys.stderr)
    usd = prices("ngoaite", ["USD"])[0].get("USD")
    if not usd:
        raise RuntimeError("không có tỷ giá USD để đổi giá tiền số")
    got = {}
    for code in codes:
        try:
            got[code] = crypto.coinbase_usd(code) * usd
        except Exception as e:
            print(f"[lỗi] Coinbase {code}: {e!r}", file=sys.stderr)
    return got


def fx_rates(codes=None):
    return vietcombank.fx_rates()


SOURCES = {  # loại: (hàm lấy giá theo danh sách mã, số phút còn dùng được giá đã lưu)
    "cp": (stock_prices, 5), "etf": (stock_prices, 5), "vang": (gold_table, 30), "quy": (fund_navs, 120), "coin": (coin_prices, 30),
    "ngoaite": (fx_rates, 60)}


def prices(kind, codes, fresh=False):
    """(giá {mã: đồng}, lúc cập nhật, có phải giá cũ do nguồn lỗi). fresh=True thì bỏ qua giá đã lưu."""
    codes = sorted(set(codes))
    if not codes:
        return {}, None, False
    fetch, minutes = SOURCES[kind]
    saved, when = assets_repo.price_cache(kind)
    if not fresh and when and all(c in saved for c in codes) and \
            (clock.now_vn() - datetime.fromisoformat(when)).total_seconds() < minutes * 60:
        return saved, when, False
    try:
        got = fetch(codes)  # mã nguồn không có (mã sai) thì không có trong got; không phải lỗi nguồn
        when = clock.now_vn().isoformat(timespec="minutes")
        saved = {**saved, **got}
        assets_repo.save_price_cache(kind, saved, when)
        return saved, when, False
    except Exception as e:
        print(f"[lỗi] giá {kind}: {e!r}", file=sys.stderr)
        return saved, when, True
