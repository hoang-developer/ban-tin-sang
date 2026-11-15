"""Đầu tư quỹ mở: dữ liệu quỹ trên Fmarket (NAV, thông tin) nhớ tạm trong kho, và phiên giao dịch kế tiếp.

Phiên kế tiếp: {"phien": ngày khớp lệnh, "dong": lúc đóng sổ lệnh, "du_phong": True nếu tự đoán (không có dữ liệu Fmarket:
theo các thứ quỹ có NAV gần đây, VMEEF mọi ngày làm việc, VFF thứ Ba và thứ Năm; đóng sổ 14:40 ngày làm việc trước phiên;
chưa tính ngày lễ)}.
"""
import sys
from datetime import date, datetime, timedelta

from domain.common.dates import VN_TZ
from domain.dautu import calendar as rules
from domain.dautu.calendar import ym_of
from infrastructure import fmarket
from repositories.dautu import market as market_repo


def now_vn():
    return datetime.now(VN_TZ)


def find_fund(code):
    """(id, tên quỹ) trên Fmarket theo mã; None nếu không thấy."""
    return fmarket.find_fund(code)


def nav_history(cfg, fresh=False):
    """[(ngày, NAV)] khoảng 400 phiên gần nhất. Lưu trong kho 2 tiếng; nguồn lỗi thì dùng bản đã lưu."""
    store = market_repo.load_nav(cfg["ma"])
    if store.get("ma") == cfg["ma"] and store.get("nav") and not fresh and \
            (now_vn() - datetime.fromisoformat(store["luc"])).total_seconds() < 2 * 3600:
        return [(date.fromisoformat(d), v) for d, v in store["nav"]]
    try:
        navs = fmarket.nav_history(cfg["id"], now_vn().strftime("%Y%m%d"))
        if navs:
            market_repo.save_nav(cfg["ma"], now_vn().isoformat(timespec="minutes"), navs)
            return [(date.fromisoformat(d), v) for d, v in navs]
    except Exception as e:
        print(f"[lỗi] NAV {cfg['ma']}: {e!r}", file=sys.stderr)
    if store.get("ma") == cfg["ma"]:
        return [(date.fromisoformat(d), v) for d, v in store.get("nav", [])]
    return []


def fund_info(cfg, fresh=False):
    """Chi tiết quỹ của Fmarket (phiên giao dịch kế tiếp, top 10 mã, phí); lưu 1 tiếng, lỗi thì dùng bản cũ."""
    store = market_repo.load_info(cfg["ma"])
    if store.get("ma") == cfg["ma"] and not fresh and \
            (now_vn() - datetime.fromisoformat(store["luc"])).total_seconds() < 3600:
        return store["data"]
    try:
        keep = fmarket.fund_detail(cfg["id"])
        market_repo.save_info(cfg["ma"], now_vn().isoformat(timespec="minutes"), keep)
        return keep
    except Exception as e:
        print(f"[lỗi] thông tin quỹ {cfg['ma']}: {e!r}", file=sys.stderr)
        return store.get("data") if store.get("ma") == cfg["ma"] else None


def next_trading(cfg, d, include=False):
    """Ngày giao dịch đầu tiên sau d (include: tính cả d). Theo lịch NAV thật nếu có (bỏ ngày lễ), không thì
    thứ Hai–thứ Sáu."""
    return rules.next_trading_from(nav_history(cfg), d, include)


def session(cfg, now=None):
    """Phiên kế tiếp của quỹ cfg (xem đầu file)."""
    now = now or now_vn()
    info = fund_info(cfg) or {}
    s = info.get("phien") or {}
    try:
        trading, closing = rules.parse_session(s)
        if closing > now:
            return {"phien": trading, "dong": closing, "du_phong": False}
        if now - closing < timedelta(hours=1):  # vừa qua giờ đóng sổ, bản lưu chưa đổi: hỏi lại Fmarket
            s = (fund_info(cfg, fresh=True) or {}).get("phien") or {}
            trading, closing = rules.parse_session(s)
            if closing > now:
                return {"phien": trading, "dong": closing, "du_phong": False}
    except (KeyError, TypeError, ValueError):
        pass
    return rules.guessed_session(next_trading(cfg, rules.earliest_order_day(now)))  # phiên kế tiếp theo lịch của quỹ này


def is_deadline(cfg, now=None):
    """Hôm nay là hạn đặt lệnh của tháng (phiên đóng sổ cuối cùng trong tháng, chưa qua 14:40)?"""
    now = now or now_vn()
    s = session(cfg, now)
    return s["dong"].date() == now.date() and ym_of(s["phien"]) != ym_of(now.date()), s


def current_period(cfg, now=None):
    """Kỳ đang mở: tháng của lần đóng sổ kế tiếp (qua hạn cuối tháng thì đã sang kỳ tháng sau)."""
    return ym_of(session(cfg, now)["dong"].date())
