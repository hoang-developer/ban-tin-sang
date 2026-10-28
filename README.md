# Bản tin sáng

Mỗi sáng khoảng 7h gửi vào Telegram: thời tiết và chất lượng không khí Hà Nội, giá vàng SJC,
chỉ số chứng khoán phiên trước, tin nổi bật từ VnExpress và Dân trí.

- Chạy tự động bằng GitHub Actions ([.github/workflows/bantin.yml](.github/workflows/bantin.yml)), máy tính không cần bật.
- Gửi ngay: tab **Actions** → **Bản tin sáng** → **Run workflow** (làm được cả trên app GitHub điện thoại).
- Đổi nguồn báo, số tin, chỉ số chứng khoán: sửa phần "Cấu hình" đầu file [bantin.py](bantin.py).

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
