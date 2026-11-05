# Bản tin sáng

Bot Telegram riêng: bản tin mỗi sáng, bản tin tối, cảnh báo tức thì và các lệnh tra cứu
(chứng khoán, vàng, thời tiết, âm lịch...). Máy tính không cần bật.

- **Bản tin sáng** 6:45: âm lịch, thời tiết và không khí Hà Nội, gợi ý trong ngày (mặc gì, phơi đồ,
  chạy bộ), giá vàng, chứng khoán phiên trước, tin nổi bật. Dưới tin có nút 🔄 Cập nhật, 📈 VN30,
  🌧️ Mưa lúc nào?.
- **Bot trên Vercel** ([api/telegram.py](api/telegram.py)) trả lời lệnh, và mỗi 15 phút chạy các việc theo
  giờ ([api/tick.py](api/tick.py), [lich.py](lich.py)): bản tin sáng, cảnh báo, bảng điện ghim, đoán
  xanh/đỏ, nhắc ngày, tin cổ tức, bản tin tối. Cài theo mục **Cài bot lên Vercel**.
- **Bot chi tiêu** ([api/chitieu.py](api/chitieu.py), [sochitieu.py](sochitieu.py)): một bot Telegram thứ hai,
  nhắn "cà phê 35k" là bot ghi lại và tự xếp nhóm. Xem mục **Bot chi tiêu**.

## Lệnh trên Telegram

Gõ trong chat với bot hoặc bấm nút **Menu** cạnh ô nhập ([lenh.py](lenh.py)):

| Lệnh | Làm gì |
|---|---|
| `/stock` | Phiên hiện tại: VN-Index, VN30, HNX, UPCoM, mã VN30 tăng/giảm mạnh, khối ngoại |
| `/stock FPT` | Chi tiết mã (tối đa 3 mã một lần). Nút ⭐ Theo dõi, 📰 Thêm tin, 🔁 Làm mới |
| `/nhandinh` | Nhận định trong phiên: AI tổng hợp ngành hot, mã đáng chú ý (kèm khuyến nghị của CTCK nào, giá mục tiêu), tin, rủi ro. Nút 🔥 Ngành, 🎯 Khuyến nghị, 📰 Tin. `/nhandinh tat` / `bat`: tắt/bật tự gửi |
| `/nganh` | Ngành trên HOSE: % (theo vốn hóa), giá trị giao dịch, khối ngoại ròng, mã dẫn dắt; ngành hút tiền nhất |
| `/khuyennghi` | Khuyến nghị của các CTCK 30 ngày qua, gọn: số CTCK khuyến nghị, giá mục tiêu TB, còn tăng bao nhiêu. `/khuyennghi FPT`: từng CTCK với một mã (180 ngày) |
| `/theodoi` | Mã đang theo dõi. `/theodoi FPT` thêm mã, `/theodoi FPT 50 60` báo khi giá ≤ 50.000 hoặc ≥ 60.000 |
| `/tin` | Tin nổi bật. `/tin giá vàng` tìm tin mới nhất theo từ khóa (7 ngày qua; thêm `24h`, `3ngay` để giới hạn). Nút 🔔 báo khi có tin mới |
| `/tukhoa` | Từ khóa báo tin mới: `/tukhoa giá xăng` thêm, bấm ❌ để bỏ |
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

### Nhận định trong phiên

Ngày giao dịch, bot tự gửi lúc **10h15** và **13h45** (tắt: `/nhandinh tat`). Code ở [nhandinh.py](nhandinh.py).

- **Dữ liệu** (bot tự tính): ngành theo phân ngành ICB cấp 3 của VNDirect, % thay đổi theo vốn hóa của ~430 mã
  HOSE (giá Vietcap), giá trị giao dịch, khối ngoại ròng; mã giao dịch nhiều nhất, tăng/giảm mạnh, khối ngoại mua
  bán nhiều nhất; **khuyến nghị của các công ty chứng khoán** 30 ngày qua (VNDirect tổng hợp: HSC, VNDirect, UBS,
  Yuanta, Vietcap, MBS, ACBS…, ~100 khuyến nghị/tháng) kèm giá mục tiêu trung bình và còn tăng bao nhiêu so với giá
  hiện tại; tin 18 giờ qua từ CafeF, Vietstock (cổ phiếu, nhận định thị trường, phân tích cơ bản), VnExpress.
