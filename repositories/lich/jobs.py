"""Đánh dấu việc theo giờ đã làm trong ngày (để lịch chạy nhiều lần không làm lại)."""
from infrastructure import kho
from repositories import keys

KEEP_DAYS = 3


def done_today(job, now):
    return kho.get(keys.job_done(job, now.date())) is not None


def mark_done(job, now):
    kho.put(keys.job_done(job, now.date()), True, KEEP_DAYS * 86400)
