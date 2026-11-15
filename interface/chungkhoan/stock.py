"""Thông tin chứng khoán cho lệnh /stock của bot Telegram.

Xem thử: python -m interface.chungkhoan.stock           (tổng quan phiên hiện tại)
         python -m interface.chungkhoan.stock FPT VNM   (chi tiết từng mã)
Giữ tên cũ (stock_command, quote, quotes, news, dong...) để bot và lịch chạy dùng lại.
"""
import html
import sys
from concurrent.futures import ThreadPoolExecutor

from domain.chungkhoan.rules import MAX_SYMBOLS, NEWS_COUNT, SYMBOL, published_at  # noqa: F401
from infrastructure import clock
from interface.bantin.bulletin import stocks
from presentation.chungkhoan import view
from presentation.chungkhoan.view import change, color, dong  # noqa: F401
from services.chungkhoan import market
from services.chungkhoan.market import google_news, index_rows, quote, quotes  # noqa: F401


def news(symbol, count=NEWS_COUNT):
    return view.news_lines(market.news(symbol, count))


def market_summary():
    now = clock.now_vn()
    table, movers = market.summary_data()
    # VPS lỗi thì lấy giá theo ngày của VNDirect
    index_part = view.index_lines(table) if table else stocks()
    return view.summary(now, index_part, view.mover_lines(*movers) if movers else None)


def stock_detail(symbol):
    return view.detail(symbol, *market.detail(symbol))


def stock_command(args):
    """/stock -> tổng quan phiên; /stock FPT VNM -> chi tiết từng mã."""
    if not args:
        return market_summary()
    symbols = list(dict.fromkeys(a.upper() for a in args))
    bad = [s for s in symbols if not SYMBOL.fullmatch(s)]
    if bad:
        return f"Mã không hợp lệ: {html.escape(' '.join(bad))}. Ví dụ: /stock FPT"
    with ThreadPoolExecutor() as pool:
        text = "\n\n━━━━━━━━━━\n\n".join(pool.map(stock_detail, symbols[:MAX_SYMBOLS]))
    if len(symbols) > MAX_SYMBOLS:
        text += f"\n\n<i>Mỗi lần xem tối đa {MAX_SYMBOLS} mã.</i>"
    return text


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    print(stock_command(sys.argv[1:]))


if __name__ == "__main__":
    main()
