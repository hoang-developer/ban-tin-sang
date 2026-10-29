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

## Lệnh trên Telegram

Gõ trong chat với bot (hoặc bấm nút **Menu** cạnh ô nhập), bot trả lời sau vài giây:

- `/stock`: phiên hiện tại. VN-Index, VN30, HNX, UPCoM kèm giá trị giao dịch và số mã tăng/giảm;
  mã VN30 tăng/giảm mạnh nhất; khối ngoại mua/bán ròng trong rổ VN30.
- `/stock FPT`: chi tiết một mã. Giá khớp, tham chiếu/trần/sàn, khối lượng, khối ngoại, dư mua/bán;
  biến động 1 tuần, 1 tháng, từ đầu năm, đỉnh/đáy 52 tuần, vốn hóa; 3 tin mới nhất về mã.
  Xem nhiều mã một lúc: `/stock FPT VNM HPG` (tối đa 3).
- `/vang`: giá vàng SJC lúc này.
- `/thoitiet`: thời tiết, chất lượng không khí và mưa trong 2 tiếng tới ở Hà Nội.
- `/bantin`: gửi lại bản tin sáng ngay (khoảng 10 giây).

Bot chỉ trả lời chat có `TELEGRAM_CHAT_ID`, người khác nhắn vào thì bỏ qua.
Phần nhận lệnh chạy trên Vercel ([api/telegram.py](api/telegram.py)), các lệnh nằm trong [lenh.py](lenh.py).
Thêm hay đổi lệnh xong thì mở lại link `/api/telegram` (bước 4 bên dưới) để menu lệnh trong Telegram cập nhật.

### Cài lên Vercel (làm một lần, miễn phí)

1. Vào [vercel.com](https://vercel.com) → **Sign Up** bằng tài khoản GitHub (gói Hobby).
2. **Add New…** → **Project** → chọn repo `ban-tin-sang` → **Import**.
   Nếu không thấy repo, bấm cấu hình GitHub App của Vercel để cho phép truy cập repo này.
3. Mở **Environment Variables**, thêm 2 biến, giá trị giống secret bên GitHub:
   `TELEGRAM_BOT_TOKEN` và `TELEGRAM_CHAT_ID`. Rồi bấm **Deploy**.
4. Deploy xong, mở bằng trình duyệt `https://<tên-dự-án>.vercel.app/api/telegram`
   (tên miền xem ở trang dự án trên Vercel). Trang báo "Đã cài webhook" là xong.
5. Vào Telegram gõ `/stock`.

Về sau mỗi lần merge vào `main`, Vercel tự cập nhật bot. Bot không trả lời thì mở lại link ở bước 4:
trang đó cài lại webhook và hiện lỗi gần nhất mà Telegram gặp.

## Xem thử trên máy

```
python bantin.py
python lenh.py /stock FPT   # thử bất kỳ lệnh nào của bot
```

Không có token Telegram thì bản tin chỉ in ra màn hình. Muốn gửi thật từ máy, tạo file `.env`:

```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

## Nguồn dữ liệu

Open-Meteo (thời tiết, AQI), SJC (dự phòng: PNJ), VNDirect (dự phòng: SSI), RSS VnExpress và Dân trí.
Lệnh /stock: VPS (chỉ số trong phiên), Vietcap (giá từng mã, dự phòng: VPS), VNDirect (lịch sử giá),
Google News (tin theo mã).
