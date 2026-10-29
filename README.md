# Bản tin sáng

Mỗi sáng 6:45 gửi vào Telegram: thời tiết và chất lượng không khí Hà Nội, giá vàng SJC,
chỉ số chứng khoán phiên trước, tin nổi bật từ VnExpress và Dân trí.

- Chạy tự động bằng GitHub Actions ([.github/workflows/bantin.yml](.github/workflows/bantin.yml)), máy tính không cần bật.
  Muốn đúng giờ thì cần cài cron-job.org một lần, xem **Lịch chạy đúng giờ** bên dưới.
- Gửi ngay: tab **Actions** → **Bản tin sáng** → **Run workflow** (làm được cả trên app GitHub điện thoại).
- Đổi nguồn báo, số tin, chỉ số chứng khoán: sửa phần "Cấu hình" đầu file [bantin.py](bantin.py).

## Lịch chạy đúng giờ

Lịch có sẵn của GitHub Actions không đáng tin: hay trễ, có hôm bỏ hẳn. Nên bản tin dùng hai lớp:

1. **Lịch chính: cron-job.org** (miễn phí) gọi GitHub đúng 6:45 mỗi sáng.
2. **Dự phòng: lịch của GitHub** lúc 6:55, 7:25, 7:55. Mốc nào tới khi hôm nay đã gửi rồi thì bỏ qua,
   nên không bị trùng. Bản tin gửi từ dự phòng có dòng ⚠️ ở cuối: khi thấy dòng đó, vào cron-job.org
   xem lỗi (thường là token hết hạn).

Mỗi lần chạy, workflow bật lại cả hai workflow để GitHub không tự tắt lịch khi repo 60 ngày không có commit.

### Cài cron-job.org (làm một lần)

1. Tạo token: GitHub → **Settings** → **Developer settings** → **Personal access tokens** →
   **Fine-grained tokens** → **Generate new token**.
   - Repository access: **Only select repositories** → `ban-tin-sang`
   - Permissions → Repository permissions → **Actions: Read and write** (không cần quyền nào khác)
   - Expiration: chọn dài nhất có thể, và đặt lịch nhắc gia hạn
2. Đăng ký [cron-job.org](https://cron-job.org) → **Create cronjob**:
   - URL: `https://api.github.com/repos/hoang-developer/ban-tin-sang/actions/workflows/bantin.yml/dispatches`
   - Lịch: mỗi ngày lúc 6:45, múi giờ `Asia/Ho_Chi_Minh`
   - Bật thông báo email khi chạy lỗi
   - Mục nâng cao (Advanced): Request method `POST`, thêm 3 header
     - `Authorization`: `Bearer <token vừa tạo>`
     - `Accept`: `application/vnd.github+json`
     - `Content-Type`: `application/json`
   - Request body: `{"ref":"main","inputs":{"tu_dong":"true"}}`
3. Bấm **Test run**: kết quả HTTP `204` và Telegram nhận bản tin là xong. Lần chạy thử này tính là
   bản tin của ngày hôm đó, nên đừng chạy thử trong khoảng 0h–6h45, kẻo sáng hôm ấy không gửi nữa.

Token này chỉ có quyền với mục Actions của repo này (chạy, dừng, bật/tắt workflow): không đọc được
secret, không sửa được code.

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
