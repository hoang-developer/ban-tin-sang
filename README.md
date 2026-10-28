# Bản tin sáng

Mỗi sáng khoảng 7h gửi vào Telegram: thời tiết và chất lượng không khí Hà Nội, giá vàng SJC,
chỉ số chứng khoán phiên trước, tin nổi bật từ VnExpress và Dân trí.

- Chạy tự động bằng GitHub Actions ([.github/workflows/bantin.yml](.github/workflows/bantin.yml)), máy tính không cần bật.
- Gửi ngay: tab **Actions** → **Bản tin sáng** → **Run workflow** (làm được cả trên app GitHub điện thoại).
- Đổi nguồn báo, số tin, chỉ số chứng khoán: sửa phần "Cấu hình" đầu file [bantin.py](bantin.py).

## Cảnh báo tức thì

[canhbao.py](canhbao.py) chạy mỗi 30 phút từ 6h đến 22h và chỉ nhắn khi có chuyện:

- ☔ Sắp mưa trong 2 tiếng tới (báo xong im 3 tiếng)
- 😷 Không khí xấu đi so với đầu ngày, vượt AQI 150
- 🪙 Giá vàng SJC đổi từ 1 triệu/lượng trở lên
- 📉 VN-Index tăng/giảm mỗi 1,5% trong phiên
- 🎯 Cổ phiếu trong `WATCHLIST` chạm giá đặt trước
- 📰 Tin có từ khóa trong `KEYWORDS` (tối đa 5 tin/lần)

Ngưỡng, mã cổ phiếu, từ khóa: sửa phần "Cấu hình" đầu file. Xem thử không gửi: `python canhbao.py --xem`.

## Xem thử trên máy

```
python bantin.py
```

Không có token Telegram thì bản tin chỉ in ra màn hình. Muốn gửi thật từ máy, tạo file `.env`:

```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

## Nguồn dữ liệu

Open-Meteo (thời tiết, AQI), SJC (dự phòng: PNJ), VNDirect (dự phòng: SSI), RSS VnExpress và Dân trí.