- **Tin gửi đi ngắn gọn** (khoảng 7 dòng): dòng đầu VN-Index, thanh khoản, khối ngoại ròng (bot tính); rồi AI
  (dùng chung `GEMINI_API_KEY`, OpenRouter dự phòng) viết tối đa 5 dòng: 🔥 2–3 ngành hot (ưu tiên vừa tăng vừa
  hút tiền), 🎯 2–3 mã đáng chú ý (% hôm nay, CTCK nào khuyến nghị, mục tiêu, còn tăng), ⚠️ 1 rủi ro. Chi tiết
  xem bằng nút 🔥 Ngành, 🎯 Khuyến nghị, 📰 Tin. AI được dặn chỉ dùng dữ liệu đưa vào, không tự khuyến nghị mua
  bán; dòng nào nhắc mã không có trong dữ liệu bị bỏ. AI bận/hết lượt thì bot gửi bản ngắn chỉ có số liệu.
- Lưu ý: khuyến nghị của CTCK hầu hết là MUA và giá mục tiêu thường lạc quan; AI có thể tóm tắt sai. **Thông tin
  tổng hợp để tham khảo, không phải lời khuyên đầu tư.** Ngày nghỉ lễ (chưa có giao dịch) bot không gửi.
- Thử ngày 05/11/2026 trong phiên sáng: cả lấy dữ liệu và AI viết mất khoảng 7–16 giây.

## Việc bot tự làm theo giờ

Chạy mỗi lần có lời gọi `/api/tick` (cron-job.org mỗi 15 phút; lịch GitHub của
[canhbao.yml](.github/workflows/canhbao.yml) và [bantin.yml](.github/workflows/bantin.yml) gọi dự phòng):

- **☀️ Bản tin sáng** (6:45, lỡ giờ thì gửi muộn tới 12h, mỗi ngày một lần).
- **Cảnh báo** (6h–22h, [canhbao.py](canhbao.py)), chỉ nhắn khi có chuyện:
  ☔ sắp mưa trong 2 tiếng tới · 😷 không khí xấu đi, vượt AQI 150 · 🪙 vàng SJC đổi từ 1 triệu/lượng
  (kèm giá trị ví vàng) · 📉 VN-Index tăng/giảm mỗi 1,5% · 🎯 mã chạm giá đặt bằng `/theodoi` hoặc
  `WATCHLIST` · 📰 tin có từ khóa trong `KEYWORDS` hoặc thêm bằng `/tukhoa` (tối đa 5 tin/lần).
  Ngưỡng, từ khóa cài sẵn: phần "Cấu hình" đầu file.
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

## Bot chi tiêu

Bot Telegram riêng để ghi chi tiêu. Nhắn số tiền kèm nội dung, bot tự hiểu số tiền và xếp nhóm:

- `cà phê 35k` · `đổ xăng 80000` · `tiền nhà 5tr` · `tien dien 1tr2` (gõ không dấu cũng được)
- `hôm qua ăn tối 250k` · `02/11 cắt tóc 100k` · `+ lương 20tr` (dấu `+` là khoản thu)
- `đóng họ 1tr #tiết kiệm`: tự chọn nhóm bằng dấu `#` (tên nhóm, gõ tắt hay không dấu đều được); bot nhớ
  cho lần sau
- Nhiều khoản một lúc: mỗi khoản một dòng.
- 📷 **Gửi ảnh** hóa đơn hoặc màn hình chuyển khoản: bot đọc rồi ghi (xem mục Ghi bằng ảnh).

