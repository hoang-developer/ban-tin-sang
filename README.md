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
- **📈 Đầu tư quỹ mở** (bot chi tiêu, nếu bật `/dautu`): ngày hạn đặt lệnh cuối tháng nhắc 8:30 và 13:00, sau 17h
  báo lệnh đã khớp, tin tối 21h có giá trị và lãi/lỗ các quỹ theo NAV; bản tin tối có dòng NAV quỹ.
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

**Nhắn câu thường, không cần nhớ lệnh** ([troly.py](troly.py), cần bật AI): ngoài khoản chi, bot hiểu cả các việc khác
và chỉ ghi sau khi bạn bấm ✅ trên thẻ "Mình hiểu là…" (có nút ✏️ Sửa: nhắn phần cần sửa, ví dụ «6 tháng»; ❌ Thôi):

- `mua 2 chỉ vàng nhẫn hết 27tr` · `gửi tiết kiệm VCB 50tr lãi 4,7% 6 tháng` · `vay anh Nam 10tr, mỗi tháng trả 2tr`
- `nạp 2tr vào quỹ dự phòng` · `tài khoản Techcombank còn 14tr` · `cho Dương vay 2tr` · `nhận lương 19tr`
- `sáng nay đặt mua 3tr VMEEF` · `bán 1300 HAG giá 12` · `đặt ngân sách ăn uống 3tr` · `hôm nay không tiêu gì`
- Hỏi: `tôi còn nợ bao nhiêu?` · `quỹ lãi lỗ thế nào?` · `tháng này cà phê hết bao nhiêu?`
- Thiếu thông tin thì bot hỏi từng câu (có nút chọn nhanh, nút Bỏ qua), trả lời ngắn như `4,7%` hay `6 tháng`.
- 📷 Ảnh lệnh mua/hoán đổi quỹ, đơn mua vàng, kết quả lệnh cổ phiếu: bot đọc, hỏi phần còn thiếu (ví dụ mã cổ phiếu)
  rồi hiện thẻ xác nhận.
- Nút **➕ Thêm** ở màn hình Tài sản, Sổ nợ: chọn loại rồi bot hỏi từng bước. Lệnh vừa khớp có nút sửa số ccq.

Cách chạy: khoản chi thường ("cà phê 35k") vẫn ghi ngay, không qua AI. Tin có chữ dễ là việc khác (chuyển, nạp, vàng,
vay, quỹ, tiết kiệm…) hoặc không có số tiền thì AI phân loại thành "việc" kèm các trường; code kiểm tra lại từng trường
(số tiền đối chiếu với số đọc được trong câu), tính toán và ghi bằng các hàm sẵn có. AI bảo là khoản chi thì bot nhớ, lần
sau ghi ngay. AI bận: bot hỏi lại bằng nút ("Ghi là khoản chi" / "Không ghi"), không tự đoán. AI nhận thêm tên các khoản
nợ, tài khoản, mã quỹ của bạn (không kèm số tiền) để gọi đúng tên. Thử một câu mà không ghi gì: mở
`https://ban-tin-sang.vercel.app/api/chitieu?hieu=mua 2 chỉ vàng nhẫn hết 27tr` (tối đa 40 câu mỗi ngày, không gửi tên
riêng cho AI).

**Kiểm thử** ([tests/](tests)): `python -m unittest discover -s tests -t .` chạy bot trong bộ nhớ (kho, Telegram, Fmarket,
AI đều giả lập; NAV thật của VMEEF, VFF trong `tests/data`), GitHub tự chạy mỗi lần đẩy code.

**Menu: 4 mục** ([menu.py](menu.py)), cũng là 4 nút cố định dưới ô chat (bot gửi lần đầu, hoặc khi bạn bấm nút của
hàng cũ):

- **🏠 Hôm nay** (`/menu`, `/start`): hôm nay đã chi gì, còn được tiêu bao nhiêu, tháng này đã chi/thu, tài khoản
  chính, chuỗi ngày ghi, và **việc cần làm** hôm nay, mỗi việc kèm nút làm luôn: hạn đặt lệnh quỹ, đã nhận lương chưa,
  lương về thì ✅ Làm hết theo kế hoạch (chưa thì từng khoản nợ tới kỳ), khoản chưa rõ nhóm; sau 18h chưa ghi gì thì
  có nút 🙅 Hôm nay không tiêu. Nút nhanh: Chi tiêu tháng, Dự báo, Vừa ghi, ➕ Thêm, Cài đặt.
- **💰 Tiền của tôi**: tài sản ròng và mỗi ngăn tiền một dòng: tài khoản chính, tài khoản khác, quỹ dự phòng (so với mục
  tiêu), quỹ mở và quỹ chờ, tiết kiệm, vàng, cổ phiếu (lãi/lỗ), nợ. Nút: tài khoản chính, chuyển tiền, chi tiết giá,
  biểu đồ, quỹ dự phòng, sổ nợ, đầu tư, sức khỏe.
