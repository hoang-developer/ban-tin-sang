"""Cổng ra giá tiền số: CoinGecko (đồng) và Coinbase (USD). Chỉ gọi và đọc kết quả."""
from infrastructure import web


def coingecko_vnd(ids):
    """{mã CoinGecko: giá đồng} của các mã có giá."""
    data = web.http_json("https://api.coingecko.com/api/v3/simple/price?vs_currencies=vnd&ids=" + ",".join(ids))
    return {i: float(v["vnd"]) for i, v in data.items() if v.get("vnd")}


def coinbase_usd(code):
    """Giá USD hiện tại của một đồng (btc, eth...) trên Coinbase."""
    return float(web.http_json(f"https://api.coinbase.com/v2/prices/{code.upper()}-USD/spot")["data"]["amount"])
