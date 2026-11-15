"""Xem thử bot chi tiêu trên máy: chỉ đọc và xếp nhóm, không ghi.

Chạy: python -m interface.chitieu.preview "cà phê 35k"   (nhiều khoản thì ngăn bằng \\n)
"""
import sys

from interface.chitieu.context import name, parse_line, today, vnd


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    for line in " ".join(sys.argv[1:]).split("\\n"):
        e = parse_line(line, today())
        print(f"{line!r} -> " + (f"{vnd(e['tien'])} · {name(e['nhom'])} · {e['ghichu']!r} · {e['ngay']}"
                                 if e else "không thấy số tiền"))


if __name__ == "__main__":
    main()
