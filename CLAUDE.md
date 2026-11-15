# CLAUDE.md

Hai bot Telegram tiếng Việt chạy trên Vercel (Python, chỉ dùng thư viện chuẩn) với kho dữ liệu Upstash Redis:

- **Bot bản tin** (`api/telegram.py`): bản tin sáng, bản tin tối, cảnh báo tức thì, lệnh tra cứu (chứng khoán, vàng, thời tiết, âm lịch, nhận định, tin theo từ khóa).
- **Bot chi tiêu** (`api/chitieu.py`): nhắn "cà phê 35k" thì ghi và tự xếp nhóm; kèm tài sản, nợ, tiết kiệm, quỹ dự phòng, đầu tư quỹ mở, kế hoạch chia lương, trợ lý hiểu câu thường (AI Gemini, gói miễn phí).
- **Việc theo giờ** (`api/tick.py`): được gọi mỗi 15 phút (cron-job.org, GitHub Actions dự phòng) để chạy `interface/lich/jobs.py`.

Mô tả cho người dùng ở `README.md`; lịch sử và lý do refactor ở `plan.md`; luồng xử lý tin nhắn ở `docs/luong-tin-nhan.md`.

## Kiến trúc: 6 lớp, mỗi lớp một thư mục, bên trong chia theo chức năng

```
domain/          luật nghiệp vụ thuần: tính toán, đọc/hiểu chữ, hằng số. Không gọi mạng, kho, không in.
infrastructure/  nói chuyện với bên ngoài: kho Redis, Telegram, AI, Open-Meteo, VNDirect/VCI/VPS, Fmarket, đồng hồ.
repositories/    đọc/ghi kho theo từng loại dữ liệu; mọi khóa Redis nằm ở repositories/keys.py.
services/        ghép dữ liệu + luật thành việc: lấy số liệu, ghi sổ, gọi AI. Trả dữ liệu, không dựng chữ.
presentation/    dựng tin nhắn HTML và nút bấm từ dữ liệu. Không đọc kho, không gọi mạng.
interface/       lệnh, nút bấm, việc theo giờ: ghép các lớp trên. Điểm vào của mọi luồng.
api/             3 hàm điều phối của Vercel (telegram, chitieu, tick); chỉ gọi interface.
```

Luật phụ thuộc (kiểm bằng `tests/test_kientruc.py`, test đỏ nếu vi phạm):

| Lớp | Được import |
|---|---|
| domain | domain |
| infrastructure | infrastructure |
| repositories | domain, infrastructure, repositories |
| services | domain, repositories, infrastructure, services |
| presentation | domain, presentation |
| interface | mọi lớp |

Thư mục gốc không còn file `.py` nào (`ROOT_PY_MAX = 0`, `LEGACY_IMPORTS` rỗng). Thêm code mới ở gốc hoặc import ngược lớp đều làm test đỏ.

### Các chức năng (mỗi chức năng có mặt ở nhiều lớp với cùng tên thư mục)

| Nhóm | Chức năng |
|---|---|
| Bot chi tiêu | `chitieu` (sổ, nhóm, báo cáo, ngân sách, lệnh, định tuyến), `phantich` (dự báo, hỏi đáp, biểu đồ, nhận xét), `taisan`, `no`, `tietkiem`, `duphong`, `dautu` (quỹ mở), `kehoach` (chia lương), `doichieu`, `docanh` (đọc ảnh hóa đơn), `troly` (hiểu câu thường), `menu`, `thongbao` (tin sáng/tối gộp), `danhgia` (công cụ đo bot hiểu câu) |
| Bot bản tin | `bantin` (thời tiết, vàng, chỉ số, tin), `canhbao` (mưa, không khí, vàng, VN-Index, mã chạm giá, từ khóa), `chungkhoan` (`/stock`), `tintuc` (`/tin`), `thoitiet`, `nhandinh` (ngành, khuyến nghị CTCK, AI tổng hợp), `lenh` (bảng lệnh), `lich` (việc theo giờ), `amlich` (âm lịch, thuần) |

Mỗi chức năng thường có: `domain/<cn>/` (luật), `services/<cn>/` (dữ liệu), `presentation/<cn>/view.py` (chữ), `interface/<cn>/` (lệnh/nút), thêm `repositories/<cn>/` nếu có dữ liệu lưu.

### Điểm vào quan trọng

- `interface/chitieu/bot.py`: `answer`, `respond`, `on_button`, bảng `COMMANDS`; thứ tự xử lý một tin: lệnh, khoản chi/thu thường, rồi `interface/troly/assistant.py` (AI hiểu câu).
- `interface/chitieu/context.py`: hàm tiện dụng gắn với cấu hình nhóm của người dùng (`today`, `name`, `classify`, `report`, `token`, `owner_chats`…).
- `interface/chitieu/features.py`: hàm nạp muộn (`taisan()`, `dautu()`, `troly()`…) để các chức năng gọi lẫn nhau mà không vòng import.
- `interface/lenh/bot.py`: `answer`, `on_button`, `MENU` của bot bản tin. `interface/lich/jobs.py`: danh sách `JOBS` và `run(now)`.
- `interface/bantin/bulletin.py`, `interface/canhbao/runner.py`, `interface/chungkhoan/stock.py`… có thể chạy tay: `python -m interface.<cn>.<module>`.
- `interface/common.py`: hàm dùng chung của lớp giao diện (`needs_store`, `keyboard_rows`, `from_menu`…).
- `infrastructure/kho.py`: Redis qua REST; `kho.ready()` false thì tính năng cần kho báo "cần kho dữ liệu". `infrastructure/ai.py`: Gemini trước, OpenRouter dự phòng. `infrastructure/clock.py`: `now_vn()` và `VN_TZ` (một chỗ lấy giờ).

