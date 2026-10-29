# Bản tin sáng

Bot Telegram riêng: bản tin mỗi sáng, bản tin tối, cảnh báo tức thì và các lệnh tra cứu
(chứng khoán, vàng, thời tiết, âm lịch...). Máy tính không cần bật.

- **Bản tin sáng** 6:45: âm lịch, thời tiết và không khí Hà Nội, gợi ý trong ngày (mặc gì, phơi đồ,
  chạy bộ), giá vàng, chứng khoán phiên trước, tin nổi bật. Dưới tin có nút 🔄 Cập nhật, 📈 VN30,
  🌧️ Mưa lúc nào?. Chạy bằng GitHub Actions ([bantin.yml](.github/workflows/bantin.yml)), muốn đúng giờ
  thì cài cron-job.org (mục **Lịch bản tin sáng**).
- **Bot trên Vercel** ([api/telegram.py](api/telegram.py)) trả lời lệnh, và mỗi 15 phút chạy các việc theo
  giờ ([api/tick.py](api/tick.py), [lich.py](lich.py)): cảnh báo, bảng điện ghim, đoán xanh/đỏ, nhắc ngày,
  tin cổ tức, bản tin tối. Cài theo mục **Cài bot lên Vercel**.

## Lệnh trên Telegram

Gõ trong chat với bot hoặc bấm nút **Menu** cạnh ô nhập ([lenh.py](lenh.py)):

| Lệnh | Làm gì |
|---|---|
| `/stock` | Phiên hiện tại: VN-Index, VN30, HNX, UPCoM, mã VN30 tăng/giảm mạnh, khối ngoại |
| `/stock FPT` | Chi tiết mã (tối đa 3 mã một lần). Nút ⭐ Theo dõi, 📰 Thêm tin, 🔁 Làm mới |
| `/theodoi` | Mã đang theo dõi. `/theodoi FPT` thêm mã, `/theodoi FPT 50 60` báo khi giá ≤ 50.000 hoặc ≥ 60.000 |
| `/vang` | Giá vàng SJC lúc này |
| `/vivang` | Ví vàng: `/vivang nhan 2 chi 136` (giá mua triệu/lượng, có thể bỏ), `/vivang sjc 1 luong`, `/vivang xoa` |
| `/neu` | Nếu ngày xưa mua: `/neu FPT 10tr 1nam`, `/neu vnindex 50tr 6thang`, `/neu vang 100tr 3thang` |
| `/thoitiet` | Thời tiết, mưa 2 tiếng tới, gợi ý trong ngày. `/thoitiet Đà Nẵng` cho nơi khác |
| 📍 gửi vị trí | Thời tiết đúng chỗ bạn đang đứng (📎 → Vị trí) |
| `/nho` | Ngày cần nhớ: `/nho giỗ ông 12/3 âm`, `/nho sinh nhật vợ 20/11`. Nhắc trước 3 ngày và đúng ngày |
| `/amlich` | Âm lịch hôm nay, mùng 1 và rằm tới. `/amlich 15/8` đổi ngày âm sang dương |
| `/doan` | Thành tích đoán VN-Index xanh/đỏ |
| `/bantin` | Gửi lại bản tin sáng ngay (khoảng 10 giây) |
| `/caidat` | Tình trạng kho dữ liệu, lịch chạy và địa chỉ để cài cron-job.org |

Bot chỉ trả lời chat có `TELEGRAM_CHAT_ID`, người khác nhắn vào thì bỏ qua.
Các lệnh `/theodoi`, `/nho`, `/vivang`, `/doan` và nút ⭐ cần **kho dữ liệu** (bước 4 bên dưới).

## Việc bot tự làm theo giờ

Chạy mỗi lần có lời gọi `/api/tick` (cron-job.org mỗi 15 phút; lịch GitHub của
[canhbao.yml](.github/workflows/canhbao.yml) gọi dự phòng):

- **Cảnh báo** (6h–22h, [canhbao.py](canhbao.py)), chỉ nhắn khi có chuyện:
  ☔ sắp mưa trong 2 tiếng tới · 😷 không khí xấu đi, vượt AQI 150 · 🪙 vàng SJC đổi từ 1 triệu/lượng
  (kèm giá trị ví vàng) · 📉 VN-Index tăng/giảm mỗi 1,5% · 🎯 mã chạm giá đặt bằng `/theodoi` hoặc
  `WATCHLIST` · 📰 tin có từ khóa trong `KEYWORDS`. Ngưỡng, từ khóa: phần "Cấu hình" đầu file.
- **📌 Bảng điện** (ngày giao dịch, 9h–15h): một tin ghim đầu chat với VN-Index, VN30, HNX, UPCoM,
  các mã đang theo dõi và giá vàng, tự sửa lại mỗi 15 phút.