- **🎯 Kế hoạch**: chia lương tháng này, đang ở bước mấy của lộ trình, nút ✅ Làm hết theo kế hoạch, 🎯 Lộ trình.
- **💬 Hỏi**: câu hay hỏi bấm là có (còn được tiêu bao nhiêu, tháng này tiêu vào đâu, so với tháng trước, còn nợ bao
  nhiêu, quỹ lãi lỗ, tài chính có ổn không, nhận xét tháng này); câu khác cứ nhắn câu thường.
- **⚙️ Cài đặt** (từ Hôm nay): nhóm, ngân sách, ngày lương, bật/tắt nhắc ghi chép 21h và báo lãi/lỗ quỹ buổi tối, xuất
  Excel.

Bấm nút thì mở ngay trong tin đó, có nút ⬅️ Hôm nay để quay lại. Nút Menu của Telegram chỉ còn vài lệnh chính (`/menu`,
`/taisan`, `/kehoach`, `/hoi`, `/baocao`, `/huongdan`); các lệnh khác vẫn gõ được, xem `/huongdan`.
Khai báo nhiều thứ một lần: dán nhiều lệnh trong một tin, mỗi lệnh một dòng, bot chạy lần lượt.

Số tiền hiểu được: `35k`, `35.000đ`, `35 nghìn`, `1tr2` (1.200.000đ), `2tr500`, `1,5tr`, `1k5`; số trơn
dưới 1.000 hiểu là nghìn (`cà phê 35` là 35.000đ). Nhóm có sẵn: Ăn uống, Đi chợ, Đi lại, Nhà cửa và hóa
đơn, Mua sắm, Sức khỏe, Giải trí và du lịch, Học tập, Hiếu hỷ và quà, Gia đình và con cái, Khác, Thu nhập.
Xếp sai thì bấm **✏️ Đổi nhóm** dưới tin: bot đổi và nhớ, lần sau gặp nội dung đó tự xếp đúng.
Từ khóa có sẵn của từng nhóm: phần "Nhóm chi tiêu" đầu [sochitieu.py](sochitieu.py).

### Tự xếp nhóm, ít khoản rơi vào Khác

