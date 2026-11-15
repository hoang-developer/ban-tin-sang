"""Chữ của lệnh /tin: kết quả tìm tin theo từ khóa và tin nổi bật."""
import html

from domain.tintuc.rules import ago, window_label


def results_text(keyword, hours, found, backup, now):
    lines = [f"🔎 <b>Tin về “{html.escape(keyword)}”</b> · {window_label(hours)}"]
    if not found:
        lines.append(f"<i>Không có tin nào. Thử từ khóa ngắn hơn hoặc tìm xa hơn: "
                     f"/tin {html.escape(keyword)} 30ngay</i>")
    for title, link, source, published in found:
        meta = " · ".join(x for x in [source, ago(published, now) if published else ""] if x)
        lines.append(f'• <a href="{html.escape(link)}">{html.escape(title, quote=False)}</a>'
                     + (f"\n   <i>{html.escape(meta)}</i>" if meta else ""))
    if backup:
        lines.append("<i>Google News đang lỗi, kết quả lấy từ VnExpress, Dân trí, Tuổi Trẻ, Thanh Niên</i>")
    return "\n".join(lines)


def headlines_text(lines):
    return "📰 <b>Tin nổi bật</b>\n" + "\n".join(lines) + "\n\n<i>Tìm theo từ khóa: /tin giá vàng</i>"