Số tiền hiểu được: `35k`, `35.000đ`, `35 nghìn`, `1tr2` (1.200.000đ), `2tr500`, `1,5tr`, `1k5`; số trơn
dưới 1.000 hiểu là nghìn (`cà phê 35` là 35.000đ). Nhóm có sẵn: Ăn uống, Đi chợ, Đi lại, Nhà cửa và hóa
đơn, Mua sắm, Sức khỏe, Giải trí và du lịch, Học tập, Hiếu hỷ và quà, Gia đình và con cái, Khác, Thu nhập.
Xếp sai thì bấm **✏️ Đổi nhóm** dưới tin: bot đổi và nhớ, lần sau gặp nội dung đó tự xếp đúng.
Từ khóa có sẵn của từng nhóm: phần "Nhóm chi tiêu" đầu [sochitieu.py](sochitieu.py).

### Tự xếp nhóm, ít khoản rơi vào Khác

Bot xếp mỗi khoản theo thứ tự: nhóm bạn đã tự chọn cho nội dung đó → từ khóa (bạn thêm, rồi có sẵn) →
AI (nếu bật, khoản có dấu 🤖) → nếu vẫn chưa rõ thì **hỏi bạn ngay** bằng nút chọn nhóm dưới tin (bấm
"📦 Để ở Khác" nếu đúng là khoản lặt vặt). Chọn một lần là bot nhớ, các khoản cùng nội dung đang ở Khác
cũng được xếp luôn; số và ngày tháng trong ghi chú được bỏ qua khi nhớ ("tiền rác tháng 11" nhớ thành
"tiền rác", tháng sau vẫn nhận ra).

| Lệnh | Làm gì |
|---|---|
| `/nhom them 🏦 Trả nợ: trả nợ, trả góp, vay` | Tạo nhóm mới kèm từ khóa (biểu tượng không bắt buộc). Khoản đang ở Khác khớp từ khóa được xếp lại ngay |
| `/nhom tukhoa Ăn uống: bún chả, bánh tráng` | Thêm từ khóa cho nhóm bất kỳ; từ khóa bạn thêm thắng từ khóa có sẵn |
| `/nhom doiten Đi lại: 🚗 Xe cộ` | Đổi tên nhóm |
| `/nhom xoa Học tập` | Ẩn nhóm không dùng (khoản cũ giữ nguyên); `/nhom them Học tập` để dùng lại |
| `/chuaxep` | Các khoản còn ở Khác: xếp lại theo những gì bot đã học, hỏi lại AI, còn lại bấm chọn từng khoản |

Báo cáo nhắc số khoản chưa rõ nhóm. `/nhom` cho xem các nhóm, nhóm đã ẩn, số cụm bot đã học và AI đã
đoán bao nhiêu khoản, bạn phải sửa bao nhiêu.

| Lệnh | Làm gì |
|---|---|
| `/baocao` | Báo cáo kèm nút chọn kỳ: hôm nay, tuần này, tháng này, tháng trước |
| `/homnay`, `/tuan`, `/thang` | Báo cáo nhanh; `/thang 10` cho tháng 10. Có tổng chi, từng nhóm, so với kỳ trước, thu, khoản lớn nhất |
| `/ngansach` | Ngân sách tháng: `/ngansach ăn uống 3tr`, `/ngansach tổng 15tr`, bỏ: `/ngansach ăn uống 0`. Ghi khoản mới thì bot báo ⚠️ khi quá 80%, 🚨 khi vượt |
| `/lichsu` | 10 khoản gần nhất, bấm ❌ để xóa |
| `/xoa` | Xóa khoản vừa ghi |
| `/xuat` | File CSV mở bằng Excel; `/xuat 10` cho tháng 10 |
| `/nhom` | Các nhóm, từ khóa; tự tạo nhóm, thêm từ khóa (xem dưới) |
| `/chuaxep` | Xếp nhóm các khoản đang ở Khác |
| `/dubao` | Dự báo cả tháng, mỗi ngày còn lại / hôm nay còn được tiêu bao nhiêu (xem dưới) |
| `/hoi` | Hỏi bằng câu thường, hoặc gõ thẳng câu hỏi: `tháng này cà phê hết bao nhiêu?` |
| `/bieudo` | Biểu đồ tròn theo nhóm và cột theo ngày; `/bieudo 10` cho tháng 10 |
| `/nhanxet` | Số liệu đáng chú ý của tháng + nhận xét và gợi ý tiết kiệm của AI; `/nhanxet 10` |
| `/taisan` | Tài sản ròng: tiền, tiết kiệm, cổ phiếu, quỹ, vàng, tiền số, ngoại tệ, nợ (xem dưới) |
| `/suckhoe` | Khám sức khỏe tài chính cá nhân |
| `/luong` | Nhắc ngày nhận lương: `/luong 10 25tr` |