Bot xếp mỗi khoản theo thứ tự: nhóm bạn đã tự chọn cho nội dung đó → từ khóa (bạn thêm, rồi có sẵn) →
AI (nếu bật, khoản có dấu ✨) → nếu vẫn chưa rõ thì **hỏi bạn ngay** bằng nút chọn nhóm dưới tin (bấm
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
| `/dubao` | Dự báo chi tiêu hằng ngày (ăn uống, đi chợ, đi lại; không tính mua sắm, khoản đột biến), mỗi ngày còn lại / hôm nay còn được tiêu bao nhiêu (xem dưới). `/dubao tatca`: mọi khoản |
| `/hoi` | Hỏi bằng câu thường, hoặc gõ thẳng câu hỏi: `tháng này cà phê hết bao nhiêu?` |
| `/bieudo` | Biểu đồ tròn theo nhóm và cột theo ngày; `/bieudo 10` cho tháng 10 |
| `/nhanxet` | Số liệu đáng chú ý của tháng + nhận xét và gợi ý tiết kiệm của AI; `/nhanxet 10` |
| `/taisan` | Tài sản ròng: tiền, tiết kiệm, cổ phiếu, quỹ, vàng, tiền số, ngoại tệ, nợ (xem dưới) |
| `/suckhoe` | Khám sức khỏe tài chính cá nhân |
| `/duphong` | Quỹ dự phòng: mục tiêu 3–12 tháng chi thiết yếu, tiến độ, mỗi tháng cần để bao nhiêu, để quỹ ở đâu (xem dưới) |
| `/luong` | Nhắc ngày nhận lương: `/luong 10 25tr` |
| `/tietkiem` | Chi lặt vặt so với trước khi dùng bot, đã bớt bao nhiêu, chuỗi ngày ghi chép, nhắc 21h (xem dưới) |
| `/dautu` | Đầu tư quỹ mở hằng tháng (Value Averaging): tháng này nên mua bao nhiêu, nhắc hạn đặt lệnh (xem dưới) |

**Thông báo gộp** ([thongbao.py](thongbao.py)), mỗi buổi tối đa một tin (qua lịch chạy `/api/tick` sẵn có):

- **☀️ Sáng** (từ 9h): đã nhận lương chưa, sổ tiết kiệm sắp đáo hạn, khoản nợ tới hạn chưa trả, chung một tin, nút
  của từng việc nằm dưới tin.
- **🌙 Tối** (từ 21h): hôm nay chưa ghi gì thì nhắc (nút 🙅 không tiêu), nhóm tiêu tăng vọt hay sắp vượt ngân sách,
  lãi/lỗ các quỹ ngày có NAV mới; đã ghi thì thêm dòng hôm nay chi bao nhiêu, trong mức hay quá. Không có gì đáng
  nói thì không gửi.
- Tối Chủ nhật 20h tổng kết tuần; ngày 1 tổng kết tháng trước (kèm dòng nợ, quỹ dự phòng), biểu đồ và nhận xét. 18h
  lưu tài sản ròng.
- Tin cần làm ngay vẫn gửi riêng: nhắc hạn đặt lệnh quỹ (8:30, 13:00), lệnh quỹ vừa khớp (sau 17h).

### Hiểu mình tiêu thế nào

Số liệu luôn do bot tự tính từ sổ; AI (nếu bật) chỉ hiểu câu hỏi và viết nhận xét. Code ở
[phantich.py](phantich.py).

- **Dự báo chi tiêu hằng ngày** (`/dubao`, nút 🔮 dưới báo cáo): chỉ tính các nhóm sinh hoạt thường nhật, mặc
  định ăn uống, đi chợ/siêu thị, đi lại (đổi: `/dubao nhom ăn uống, đi chợ`; về mặc định: `/dubao nhom macdinh`).
  Không tính mua sắm, tiền nhà, giải trí… và các **khoản đột biến**: khoản gấp 3 lần mức thường (trung vị 2 tháng)
  của nhóm, ít nhất 300k (chưa đủ dữ liệu thì từ 500k), ví dụ một bữa cơm khách 1,5tr; các khoản này được liệt kê
  riêng. Bot báo: đã chi (TB mỗi ngày), nhịp tiêu mỗi ngày theo từng nhóm (28 ngày qua), cả tháng khoảng bao nhiêu,
  so với tháng trước. Đặt `/ngansach hằng ngày 9tr` (hoặc đặt ngân sách cho đủ các nhóm hằng ngày) thì bot tính mỗi
  ngày còn lại được tiêu bao nhiêu, và mỗi lần ghi khoản ăn uống/đi chợ/đi lại đều báo "💡 Chi hằng ngày: hôm nay
  còn được tiêu …". `/dubao tatca`: dự báo mọi khoản như trước (đã chi + nhịp tiêu khoản dưới 1tr + khoản lớn tháng
  trước có mà tháng này chưa thấy; theo ngân sách tổng).
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
- **Ảnh lịch sử giao dịch ngân hàng** (nhiều dòng): bot hiện danh sách để chọn trước khi ghi. Tự chọn sẵn chi
  tiêu, thu nhập, trả nợ vay (vào nhóm "Trả nợ" nếu bạn đã tạo); tự bỏ qua **trả thẻ tín dụng** (các khoản quẹt
  thẻ đã ghi riêng, ghi nữa là trùng) và **chuyển tiền giữa các tài khoản của chính bạn** (bot nhận ra tên chủ
  tài khoản ở các dòng trả thẻ tín dụng và nhớ cho các lần sau). Bấm số để chọn/bỏ từng dòng, rồi "✅ Ghi".
  Giao dịch đã ghi (cùng ngày, số tiền, chiều) thì lần chụp sau tự bỏ qua, ghi "đã ghi trước đó".
- Hóa đơn có phần trả bằng voucher, Got It, điểm thưởng: bot hiện nút "➕ Ghi … vào Thu nhập" (điểm đổi từ
  chi tiêu thẻ là khoản thu; chi vẫn ghi đủ giá).
- Chữ kèm ảnh là ghi chú, có `#nhóm` thì vào nhóm đó: gửi ảnh kèm `cà phê với khách #giải trí`.
- Nhóm: cụm từ bạn đã dạy và từ khóa đi trước, không khớp mới dùng nhóm AI đoán (dấu ✨).
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
- **Mua bán cổ phiếu, ETF**: nhắn `mua 1000 FPT giá 95`, `mua 500 E1VFVN30 giá 33,6` hoặc `bán 500 FPT giá 120` (giá
  nghìn đồng hoặc đồng).
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
  | ETF | `/taisan etf E1VFVN30 1000 30` (ETF VN30 của Dragon Capital; mã E1VF…, FUE… tự vào nhóm ETF) | Giá khớp gần nhất (Vietcap) |
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
  đủ mấy tháng chi tiêu, nên 3–6), tỉ lệ để dành (nên từ 20% thu nhập), nợ (xem mục Sổ nợ),
  phân bổ (một mã quá 20% tài sản, tiền số quá 10%, một loại quá 70%), khoản đầu tư lỗ từ 20%, xu hướng
  tài sản ròng. Chi và thu lấy từ sổ 90 ngày qua. AI (nếu bật) viết 2 nhận xét và 2–3 việc nên làm có
  con số; được dặn không khuyên mua bán mã nào, không dự đoán giá. Chỉ để tham khảo.

