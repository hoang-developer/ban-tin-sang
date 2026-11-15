"""Các loại tài sản và bảng đổi mã dùng chung."""
COINS = {"btc": "bitcoin", "eth": "ethereum", "usdt": "tether", "bnb": "binancecoin", "sol": "solana",
         "xrp": "ripple", "ada": "cardano", "doge": "dogecoin", "ton": "the-open-network", "trx": "tron"}
TYPES = {"tien": "🏦 Tiền, tài khoản", "tietkiem": "🐷 Tiết kiệm", "etf": "🧺 ETF", "cp": "📈 Cổ phiếu", "quy": "💹 Quỹ mở",
         "vang": "🥇 Vàng", "coin": "🪙 Tiền số", "ngoaite": "💵 Ngoại tệ", "khac": "🏠 Tài sản khác", "no": "💳 Nợ"}
FX_CODES = {"usd", "eur", "jpy", "gbp", "aud", "cad", "chf", "cny", "sgd", "krw", "thb", "hkd", "twd"}
ALIASES = {"tien": "tien", "taikhoan": "tien", "tk": "tien", "vi": "tien", "tietkiem": "tietkiem", "so": "tietkiem",
           "sotietkiem": "tietkiem", "cp": "cp", "cophieu": "cp", "etf": "etf", "chungchiquy": "etf", "quy": "quy", "ccq": "quy", "vang": "vang",
           "coin": "coin", "crypto": "coin", "khac": "khac", "nha": "khac", "xe": "khac", "no": "no", "vay": "no"}