Tối Chủ nhật 20h bot gửi tổng kết tuần, ngày 1 hằng tháng gửi tổng kết tháng trước kèm biểu đồ và nhận
xét, 21h hằng ngày báo nếu có gì cần để ý, 9h nhắc lương và sổ tiết kiệm sắp đáo hạn, 18h lưu tài sản ròng
(qua lịch chạy `/api/tick` sẵn có).

### Hiểu mình tiêu thế nào

Số liệu luôn do bot tự tính từ sổ; AI (nếu bật) chỉ hiểu câu hỏi và viết nhận xét. Code ở
[phantich.py](phantich.py).

- **Dự báo** (`/dubao`, nút 🔮 dưới báo cáo): đã chi + nhịp tiêu hằng ngày (trung bình các khoản dưới 1tr
  trong 28 ngày qua) × số ngày còn lại + khoản lớn tháng trước có mà tháng này chưa thấy (tiền nhà, học
  phí...). Có ngân sách tổng (`/ngansach tổng 15tr`) thì bot tính mỗi ngày còn lại được tiêu bao nhiêu,
  và mỗi lần ghi khoản chi đều báo "💡 Hôm nay còn được tiêu …". Nhóm có ngân sách: dự báo và ngày có thể
  vượt.
- **Báo bất thường**: ghi một khoản từ 200k mà gấp 3 lần mức thường của nhóm (trung vị 90 ngày, cần từ 5
  khoản) thì bot nói ngay. 21h hằng ngày bot xem: nhóm nào 7 ngày qua tiêu gấp 1,6 lần mức thường (và
  nhiều hơn 300k), nhóm nào đang trên đà vượt ngân sách; có thì nhắn "👀 Để ý chi tiêu", mỗi chuyện chỉ
  báo một lần mỗi tuần.
- **Hỏi bằng câu thường**: "tháng này cà phê hết bao nhiêu?", "tuần này tiêu vào đâu nhiều nhất",
  "so tháng 11 với tháng 10", "khoản lớn nhất tháng trước", "liệt kê các lần đổ xăng tháng này",
  "ngày nào tiêu nhiều nhất", "tháng này thu nhập bao nhiêu". Tin có dấu `?` hay từ để hỏi (bao nhiêu,
  so với, nhiều nhất, liệt kê, … không/chưa ở cuối) là câu hỏi, bot không ghi thành khoản. Dòng đầu câu
  trả lời cho biết bot hiểu thế nào (khoảng ngày, nhóm, chữ cần có trong ghi chú) để bạn kiểm tra. Có AI
  thì AI hiểu câu hỏi; AI bận/hết lượt thì bot tự hiểu theo cách đơn giản (thời gian, tên nhóm, từ khóa).
