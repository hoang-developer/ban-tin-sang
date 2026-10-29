"""Lịch chạy của bot: cron-job.org gọi mỗi 15 phút, GitHub Actions gọi dự phòng (cách cài: README).

GET /api/tick?key=<khóa>: chạy các việc đã tới giờ (lich.py). Khóa xem bằng lệnh /caidat trong Telegram.
"""
import hmac
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # để import các file ở thư mục gốc

import kho  # noqa: E402
import lich  # noqa: E402
import tg  # noqa: E402
from bantin import VN_TZ  # noqa: E402


def respond(start_response, status, text):
    body = text.encode("utf-8")
    start_response(status, [("Content-Type", "text/plain; charset=utf-8"),
                            ("Content-Length", str(len(body)))])
    return [body]


def app(environ, start_response):
    key = (parse_qs(environ.get("QUERY_STRING", "")).get("key") or [""])[0].encode()
    if not tg.token() or not hmac.compare_digest(key, tg.derived_secret("tick").encode()):
        return respond(start_response, "403 Forbidden", "sai khóa")
    if not kho.ready():
        # Mã lỗi để GitHub Actions biết mà tự chạy cảnh báo theo cách cũ
        return respond(start_response, "503 Service Unavailable", "chưa có kho dữ liệu (xem README)")
    now = datetime.now(VN_TZ)
    # Hai lời gọi sát nhau (cron-job.org và GitHub) thì chỉ một lượt chạy
    if not kho.put_new("khoa:tick", now.isoformat(), 300):
        return respond(start_response, "200 OK", "lượt khác đang chạy")
    try:
        notes = lich.run(now)
    finally:
        kho.delete("khoa:tick")
    return respond(start_response, "200 OK", "\n".join(notes))