## Quy ước làm việc

- **Hành vi là hợp đồng**: tin nhắn, nút, cấu trúc Redis (khóa và JSON) không đổi khi tái cấu trúc. Khóa Redis chỉ khai báo ở `repositories/keys.py`; test `tests/test_keys.py` giữ chuỗi khóa nguyên vẹn.
- **Luật nhận tiền/ngày/nhóm là code, AI chỉ hiểu câu**: số liệu luôn do code tính; AI lỗi hay bận thì bot hỏi lại bằng nút, không tự đoán. Chỉ dùng Gemini gói miễn phí; không tự chạy bộ đo 113 câu của trợ lý khi không động tới định tuyến (hạn mức 80 lượt/ngày).
- **Gọi giờ qua `infrastructure/clock.now_vn()`** (hoặc `interface.chitieu.context.today()`), không gọi `datetime.now` trong luồng chính, để test đổi đồng hồ được.
- **Gọi mạng qua `infrastructure/*`**; trong code gọi theo kiểu `module.hàm(...)` (không `from module import hàm`) ở chỗ test cần thay thế, vì test thay bằng cách gán thuộc tính mô-đun.
- Văn bản cho người dùng viết tiếng Việt có dấu; commit và PR cũng tiếng Việt. Không đưa tên model AI vào commit/PR. Không commit file sao kê ngân hàng hay dữ liệu cá nhân.
- Dùng đúng tên biến: biến cục bộ trùng tên hàm vừa import sẽ che hàm đó (đã gây lỗi hai lần khi chuyển code); chạy test sau mỗi lần đổi import.

## Kiểm thử

```bash
python -m unittest discover -s tests -t . -v
```

- CI `kiemthu` (`.github/workflows/kiemthu.yml`, Python 3.12) chạy lệnh trên cho mỗi push vào `main` và mỗi pull request. Hiện 467 test, chạy trong vài giây; không gọi Telegram, Redis, Fmarket hay AI thật.
- `tests/harness.py` dựng bot chạy trong bộ nhớ: kho Redis giả (`h.STORE`), AI giả (`h.AI.replies`, `h.AI.photo`), đồng hồ (`h.CLOCK`, `h.at(...)`), tin gửi đi (`h.SENT`); gọi bot bằng `h.say(text)`, `h.press(data)`, `h.send_photo()`. Test nào thay `ai_client.chat` hay hàm mạng phải trả lại bằng `addCleanup`, nếu không các test khác vỡ.
- `tests/test_kientruc.py` giữ luật 6 lớp; `tests/test_keys.py` cấm viết khóa Redis ngoài `repositories/keys.py`.
- Khi tách/chuyển code: chạy bản mới và bản `main` cũ trên cùng đầu vào giả rồi so kết quả, lỗi in ra và các lệnh ghi Redis (phương pháp dùng suốt đợt refactor, chi tiết ở `plan.md`).

## Triển khai

- Vercel: `vercel.json` (vùng `sin1`; `api/telegram.py` 60 s, `api/tick.py` 120 s, `api/chitieu.py` 60 s). Đẩy lên `main` là deploy.
- Biến môi trường: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `CHITIEU_BOT_TOKEN`, `CHITIEU_CHAT_ID`, `GEMINI_API_KEY`, `AI_API_KEY`/`AI_API_URL` (OpenRouter dự phòng), cùng biến kết nối Upstash do Vercel Marketplace thêm (`KV_REST_API_URL`…).
- GitHub Actions dự phòng khi Vercel không chạy được: `.github/workflows/bantin.yml` (`python3 -m interface.bantin.bulletin`) và `canhbao.yml` (`python3 -m interface.canhbao.runner`).
- Kiểm tra sau deploy: mở `https://ban-tin-sang.vercel.app/api/telegram` và `/api/chitieu`: phải thấy "Kho dữ liệu: đã kết nối", "Tin nhắn đang chờ: 0" và "Lịch chạy: lần gần nhất HH:MM" tiến thêm mỗi 15 phút. Lần chạy đầu sau deploy mới là lần thử thật của code mới.
- Quy trình đã dùng: nhánh `claude/refactor-repository`, mỗi PR một bước, đợi CI `kiemthu` xanh, squash merge, đợi deploy, xem trạng thái hai trang trên; sau mỗi lần squash merge, đặt lại nhánh từ `main` rồi đẩy với `--force-with-lease`.

## Còn lại và điểm cần biết

- `interface/{menu,lich,lenh,troly,thongbao,danhgia}` vẫn lẫn phần chữ và danh sách việc (`JOBS` của trợ lý phụ thuộc hàm lấy danh sách từ chức năng khác); một số `services` còn chứa câu chữ cho người dùng. Đã ghi ở mục dọn dẹp của `plan.md`.
- Hàm nạp muộn trong `interface/chitieu/features.py` chỉ bỏ được sau khi các `interface` hết gọi lẫn nhau.
- Lời nhắn của lệnh `/tukhoa` cho từ khóa cài sẵn vẫn nhắc "canhbao.py" (file đã xóa); giữ nguyên chữ để không đổi hành vi, cần sửa riêng.
- Gợi ý chạy bộ (`domain/bantin/weather.tips`) chọn lý do chặn theo thứ tự băm của `set`, nên khi hòa có thể đổi giữa các lần chạy (lỗi có từ trước).
- Lỗi cũ chưa sửa: bộ đọc nợ nhận "ngày 5," có dấu phẩy sai (plan.md mục 4c).

## Số liệu hiện tại

Khoảng 16.000 dòng code và 6.000 dòng test: domain 3.185, repositories 675, infrastructure 701, services 3.488, presentation 2.089, interface 5.829, api 286.