- **Biểu đồ** (`/bieudo`, nút 📈): vẽ bằng [QuickChart](https://quickchart.io) (miễn phí), chỉ gửi tên
  nhóm và số tiền, không gửi ghi chú.
- **Nhận xét** (`/nhanxet`, nút 💬, tự gửi ngày 1): tổng, so với kỳ trước và trung bình 3 tháng, nhóm
  tăng/giảm, khoản lặp lại nhiều (cà phê 22 lần…), khoản lớn nhất, ngày thường/cuối tuần, số ngày không
  tiêu, tỉ lệ để dành; AI viết 3 điểm đáng chú ý và 1 gợi ý tiết kiệm có con số.

### Ghi bằng ảnh

Chụp hóa đơn, hoặc chụp màn hình chuyển khoản / nhận tiền rồi gửi vào bot. AI (Gemini, cần `GEMINI_API_KEY`;
không có thì OpenRouter với model đọc ảnh `AI_VISION_MODEL`, mặc định Nemotron 3.5 Super VL) đọc tổng tiền,
ngày, nội dung; bot ghi như tin nhắn thường, vẫn có nút ✏️ đổi nhóm, ❌ xóa. Code ở [docanh.py](docanh.py).

- Lấy **tổng** hóa đơn (dòng Tổng cộng / Tong tien), không lấy tiền khách đưa, tiền thừa, số dư hay từng
  phương thức thanh toán. Nhận tiền vào tài khoản thì ghi vào Thu nhập.
- Hóa đơn có phần trả bằng voucher, Got It, điểm thưởng: bot hiện nút "➕ Ghi … vào Thu nhập" (điểm đổi từ
  chi tiêu thẻ là khoản thu; chi vẫn ghi đủ giá).
- Chữ kèm ảnh là ghi chú, có `#nhóm` thì vào nhóm đó: gửi ảnh kèm `cà phê với khách #giải trí`.
- Nhóm: cụm từ bạn đã dạy và từ khóa đi trước, không khớp mới dùng nhóm AI đoán (dấu 🤖).
- Ngày trên ảnh ở tương lai hoặc quá 1 năm thì lấy hôm nay. Gửi lại đúng ảnh cũ thì bot báo đã ghi rồi.
- Thử ngày 04/11/2026 với Gemini 3.5 Flash-Lite: đúng số tiền 7/7 ảnh, gồm hóa đơn Highlands chụp thật (tổng
  29.000đ trả bằng Got It 20.000 + MoMo 9.000), hóa đơn chụp nghiêng mờ, màn hình chuyển/nhận tiền; ảnh
  không phải hóa đơn thì bot báo không thấy. Lúc Gemini đông mỗi ảnh mất 10–20 giây (bot hiện "đang nhập…").
- Ảnh được gửi cho nhà cung cấp AI (ở gói miễn phí Google dùng để cải thiện sản phẩm), bot không lưu ảnh.
  Màn hình chuyển khoản có tên, số tài khoản: che bớt trước khi gửi nếu muốn.

### Thu nhập, tài sản, khám sức khỏe tài chính

Code ở [taisan.py](taisan.py).

- **Thu nhập**: `+ lương 25tr`, `+ thưởng 3tr`, `+ cổ tức VNM 1tr2`. Báo cáo chia thu theo loại: lương,
  thưởng, đầu tư (lãi bán cổ phiếu, cổ tức, lãi tiết kiệm), làm thêm, khác. `/luong 10 25tr`: từ ngày 10
  (tối đa 3 ngày) bot hỏi đã nhận lương chưa, bấm nút là ghi.
- **Mua bán cổ phiếu**: nhắn `mua 1000 FPT giá 95` hoặc `bán 500 FPT giá 120` (giá nghìn đồng hoặc đồng).
  Mua: cộng vào danh mục, tính giá vốn bình quân. Bán: trừ thuế thu nhập 0,1% giá trị bán (DNSE miễn phí
  giao dịch nên không có phí; công ty khác sửa `BROKER_FEE` trong taisan.py), tính lãi/lỗ so với giá vốn,
  phần **lãi** ghi vào Thu nhập (phần vốn chỉ là đổi cổ phiếu ra tiền). Có khai báo tài khoản tiền tên
  "DNSE" (`/taisan tien DNSE 50tr`) thì bot tự trừ/cộng tiền trong đó. Mua cổ phiếu không tính là khoản chi.
- **Tài sản** (`/taisan`, `/taisan huongdan` xem cách khai báo):

  | Loại | Khai báo | Giá |
  |---|---|---|
  | Tiền, tài khoản | `/taisan tien VCB 25tr` (cùng tên là cập nhật số dư) | Bạn tự cập nhật |
  | Tiết kiệm | `/taisan tietkiem VCB 100tr 4,7% 6 thang 01/08/2026` | Bot tính lãi theo ngày, nhắc trước đáo hạn 3 ngày |
  | Cổ phiếu | `/taisan cp FPT 1000 95` (số lượng, giá vốn) | Giá khớp gần nhất (Vietcap) |
  | Quỹ mở | `/taisan quy VCBF-FIF 1200 15000` | Giá chứng chỉ quỹ trên Fmarket |
  | Vàng | `/taisan vang sjc 1 luong 140` (chung ví `/vivang` của bot bản tin) | Giá cửa hàng mua vào SJC/PNJ |
  | Tiền số | `/taisan coin btc 0,05` | CoinGecko, lỗi thì Coinbase × tỷ giá |
  | Ngoại tệ | `/taisan usd 1000` | Vietcombank mua chuyển khoản |
  | Khác, nợ | `/taisan khac xe máy 30tr` · `/taisan no vay mua nhà 500tr` | Bạn tự nhập |

  Bot cho xem tài sản ròng (tài sản trừ nợ), từng loại chiếm bao nhiêu phần trăm, lãi/lỗ từng khoản, lãi/lỗ
  đã chốt trong năm, so với khoảng 30 ngày trước; nút 📊 vẽ biểu đồ cơ cấu và đường tài sản ròng theo thời
  gian (18h mỗi ngày bot lưu lại tài sản ròng). Nguồn giá lỗi thì dùng giá gần nhất và ghi chú. Sửa: khai
  báo lại cùng tên/mã; xóa: `/taisan xoa`.
- **Khám sức khỏe tài chính** (`/suckhoe`, nút 🩺): chấm điểm /100 theo quỹ dự phòng (tiền + tiết kiệm
  đủ mấy tháng chi tiêu, nên 3–6), tỉ lệ để dành (nên từ 20% thu nhập), nợ so với tài sản (nên dưới 30%),
  phân bổ (một mã quá 20% tài sản, tiền số quá 10%, một loại quá 70%), khoản đầu tư lỗ từ 20%, xu hướng
  tài sản ròng. Chi và thu lấy từ sổ 90 ngày qua. AI (nếu bật) viết 2 nhận xét và 2–3 việc nên làm có
  con số; được dặn không khuyên mua bán mã nào, không dự đoán giá. Chỉ để tham khảo.

### Cài bot chi tiêu (làm một lần)

1. Trong Telegram nhắn **@BotFather** → `/newbot` → đặt tên (ví dụ "Chi tiêu của tôi") và username
   (phải kết thúc bằng `bot`) → sao chép token.
2. Trên Vercel, dự án `ban-tin-sang` → **Settings** → **Environment Variables** → thêm
   `CHITIEU_BOT_TOKEN` = token vừa sao chép → **Save** → tab **Deployments** → **⋯** ở bản Production →
   **Redeploy**.
3. Mở `https://ban-tin-sang.vercel.app/api/chitieu` bằng trình duyệt: trang báo "Đã cài webhook".
4. Vào Telegram, mở bot mới, nhắn `cà phê 35k`.

### AI (tùy chọn, miễn phí): Google Gemini, OpenRouter dự phòng

AI giúp bot ở các việc: xếp nhóm khoản lạ (dấu 🤖), hiểu câu hỏi, viết nhận xét tháng và khám sức khỏe tài
chính. Mọi con số vẫn do bot tự tính. Khoản nào từ khóa không nhận ra thì bot hỏi AI; AI được biết cả nhóm
bạn tự tạo (kèm từ khóa) và những khoản bạn đã tự xếp để đoán theo thói quen của bạn; không chắc thì AI để
Khác và bot hỏi bạn. Bot nhớ câu trả lời, cùng nội dung không hỏi lại. AI lỗi, bận hay hết lượt thì bot vẫn
chạy: khoản lạ bot hỏi bạn, câu hỏi bot tự hiểu cách đơn giản, nhận xét chỉ có số liệu.

**Google Gemini (dùng trước).** Thử ngày 04/11/2026: `gemini-3.5-flash-lite` xếp đúng 13/13 khoản lạ trong
khoảng 1 giây, hiểu đúng 5/5 câu hỏi mẫu (dưới 1 giây mỗi câu), đọc đúng số tiền 7/7 ảnh hóa đơn/chuyển
khoản; `gemini-3.5-flash` cũng 13/13 nhưng chậm hơn. Bot thử Flash-Lite trước, lỗi/bận/hết lượt thì Flash,
rồi tới OpenRouter. Gói miễn phí không cần thẻ; giới hạn tính theo dự án và theo từng model (Flash: 5 lượt
mỗi phút), số lượt mỗi ngày xem ở [aistudio.google.com/rate-limit](https://aistudio.google.com/rate-limit),
tính lại lúc 0h giờ Mỹ (khoảng 15h chiều Việt Nam). Ở gói miễn phí Google dùng nội dung gửi lên để cải thiện
sản phẩm.

**OpenRouter (dự phòng).** Model miễn phí `nvidia/nemotron-3-ultra-550b-a55b:free`, bận thì
`dots-studio/dots-3-note-preview:free` (thử 13 khoản lạ: mỗi model đúng 12, mất 10–20 giây). Cả tài khoản
chỉ **50 lượt model miễn phí mỗi ngày** (nạp tiền một lần thì lên 1.000 lượt), tính lại lúc 7h sáng.

Bật bằng biến môi trường trên Vercel (rồi Redeploy), có một trong hai là được:
- `GEMINI_API_KEY`: khóa của Google AI Studio (aistudio.google.com → Get API key → Create API key)
- `GEMINI_MODEL` (không bắt buộc): đổi model Gemini, nhiều model cách nhau dấu phẩy, thử lần lượt
- `AI_API_KEY`: khóa OpenRouter (openrouter.ai → Keys), làm dự phòng
- `AI_MODEL`, `AI_API_URL` (không bắt buộc): đổi model OpenRouter, hoặc dùng nhà cung cấp khác có API
  dạng OpenAI (`/v1/chat/completions`). Model miễn phí thay đổi theo thời gian; model mặc định bị gỡ thì
  đặt biến sang model khác

Mở `https://ban-tin-sang.vercel.app/api/chitieu`: dòng "AI xếp nhóm" cho biết bot sẽ thử những model nào,
theo thứ tự, và số lượt OpenRouter đã dùng hôm nay (không tốn lượt). Thêm `?thu=1` vào cuối địa chỉ để thử
gọi AI thật (tốn 1 lượt): trang báo model nào trả lời, mất bao lâu, hay lỗi gì.

Dữ liệu nằm trong kho Upstash Redis của dự án (khóa `chitieu:...`). Bot chỉ trả lời chat có
`TELEGRAM_CHAT_ID`; muốn dùng chung với người nhà thì thêm biến `CHITIEU_CHAT_ID` = các chat ID cách nhau
dấu phẩy (người đó nhắn bot sẽ được báo chat ID của mình), mọi người ghi chung một sổ.

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
python tintuc.py giá vàng 24h
python sochitieu.py "cà phê 35k"   # bot chi tiêu: chỉ đọc và xếp nhóm, không ghi
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
và Dân trí. Chứng khoán trong phiên: VPS (chỉ số), Vietcap (giá từng mã, dự phòng: VPS). Google News:
tìm tin theo từ khóa ([tintuc.py](tintuc.py), dự phòng: RSS VnExpress, Dân trí, Tuổi Trẻ, Thanh Niên),
tin theo mã, tin cổ tức. Âm lịch tính theo thuật toán của Hồ Ngọc Đức ([amlich.py](amlich.py)).
Lịch sử giá vàng không có nguồn công khai: bot tự ghi giá SJC mỗi tối.
