"""Tìm tin tức theo từ khóa cho bot: /tin giá vàng, /tin giá vàng 24h.

Xem thử: python -m interface.tintuc.search giá vàng 24h
"""
import sys
from datetime import datetime, timezone

from domain.tintuc.rules import parse_query  # noqa: F401
from interface.bantin.bulletin import news as headlines
from presentation.tintuc import view
from services.tintuc import search


def results_text(keyword, hours):
    found, backup = search.results(keyword, hours)
    return view.results_text(keyword, hours, found, backup, datetime.now(timezone.utc))


def headlines_text():
    return view.headlines_text(headlines())


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    keyword, hours = parse_query(sys.argv[1:])
    print(results_text(keyword, hours) if keyword else headlines_text())


if __name__ == "__main__":
    main()
