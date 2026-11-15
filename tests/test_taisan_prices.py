"""Giá tài sản: các nguồn (mạng giả), nhớ tạm theo loại, giá cũ khi nguồn lỗi."""
import io
import unittest
import urllib.request

from tests import harness as h

from services.chungkhoan import market as chungkhoan
from infrastructure import crypto, fmarket, vietcombank, web
from repositories.taisan import assets as assets_repo
from services.taisan import prices as svc

XML = (b'<ExrateList><Exrate CurrencyCode="USD" Buy="25,100" Transfer="25,200"/>'
       b'<Exrate CurrencyCode="EUR" Buy="27,000" Transfer="-"/><Exrate CurrencyCode="XXX" Buy="-" Transfer="-"/></ExrateList>')


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Nguon(unittest.TestCase):
    def setUp(self):
        h.reset()
        h.at(2026, 11, 1, 10)
        self.mode = "ok"
        self.calls = []
        self.saved = (web.http_json, urllib.request.urlopen, chungkhoan.quotes, svc.gold_prices, dict(svc.SOURCES))
        web.http_json = self.http
        urllib.request.urlopen = lambda req, timeout=None: Resp(XML)
        chungkhoan.quotes = lambda codes: {c: {"price": None if c == "REF" else 95000, "ref": 94000 if c != "ZERO" else 0}
                                           for c in codes}
        svc.gold_prices = lambda: {"sjc": [138.5, 0], "nhan": [136.2, 0]}
        svc.SOURCES.update({"cp": (svc.stock_prices, 5), "etf": (svc.stock_prices, 5), "vang": (svc.gold_table, 30),
                            "quy": (svc.fund_navs, 120), "coin": (svc.coin_prices, 30), "ngoaite": (svc.fx_rates, 60)})
        self.addCleanup(self.restore)

    def restore(self):
        web.http_json, urllib.request.urlopen, chungkhoan.quotes, svc.gold_prices = self.saved[:4]
        svc.SOURCES.clear()
        svc.SOURCES.update(self.saved[4])

    def http(self, url, body=None):
        self.calls.append(url.split("?")[0])
        if "fmarket" in url:
            if self.mode == "fmarket_down":
                raise RuntimeError("fmarket lỗi")
            return {"data": {"rows": [{"shortName": "vmeef", "nav": "15458.5"}, {"shortName": "VFF", "nav": 21000},
                                      {"shortName": None, "nav": 1}, {"shortName": "X", "nav": None}]}}
        if "coingecko" in url:
            if self.mode in ("gecko_down", "all_down"):
                raise RuntimeError("429")
            if self.mode == "gecko_empty":
                return {}
            return {"bitcoin": {"vnd": 2.5e9}, "ethereum": {"vnd": None}, "tether": {"vnd": 25500}}
        if "coinbase" in url:
            if self.mode == "all_down" or "ETH" in url:
                raise RuntimeError("coinbase lỗi")
            return {"data": {"amount": "65000.5"}}
        raise RuntimeError("url lạ " + url)

    def test_cac_nguon(self):
        self.assertEqual(svc.stock_prices(["FPT", "REF", "ZERO"]), {"FPT": 95000, "REF": 94000, "ZERO": 95000})
        self.assertEqual(svc.gold_table(), {"sjc": 138_500_000.0, "nhan": 136_200_000.0})
        self.assertEqual(svc.fund_navs(), {"VMEEF": 15458.5, "VFF": 21000.0})
        self.assertEqual(fmarket.fund_navs(), {"VMEEF": 15458.5, "VFF": 21000.0})
        self.assertEqual(svc.fx_rates(), {"USD": 25200.0, "EUR": 27000.0})  # chuyển khoản, không có thì tiền mặt
        self.assertEqual(vietcombank.fx_rates(), svc.fx_rates())

    def test_gia_tien_so(self):
        self.assertEqual(crypto.coingecko_vnd(["bitcoin", "ethereum", "tether"]),
                         {"bitcoin": 2.5e9, "tether": 25500.0})  # mã không có giá (ethereum) bị bỏ
        self.assertEqual(crypto.coinbase_usd("btc"), 65000.5)
        self.assertEqual(svc.coin_prices(["btc", "eth", "usdt"]), {"btc": 2.5e9, "usdt": 25500.0})
        self.mode = "gecko_down"  # CoinGecko lỗi: giá Coinbase USD × tỷ giá Vietcombank
        self.assertEqual(svc.coin_prices(["btc", "eth"]), {"btc": 65000.5 * 25200.0})  # eth lỗi thì bỏ qua
        self.mode = "gecko_empty"
        self.assertEqual(svc.coin_prices(["btc"]), {"btc": 65000.5 * 25200.0})
        self.mode = "all_down"
        self.assertEqual(svc.coin_prices(["btc"]), {})

    def test_nho_tam_theo_loai(self):
        first = svc.prices("coin", ["btc", "usdt"])
        self.assertEqual(first, ({"btc": 2.5e9, "usdt": 25500.0}, "2026-11-01T10:00+07:00", False))
        n = len(self.calls)
        self.assertEqual(svc.prices("coin", ["btc", "usdt"]), first)
        self.assertEqual(len(self.calls), n)  # còn hạn: dùng giá đã lưu
        svc.prices("coin", ["btc"], fresh=True)
        self.assertGreater(len(self.calls), n)  # fresh: bỏ qua giá đã lưu
        n = len(self.calls)
        h.at(2026, 11, 1, 10, 31)  # coin chỉ nhớ 30 phút
        svc.prices("coin", ["btc"])
        self.assertGreater(len(self.calls), n)
        self.assertEqual(assets_repo.price_cache("coin")[1], "2026-11-01T10:31+07:00")

    def test_thieu_ma_thi_lay_lai(self):
        svc.prices("coin", ["btc"])
        n = len(self.calls)
        svc.prices("coin", ["btc", "usdt"])
        self.assertGreater(len(self.calls), n)  # có mã mới chưa có trong giá đã lưu

    def test_nguon_loi_thi_dung_gia_cu(self):
        good = svc.prices("quy", ["VMEEF"])
        self.mode = "fmarket_down"
        h.at(2026, 11, 1, 14)  # quá 120 phút: phải lấy lại, nguồn lỗi
        self.assertEqual(svc.prices("quy", ["VMEEF"]), (good[0], good[1], True))  # giá cũ, báo là giá cũ
        self.assertEqual(svc.prices("coin", []), ({}, None, False))
        self.mode = "all_down"  # nguồn trả rỗng (không phải lỗi): coi là lấy xong, lưu giá rỗng
        self.assertEqual(svc.prices("coin", ["btc"], fresh=True), ({}, "2026-11-01T14:00+07:00", False))

    def test_cac_loai(self):
        self.assertEqual(svc.prices("ngoaite", ["USD"], fresh=True)[0]["USD"], 25200.0)
        self.assertEqual(svc.prices("quy", ["VMEEF"], fresh=True)[0]["VMEEF"], 15458.5)
        self.assertEqual(svc.prices("vang", ["sjc", "nhan"], fresh=True)[0]["sjc"], 138_500_000.0)
        self.assertEqual(svc.prices("cp", ["FPT"], fresh=True)[0], {"FPT": 95000})


if __name__ == "__main__":
    unittest.main()
