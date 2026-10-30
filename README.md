# Bản tin sáng

Bot Telegram riêng: bản tin mỗi sáng, bản tin tối, cảnh báo tức thì và các lệnh tra cứu
(chứng khoán, vàng, thời tiết, âm lịch...). Máy tính không cần bật.

- **Bản tin sáng** 6:45: âm lịch, thời tiết và không khí Hà Nội, gợi ý trong ngày (mặc gì, phơi đồ,
  chạy bộ), giá vàng, chứng khoán phiên trước, tin nổi bật. Dưới tin có nút 🔄 Cập nhật, 📈 VN30,
  🌧️ Mưa lúc nào?.
- **Bot trên Vercel** ([api/telegram.py](api/telegram.py)) trả lời lệnh, và mỗi 15 phút chạy các việc theo
  giờ ([api/tick.py](api/tick.py), [lich.py](lich.py)): bản tin sáng, cảnh báo, bảng điện ghim, đoán
  xanh/đỏ, nhắc ngày, tin cổ tức, bản tin tối. Cài theo mục **Cài bot lên Vercel**.

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
[canhbao.yml](.github/workflows/canhbao.yml) và [bantin.yml](.github/workflows/bantin.yml) gọi dự phòng):

- **☀️ Bản tin sáng** (6:45, lỡ giờ thì gửi muộn tới 12h, mỗi ngày một lần).
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

Nếu Vercel không chạy được (chưa có kho dữ liệu, lỗi...), GitHub tự chạy `canhbao.py` và `bantin.py`
như trước, chỉ thiếu các việc mới; bản tin gửi theo cách này có dòng ⚠️ ở cuối. Lịch của GitHub rất
thất thường (có ngày gần như không chạy), nên đừng trông vào nó: cronjob 15 phút ở bước 6 là chính.

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

## Gửi bản tin ngay

Gõ `/bantin` trong Telegram, hoặc trên GitHub: tab **Actions** → **Bản tin sáng** → **Run workflow**
(làm được cả trên app GitHub điện thoại).

Trước đây bản tin sáng cần một cronjob riêng trên cron-job.org kèm token GitHub. Giờ cronjob 15 phút
của bot (bước 6 ở trên) lo luôn, token đó không cần nữa; nếu đã tạo cronjob gọi GitHub thì để hay xóa
đều được, bản tin không bị gửi trùng. Mỗi lần chạy, workflow bản tin còn bật lại cả hai workflow để
GitHub không tự tắt lịch khi repo 60 ngày không có commit.

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