### Một dòng tiền: tài khoản chính, chuyển giữa các ngăn

Code ở [taisan.py](taisan.py) (phần "Tài khoản chính"), [kehoach.py](kehoach.py) (làm hết theo kế hoạch, mỗi ngày
được tiêu). Tiền của bạn nằm ở nhiều ngăn: tài khoản ngân hàng, ví, quỹ dự phòng, quỹ chờ đầu tư, sổ tiết kiệm,
vàng, cổ phiếu, khoản nợ. Bot nối các ngăn thành một dòng tiền:

- **Tài khoản chính** (💼 Tài sản → 🏦 Tài khoản chính, hoặc nhắn `tài khoản VCB còn 30tr` rồi bấm "là tài khoản
  chính"): nơi lương về và hay tiêu nhất. Số dư = số dư thật lúc chốt + thu − chi ghi sổ sau lúc chốt ± tiền chuyển
  sang ngăn khác. Tính lại mỗi lần xem, nên sửa hay xóa khoản chi thì số dư tự đúng; khoản ghi bù ngày trước lúc chốt
  không tính (đã nằm trong số dư). Lệch với app ngân hàng thì bấm ✏️ Cập nhật số dư thật (hoặc nhắn lại câu trên).
- **Chuyển giữa các ngăn trừ nơi đi, cộng nơi đến** (tài sản ròng không đổi): nạp/rút quỹ dự phòng, để/rút tiền quỹ
  chờ đầu tư (`để 4tr vào quỹ chờ`, `/dautu nap`, `/dautu rut`), phần tiền mua quỹ không lấy từ quỹ chờ, gửi tiết
  kiệm, mua vàng, cho vay, mua bán cổ phiếu (không khai báo tài khoản DNSE thì tiền đi/về tài khoản chính), chuyển
  giữa hai tài khoản của mình (`chuyển 5tr từ VCB sang MoMo`, `rút 2tr tiền mặt`; tài khoản đến chưa có thì tạo).
  Trả nợ là khoản chi nhóm Trả nợ nên tự trừ tài khoản chính và dư nợ. Thẻ xác nhận ghi rõ "Tiền từ VCB: còn ~…";
  tiền có sẵn ở chỗ khác thì bấm 🔁 Tiền có sẵn, không trừ. Lệnh mua quỹ đã đặt chưa khớp vẫn tính vào tài sản (theo
  số tiền) tới khi thành ccq.
- **✅ Làm hết theo kế hoạch** (nút trên tin "Lương về!" và tin Chia lương): một lần bấm làm mọi việc còn lại của
  tháng: trả các khoản nợ tới kỳ (ghi khoản chi Trả nợ, trừ dư nợ), nạp quỹ dự phòng, để tiền vào quỹ chờ đầu tư. Bot
  hỏi lại một lần (liệt kê từng việc, tổng tiền, tài khoản chính còn bao nhiêu sau đó) rồi mới làm; tính lại lúc bấm
  nên bấm hai lần không làm hai lần.
- **Mỗi ngày được tiêu**: một con số dùng chung cho tin sau khi ghi, `/dubao`, màn hình tổng quan, Chia lương. Có
  ngân sách tổng thì theo ngân sách; không thì theo kế hoạch: thu − trả nợ tới kỳ − quỹ dự phòng − đầu tư là phần để
  chi tiêu cả tháng (không tính trả nợ). Trừ phần đã chi trước hôm nay và khoản lớn sắp tới (tháng trước có, tháng
  này chưa thấy), chia đều cho hôm nay và các ngày còn lại. Ngân sách hằng ngày (`/ngansach hằng ngày`) vẫn tính
  riêng cho ăn uống, đi chợ, đi lại. Khi có con số này, dòng tiết kiệm dưới tin chỉ còn chuỗi ngày và số đã bớt.
- Chưa chọn tài khoản chính thì mọi thứ như trước (bot chỉ ghi vào từng ngăn, không trừ số dư tài khoản nào).

### Quỹ dự phòng (bước đầu xây dựng tài chính)

Code ở [duphong.py](duphong.py). `/duphong` cho xem:

- **Chi thiết yếu mỗi tháng**, tính từ sổ 90 ngày qua (cần ít nhất 14 ngày ghi chép): ăn uống, đi chợ, đi lại
  (bỏ khoản đột biến), nhà cửa và hóa đơn, sức khỏe, học tập, gia đình, nhóm "Trả nợ" nếu đã tạo. Không tính mua
  sắm, giải trí, quà. Tự đặt: `/duphong chi 12tr` (về tự tính: `/duphong chi tu dong`).
- **Mục tiêu**: đủ 3/6/9/12 tháng chi thiết yếu (mặc định 6, chọn bằng nút hoặc `/duphong muctieu 6`), mốc khởi đầu
  1 tháng, rồi 3 tháng. Thanh tiến độ, đủ mấy tháng chi.
- **Mỗi tháng cần để bao nhiêu** để đạt trong 6/12/18/24 tháng (mặc định 12, `/duphong han 12`), so với số dư
  thu − chi trung bình 3 tháng (vừa sức hay căng; căng thì bot tính để 70% phần dư thì mất bao lâu).
- **Số dư quỹ**: tài khoản "Quỹ dự phòng" trong `/taisan` (`/duphong nap 2tr`, nút ➕, `/duphong rut 1tr` khi phải
  dùng) cộng các sổ tiết kiệm, quỹ có sẵn bạn gắn vào (`/duphong tinh ACB`). Để tiền vào quỹ là chuyển tiền,
  không tính là khoản chi. Chạm mốc thì bot chúc mừng.
- **Ngày nhận lương**: ghi `+ lương …` (hoặc ảnh lịch sử có lương) thì bot gợi ý chia lương (trả nợ → chi tiêu →
  quỹ dự phòng, xem mục Kế hoạch) kèm nút để luôn vào quỹ. Mỗi lần nạp được cộng vào số đã nạp của tháng.
- **🏦 Để quỹ ở đâu**: tiết kiệm không kỳ hạn hoặc tiết kiệm online kỳ hạn 1–3 tháng (chia vài sổ nhỏ), 1 tháng chi
  có thể để ở tài khoản thanh toán; lãi suất các sổ bạn đã khai báo; không để ở cổ phiếu, ETF, vàng.
- `/suckhoe` dùng đúng số liệu quỹ; tổng kết đầu tháng kèm tiến độ quỹ.

### Sổ nợ

Code ở [sono.py](sono.py). Khoản nợ lưu chung với tài sản (loại "Nợ" trong `/taisan`) nên tài sản ròng luôn đúng;
`/no` thêm phần trả dần:

- **Khai báo**: `/no chú Tư 300tr đã trả 32tr, trả 5tr/tháng, không lãi` ·
  `/no thẻ tín dụng trả góp 8,2tr, trả 4,39tr/tháng, ngày 5` · có lãi thì ghi `lãi 12%` (hoặc `lãi 1%/tháng`).
  Gõ lại cùng tên để sửa (`/no chú Tư trả 6tr/tháng`). Khoản mới tính kỳ trả từ tháng sau (số dư khai báo đã gồm lần
  trả tháng này); chưa trả tháng này thì thêm `tháng này chưa trả`. Lần đầu bot tạo nhóm chi 🏦 Trả nợ.
- **`/no`**: mỗi khoản còn bao nhiêu / tổng ban đầu, thanh tiến độ, có lãi hay không, mỗi tháng trả bao nhiêu, còn
  mấy tháng và tháng nào xong, tháng này đã trả chưa (nút ✅ Trả). Khoản sắp xong thì báo trước mỗi tháng dư ra bao
  nhiêu.
- **Trả nợ tự trừ dư nợ**: bấm ✅ Trả; nhắn `trả nợ chú Tư 5tr`; hoặc gửi ảnh chuyển khoản. Bot so tên khoản nợ với
  nội dung, với khoản ở nhóm Trả nợ thì so cả số tiền với mức trả mỗi tháng; chưa chắc thì hỏi "trừ vào khoản nào".
  Có nút ↩️ Không trừ; xóa khoản chi đó thì dư nợ được cộng lại. Khoản trả nợ vẫn là khoản chi nhóm Trả nợ.
- **Nhắc**: tháng nào chưa trả, 9h ngày hạn (không đặt thì 2 ngày sau ngày lương, không có ngày lương thì ngày 10)
  bot nhắc kèm nút "Đã trả", 5 ngày sau nhắc thêm một lần.
- **Trả xong** một khoản: bot chúc mừng; từ tháng sau khoản tiền đó được gợi ý chuyển vào quỹ dự phòng.
- **Khám sức khỏe** chấm nợ theo tiền trả mỗi tháng so với thu nhập (nên dưới 30%), ghi riêng nợ có lãi và nợ không
  lãi (người thân); chưa biết thu nhập thì theo nợ có lãi so với tài sản. Tổng kết đầu tháng kèm sổ nợ.

### Kế hoạch: lộ trình xây tài sản và chia lương

Code ở [kehoach.py](kehoach.py). `/kehoach` cho xem lộ trình 5 bước, bot tự đánh dấu ✅ đã xong, 👉 đang làm:

1. Ghi chép chi tiêu ít nhất 2 tuần
2. Quỹ dự phòng mốc đầu: 1 tháng chi thiết yếu
3. Trả hết nợ có lãi (thẻ tín dụng, trả góp, vay tiêu dùng)
4. Quỹ dự phòng đủ mục tiêu (mặc định 6 tháng chi thiết yếu)
5. Đầu tư đều mỗi tháng: tiết kiệm, vàng, ETF, cổ phiếu (hiện đang có bao nhiêu mỗi loại)

Nợ không lãi (người thân) trả đều theo hẹn, song song với mọi bước. Dưới lộ trình là việc nên làm bây giờ (trả
khoản nợ tới kỳ, nạp quỹ tháng này, xếp nhóm khoản chưa rõ).

**Chia lương** (`/kehoach chia`, nút 📋, tự gợi ý khi ghi lương): thu tháng này → trả nợ tới kỳ (đã trả ✅ hay chưa)
→ chi tiêu dự kiến (trung bình 90 ngày qua, không tính trả nợ; có ngân sách tổng thì theo ngân sách) → quỹ dự phòng
(mức để kịp hạn, cộng tiền trước đây trả các khoản nợ đã xong; không quá phần thu còn lại) → còn lại. Nút trả nợ, nạp
quỹ ngay trên tin, hoặc ✅ Làm hết theo kế hoạch (xem mục Một dòng tiền). Chưa ghi lương thì dùng số ở `/luong`,
không có thì thu trung bình 3 tháng. Đã bật `/dautu` thì thêm bước 📈 góp vào quỹ chờ (sau quỹ dự phòng). Cuối tin là
"hôm nay còn được tiêu bao nhiêu" và số dư tài khoản chính.

### Đầu tư quỹ mở hằng tháng (Value Averaging)

Code ở [dautu.py](dautu.py). Bật: `/dautu batdau 4tr VMEEF` (góp 4 triệu mỗi tháng, mã quỹ trên Fmarket). Bot không
đặt lệnh, không chuyển tiền: bot tính nên mua bao nhiêu và nhắc, bạn đặt trên Fmarket rồi bấm ✅.

- **Đường kế hoạch**: tháng đầu = số góp (cộng giá trị quỹ đang có lúc bật), mỗi tháng sau = tháng trước × 1,01 + số
  góp (đổi mức tăng: `/dautu tang 1%`; tháng tạm dừng thì không cộng số góp).
- **Mỗi tháng mua** = kế hoạch − giá trị quỹ đang có, không quá tiền đang có (quỹ chờ + phần góp tháng này chưa để),
  làm tròn xuống 10.000đ, dưới 100.000đ thì không mua. Quỹ giảm thì mua nhiều hơn, tăng nhanh thì mua ít hoặc không
  mua, tiền để ở **quỹ chờ** (tài khoản "Quỹ chờ VMEEF" trong `/taisan`, tiền thật nên gửi tiết kiệm online kỳ hạn
  ngắn). Không bao giờ bán (phí bán VMEEF 2% năm đầu, 1% năm thứ hai).
- **Hạn đặt lệnh**: trước 14:40 phiên đóng sổ cuối cùng của tháng, khớp NAV phiên đầu tháng sau (lịch phiên lấy từ
  Fmarket nên tính đúng cả dịp nghỉ lễ). Sáng hôm đó 8:30 bot nhắc kèm số tiền và nút ✅ Đã đặt lệnh, 13:00 nhắc lại
  nếu chưa bấm. Ngày thường `/dautu` chỉ cho con số dự kiến.
- **Khớp lệnh**: sau 17h ngày khớp, bot lấy NAV, tính số ccq (phí mua 0%), cộng vào `/taisan`. Fmarket báo số khác
  thì `/dautu ccq 66,43`. Mua ngoài lịch: vừa đặt xong thì `/dautu dadat 3tr` hoặc nhắn `mua VMEEF 3tr`; lệnh đặt
  hôm khác thì thêm **ngày đặt lệnh** (`/dautu dadat 1tr 9/11`, đặt sau 14:40 thì thêm `sau 14h40`), bot tự tính phiên
  khớp (đặt trước 14:40 khớp phiên giao dịch kế tiếp, cuối tuần và ngày lễ theo lịch NAV thật).
- **Góp tiền**: ghi `+ lương …` thì gợi ý chia lương có nút 📈 để tiền vào quỹ chờ; qua hạn cuối tháng mà chưa để thì
  bot tự tính phần góp tháng đó vào quỹ chờ (sửa số dư thật: `/dautu quycho 12tr`). Quỹ dự phòng chưa tới mốc 1 tháng
  chi thiết yếu thì bot khuyên tạm dừng góp (không chặn): nút ⏸ hoặc `/dautu bo`.
- **Quỹ chờ là quỹ trái phiếu** (`/dautu quycho VFF`): hoán đổi VFF ↔ VMEEF miễn phí (bán VFF ra tiền mặt trong
  12 tháng đầu mới mất 2%), nên VFF vừa là phần trái phiếu của danh mục, vừa là tiền chờ cho VA. Góp thêm mỗi tháng vào
  VFF: `/dautu vff 1tr` (ví dụ 4tr VA + 1tr VFF). Mỗi tháng tiền góp mua VMEEF trước theo VA, phần chưa mua vào VFF; tháng
  cần mua nhiều hơn tiền góp thì hoán đổi từ VFF. Tin ngày hạn ghi sẵn từng lệnh (mua VMEEF, mua VFF, hoán đổi bao nhiêu
  ccq) và một nút ✅ ghi tất cả; khớp lệnh bot tự cập nhật số ccq (VFF giao dịch thứ Ba, thứ Năm). Đã mua VFF
  ngoài lịch: nhắn `mua VFF 1tr`; đã hoán đổi: `/dautu doi 125,5`; sửa số ccq VFF: `/dautu ccq 36,7 vff`.
  **Hoán đổi mất khoảng 1 tuần, hai bước**: bán VFF (tối ngày khớp bot trừ ccq VFF, tiền "VMEEF đang chuyển" vẫn tính vào
  tài sản), tiền về rồi mới mua VMEEF. Từ 7 ngày sau ngày đặt, tin sáng và 🏠 Hôm nay hỏi "xong chưa?" (bấm ⏳ Chưa thì 2
  ngày sau hỏi lại); xong thì bot hỏi ngày bán, ngày mua (và số ccq Fmarket báo, bỏ qua được), tính theo NAV đúng ngày rồi
  cập nhật hai quỹ. Nhắn câu thường cũng được: «hoán đổi VFF xong, bán 18/11 mua 21/11». Chạy thử trên
  NAV thật (góp 5tr: 4tr VA + 1tr VFF, VA được rút từ VFF): tài sản cuối gần bằng dồn cả 5tr vào cổ phiếu (−1% tới +2%),
  sụt giảm lớn nhất nhẹ hơn 4–6 điểm; VFF tăng 6–10% mỗi năm, giảm sâu nhất −4,3% (2014), vẫn tăng trong đợt sập 2022.
- Bản tin tối của bot bản tin có thêm dòng NAV quỹ, % hôm nay, cách đỉnh 52 tuần.
- **Khoản tiền lớn** (ví dụ tiền bán cổ phiếu): mua hết vào VFF, rồi `/dautu taicocau 15,5tr` (mặc định rải 80% phần
  cổ phiếu trong 3 tháng; đổi: `/dautu taicocau 15,5tr 6 thang 70%`). Bot ghi lệnh mua VFF (không tính vào tiền góp hằng
  tháng) và cộng dần phần cổ phiếu vào kế hoạch VMEEF, mỗi ngày hạn cuối tháng tin nhắc gộp sẵn lệnh hoán đổi VFF →
  VMEEF; VA vẫn chỉnh theo giá. Chạy thử trên NAV thật: mua hết ngay thắng rải 55–64% số lần, rải 3 tháng thiệt trung
  bình ~0,4% nhưng tránh được trường hợp mua đúng đỉnh. Bỏ phần còn lại: `/dautu taicocau xoa`.
- **Lãi/lỗ quỹ trong tin tối 21h** (bot chi tiêu, chỉ ngày có NAV mới), mỗi quỹ một dòng: giá trị theo NAV và lãi/lỗ so với tiền gốc
  (`VMEEF 1,01tr · 🟢 +7k (+0,7%)`), thêm dòng tổng và số tiền đang chờ khớp. Tắt: `/dautu baocao tat`. Fmarket cập nhật danh mục mà top 10
  có VIC, VHM, VRE, VPL thì bot báo.
- Chạy thử trên NAV thật (Fmarket) từ năm bắt đầu khác nhau, so với mua đều 4tr đầu mỗi tháng (DCA), tiền chờ lãi
  4,5%/năm: VA thắng VMEEF 3/3 lần, VESAF 6/7, SSISCA 10/10, DCDS 20/20; hơn trung vị 0,6–1,4% tổng tài sản cuối kỳ,
  sụt giảm lớn nhất thấp hơn (DCDS −42% so với −54%). Đổi lại có lúc quỹ chờ lên vài chục triệu, nhiều tháng liền không
  mua rồi một tháng mua lớn. Kết quả quá khứ không bảo đảm tương lai; tham khảo, không phải lời khuyên đầu tư.

### Tiết kiệm từ khi dùng bot, chuỗi ngày ghi chép

Code ở [tietkiem.py](tietkiem.py). `/tietkiem` cho xem chi lặt vặt so với **trước khi dùng bot**, để thấy ghi chép đều
giúp bớt được bao nhiêu.

- **Mốc**: chi lặt vặt (mỗi khoản dưới 1 triệu, không tính thu nhập, trả nợ) trung bình mỗi ngày trước khi dùng bot,
  mặc định 323.700đ/ngày, tính từ sao kê thẻ tín dụng và tài khoản 11/09–20/10/2026 (đã bỏ trả thẻ, chuyển giữa tài
  khoản của mình, trả nợ, khoản mua hộ; trừ tiền bạn bè trả lại). Đổi: `/tietkiem moc 300k`; ngày bắt đầu tính:
  `/tietkiem batdau 04/11`.
- **Đã bớt** = cộng dồn (mốc − chi lặt vặt của ngày) qua các **ngày có ghi**: có ít nhất một khoản chi, hoặc bấm
  "🙅 Hôm nay không tiêu" (`/tietkiem khongtieu`). Ngày không ghi gì thì không tính (không ghi không phải là tiết
  kiệm); hôm nay chưa hết ngày nên chưa cộng. Mốc từ sao kê không có tiền mặt còn sổ ghi có, nên số đã bớt có thể thấp
  hơn thực tế một chút.
- Sau mỗi khoản ghi có dòng `🔥 6 ngày · hôm nay 180k/324k · từ 04/11 đã bớt ~1,9tr`; màn hình `/menu` và tổng kết
  tuần cũng có. Chạm mốc (chuỗi 7/30/100/365 ngày, bớt được 1/5/10/20/50/100 triệu) thì bot chúc mừng một lần.
- **Chuỗi ngày ghi chép**: quên một ngày thì ghi bù (`hôm qua ăn tối 250k` hoặc nút "↩️ Hôm qua không tiêu") là chuỗi
  vẫn giữ. Bot không nhấn vào chuyện đứt chuỗi, chỉ hiện chuỗi hiện tại và kỷ lục (nghiên cứu: chuỗi đứt làm giảm động
  lực, cho sửa lại thì đỡ).
- **Nhắc 21h** (trong tin tối, chỉ khi hôm đó chưa ghi khoản chi nào), kèm chuỗi và số đã bớt; tắt ở ⚙️ Cài đặt hoặc
  `/tietkiem nhac tat`.
- **Đã để dành thật**: tiền nạp quỹ dự phòng, góp đầu tư (`/dautu`), trả nợ từ ngày bắt đầu. Chi ít hơn mốc chỉ thành
  tiền để dành khi chuyển đi, nên `/tietkiem` có nút chuyển phần đã bớt vào quỹ chờ đầu tư hoặc quỹ dự phòng.

### Cài bot chi tiêu (làm một lần)

1. Trong Telegram nhắn **@BotFather** → `/newbot` → đặt tên (ví dụ "Chi tiêu của tôi") và username
   (phải kết thúc bằng `bot`) → sao chép token.
2. Trên Vercel, dự án `ban-tin-sang` → **Settings** → **Environment Variables** → thêm
   `CHITIEU_BOT_TOKEN` = token vừa sao chép → **Save** → tab **Deployments** → **⋯** ở bản Production →
   **Redeploy**.
3. Mở `https://ban-tin-sang.vercel.app/api/chitieu` bằng trình duyệt: trang báo "Đã cài webhook".
4. Vào Telegram, mở bot mới, nhắn `cà phê 35k`.

### AI (tùy chọn, miễn phí): Google Gemini, OpenRouter dự phòng

AI giúp bot ở các việc: xếp nhóm khoản lạ (dấu ✨), hiểu câu hỏi, viết nhận xét tháng và khám sức khỏe tài
chính. Mọi con số vẫn do bot tự tính. Khoản nào từ khóa không nhận ra thì bot hỏi AI; AI được biết cả nhóm
bạn tự tạo (kèm từ khóa) và những khoản bạn đã tự xếp để đoán theo thói quen của bạn; không chắc thì AI để
Khác và bot hỏi bạn. Bot nhớ câu trả lời, cùng nội dung không hỏi lại. AI lỗi, bận hay hết lượt thì bot vẫn
chạy: khoản lạ bot hỏi bạn, câu hỏi bot tự hiểu cách đơn giản, nhận xét chỉ có số liệu.

**Google Gemini (dùng trước).** Thử ngày 04–05/11/2026: `gemini-3.5-flash-lite` xếp đúng 13/13 khoản lạ trong
khoảng 1 giây, hiểu đúng 5/5 câu hỏi mẫu (dưới 1 giây mỗi câu), đọc đúng số tiền 7/7 ảnh hóa đơn/chuyển
khoản và ảnh lịch sử 7 giao dịch; `gemini-3.1-flash-lite` cũng đúng 13/13 và đọc đúng các ảnh (1–2 giây, lúc 3.5
báo quá tải vẫn chạy); `gemini-3.5-flash` 13/13 nhưng chậm hơn. Bot thử lần lượt 3.5 Flash-Lite, 3.1
Flash-Lite, 3.5 Flash (lỗi/bận/hết lượt thì sang model sau), rồi tới OpenRouter. Gói miễn phí không cần thẻ; giới hạn tính theo dự án và theo từng model (Flash: 5 lượt
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
