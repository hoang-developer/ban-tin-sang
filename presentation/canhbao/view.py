"""Chữ của các cảnh báo tức thì (tin nhắn HTML cho Telegram)."""
import html

from domain.canhbao.rules import rain_label
from domain.common.format import vn_num


def rain_desc(info, start, name="Hà Nội"):
    return (f"khoảng {start:%H:%M} (~{info['minutes']} phút nữa) {name} có "
            f"{rain_label(info['peak'])}{' kèm dông ⛈️' if info['storm'] else ''}")


def alert_text(a):
    """Một cảnh báo (dict do services/canhbao tạo) -> tin nhắn."""
    kind = a["kind"]
    if kind == "rain":
        return f"☔ <b>Sắp mưa</b>: {rain_desc(a, a['start'])}. Nhớ mang áo mưa!"
    if kind == "air":
        return (f"{a['icon']} <b>Không khí chuyển sang mức {a['label'].lower()}</b>: AQI {a['aqi']:.0f}. "
                "Nên đeo khẩu trang, hạn chế ra ngoài.")
    if kind == "gold":
        word, icon = ("tăng", "📈") if a["change"] > 0 else ("giảm", "📉")
        return (f"🪙 <b>Vàng SJC {word} {vn_num(abs(a['change']), 1)} triệu</b> {icon}: giá bán "
                f"{vn_num(a['base'], 1)} → {vn_num(a['price'], 1)} triệu đồng/lượng")
    if kind == "index":
        word, icon = ("tăng", "🚀") if a["pct"] > 0 else ("giảm", "🔻")
        return (f"{icon} <b>VN-Index {word} mạnh</b>: {vn_num(a['close'])} điểm "
                f"({vn_num(a['pct'], sign=True)}%)")
    if kind == "watch":
        return (f"🎯 <b>{a['symbol']} {a['word']} {vn_num(a['target'] * 1000, 0)}đ</b>: "
                f"giá hiện tại {vn_num(a['price'] * 1000, 0)}đ")
    return (f"📰 <b>{html.escape(a['keyword'])}</b> · {a['source']}: "
            f'<a href="{html.escape(a["link"])}">{html.escape(a["title"], quote=False)}</a>')