- **🎯 Đoán xanh/đỏ**: 8:15 bot hỏi VN-Index hôm nay xanh hay đỏ (nhận đoán tới 9:15), 15h chấm điểm.
- **🔔 Nhắc ngày** (7h): ngày trong `/nho` còn 3 ngày hoặc là hôm nay.
- **💰 Tin cổ tức** (7:30): tin cổ tức, chốt quyền của các mã đang theo dõi (Google News).
- **🌙 Bản tin tối** (21h): thời tiết và gợi ý ngày mai, chứng khoán hôm nay, giá vàng so với hôm
  qua, ví vàng, ngày cần nhớ ngày mai, kết quả đoán. Bot cũng ghi giá vàng mỗi tối để `/neu vang` dùng.

Nếu Vercel chưa sẵn sàng (chưa có kho dữ liệu...), GitHub tự chạy `canhbao.py` như trước, chỉ thiếu
các việc mới.

## Cài bot lên Vercel (làm một lần, miễn phí)

1. Vào [vercel.com](https://vercel.com) → **Sign Up** bằng tài khoản GitHub (gói Hobby).
2. **Add New…** → **Project** → chọn repo `ban-tin-sang` → **Import**.
   Nếu không thấy repo, bấm cấu hình GitHub App của Vercel để cho phép truy cập repo này.
3. Mở **Environment Variables**, thêm 2 biến, giá trị giống secret bên GitHub:
   `TELEGRAM_BOT_TOKEN` và `TELEGRAM_CHAT_ID`. Rồi bấm **Deploy**.
4. **Kho dữ liệu**: trong dự án trên Vercel, mở tab **Storage** → **Create Database** (hoặc
   **Browse Marketplace**) → chọn **Upstash** (Redis) → gói **Free**, vùng gần nhất (Singapore) →
   **Connect** vào dự án `ban-tin-sang`. Vercel tự thêm biến môi trường, rồi **Redeploy** (tab
   **Deployments** → **⋯** → **Redeploy**). Chọn đúng Upstash: bot gọi Redis qua REST của Upstash.
5. Mở bằng trình duyệt `https://<tên-dự-án>.vercel.app/api/telegram`. Trang báo "Đã cài webhook" và
   "Kho dữ liệu: đã kết nối" là xong.
6. **Lịch chạy**: trong Telegram gõ `/caidat`, bot gửi địa chỉ `/api/tick?key=...`. Trên
   [cron-job.org](https://cron-job.org) tạo cronjob gọi địa chỉ đó (GET) **mỗi 15 phút**, bật email báo
   lỗi. Địa chỉ có khóa bí mật suy ra từ token bot: đừng chia sẻ; đổi token thì khóa đổi theo.

Về sau mỗi lần merge vào `main`, Vercel tự cập nhật bot. Thêm hay đổi lệnh thì mở lại link ở bước 5
để menu lệnh cập nhật. Bot không trả lời thì cũng mở link đó: trang cài lại webhook và hiện lỗi gần
nhất mà Telegram gặp.

## Lịch bản tin sáng

Lịch có sẵn của GitHub Actions không đáng tin: hay trễ, có hôm bỏ hẳn. Nên bản tin dùng hai lớp:

1. **Lịch chính: cron-job.org** (miễn phí) gọi GitHub đúng 6:45 mỗi sáng.
2. **Dự phòng: lịch của GitHub** lúc 6:55, 7:25, 7:55. Mốc nào tới khi hôm nay đã gửi rồi thì bỏ qua,
   nên không bị trùng. Bản tin gửi từ dự phòng có dòng ⚠️ ở cuối: khi thấy dòng đó, vào cron-job.org
   xem lỗi (thường là token hết hạn).

Mỗi lần chạy, workflow bật lại cả hai workflow để GitHub không tự tắt lịch khi repo 60 ngày không có commit.

### Cài cron-job.org cho bản tin sáng (làm một lần)

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

## Xem thử trên máy

```
python bantin.py                    # bản tin sáng
python lenh.py /neu FPT 10tr 1nam   # thử bất kỳ lệnh nào của bot
python thoitiet.py Đà Nẵng
python amlich.py 17/2/2026
python canhbao.py --xem             # cảnh báo, không gửi
```

Không có token Telegram thì bản tin chỉ in ra màn hình. Muốn gửi thật từ máy, tạo file `.env`:

```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

## Nguồn dữ liệu

Open-Meteo (thời tiết, AQI, tìm địa danh), SJC (dự phòng: PNJ), VNDirect (dự phòng: SSI), RSS VnExpress
và Dân trí. Chứng khoán trong phiên: VPS (chỉ số), Vietcap (giá từng mã, dự phòng: VPS), Google News
(tin theo mã, tin cổ tức). Âm lịch tính theo thuật toán của Hồ Ngọc Đức ([amlich.py](amlich.py)).
Lịch sử giá vàng không có nguồn công khai: bot tự ghi giá SJC mỗi tối.
