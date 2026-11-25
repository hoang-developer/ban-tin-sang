# Kế hoạch: từ bot lệnh thành trợ lý tài chính hiểu câu thường

Trạng thái: **bản nháp chờ duyệt** (25/11/2026). Mỗi mục "PR" là một pull request nhỏ, làm theo quy trình ở cuối file.

## 1. Mục tiêu và ba nguyên tắc

Người dùng nhắn gì bot cũng hiểu và trả lời, và **hiểu đúng ý trước khi làm**, gần như trò chuyện với Claude nhưng là trợ lý
tài chính cá nhân. Ba nguyên tắc giữ nguyên từ `CLAUDE.md`, thêm một:

1. Số tiền, ngày, nhóm do **code** tính; AI chỉ hiểu câu và viết chữ.
2. Việc không chắc thì **hỏi bằng nút**, không tự đoán. Việc chắc và nhỏ thì làm ngay, kèm cách **hoàn tác**.
3. Chỉ dùng Gemini gói miễn phí; câu nào luật code xử lý được thì không gọi AI.
4. (mới) Câu trả lời của AI có số tiền thì số đó phải **khớp số do code tính**, không thì bỏ phần số.

Các PR dưới đây **cố ý đổi hành vi** (khác đợt refactor). Mỗi PR phải liệt kê chính xác tin nhắn nào đổi kết quả; so snapshot
cũ/mới chỉ được khác đúng những ca đó.

## 2. Hiện trạng đã kiểm lại (25/11/2026, bằng `tests/harness.py`, AI giả)

| Tin nhắn | Kết quả hiện tại | Mong muốn |
|---|---|---|
| `mai tôi định mua laptop 20tr` | ghi chi 20.000.000đ | hỏi: có phải khoản chi không |
| `nếu mua xe 30tr thì sao` | ghi chi 30.000.000đ | không ghi, trả lời hoặc hỏi |
| `bún bò 6 chục` | ghi 6.000đ | hỏi: 6 chục = 60.000đ? |
| `mẹ cho 500k` | ghi **chi** 500.000đ, nhóm Khác | nhận là thu hoặc hỏi |
| `tôi vừa được tăng lương lên 25tr` | ghi **thu** 25.000.000đ | không ghi (là thông tin, hỏi có cập nhật lương) |
| `bitcoin giá bao nhiêu` | ra "Tổng: 35.000đ" của sổ chi tiêu, kể cả khi AI chạy | trả lời hoặc nói rõ chưa trả lời được |
| `lãi suất kép là gì`, `chào bot` | "Mình chưa rõ" + ví dụ | trả lời / chào lại |
| dán lại tin bot (nhiều dòng, có "Tổng:") | ghi từng dòng thành khoản mới | không ghi |
| bấm ✅ hai lần, Telegram gửi lại cùng `update_id` | có thể ghi hai lần | chỉ ghi một lần |
| `cà phê 35k`, `hôm qua mua laptop 20tr` | ghi ngay | **giữ nguyên** (không được làm chậm việc ghi nhanh) |

Điểm vào cần sửa (đã đọc): `api/chitieu.py:app`, `interface/chitieu/bot.py:respond` (dòng 71–111),
`interface/troly/assistant.py` (`wants`:171, `understand`:1214, `handle`:1172, `unsure`:1157, `card`:865),
`domain/phantich/query.py:is_question`, `domain/troly/spec.py` (TRIGGERS, BEYOND), `domain/common/money.py`,
`infrastructure/ai.py:chat` (budget mặc định 45 s), `infrastructure/kho.py:put_new` (đã có SET NX).

## 3. Giả định và quyết định còn chờ bạn

| # | Quyết định | Mặc định trong plan này | Cần chốt trước |
|---|---|---|---|
| A | Chính sách ghi | Chi nhỏ, rõ ràng (một số, có đơn vị, câu không phải hỏi/tương lai) thì **ghi ngay + ↩️ Hoàn tác**; còn lại qua thẻ "Mình hiểu là…". Ngưỡng ghi ngay đề xuất ≤ 2.000.000đ, chỉnh ở PR 2.1 | PR 2.1 |
| B | Riêng tư với Gemini gói miễn phí | Giữ mức gửi hiện tại; GĐ3 chỉ gửi **số tổng hợp**, không gửi ghi chú tự do và tên riêng | PR 3.0 |
| C | Bắt đầu từ đâu | Giai đoạn 1 | Ngay |

Giai đoạn 1 không phụ thuộc A và B, nên làm được ngay.

## 4. Model dùng cho từng phần, và chỗ phải đổi

Tôi không tự đổi được model của phiên. Tới mốc 🔁 tôi **dừng trước PR đó và báo bạn**, bạn đổi model rồi nhắn "tiếp".

| Phần | Model | Vì sao |
|---|---|---|
| PR 1.1 → 1.5, 2.2 → 2.6, 3.1 → 3.3, 3.5 → 3.7, GĐ4 | **Sonnet 5.5** (đang dùng) | Việc có đặc tả rõ, test và CI kiểm lại được |
| 🔁 **PR 2.1** (chính sách rủi ro) | **Opus 5.5** | Sai ở đây là ghi sai tiền, test khó bắt hết |
| 🔁 **PR 3.0** (thiết kế planner) và **PR 3.4** (prompt + định tuyến planner) | **Opus 5.5** | Thiết kế mở, không có đáp án đúng để test sẵn |
| 🔁 **PR 3.8** (rà soát cuối giai đoạn 3) | **Fable 5.2** nếu còn hạn mức tuần riêng, không thì Opus 5.5 | Một lượt đọc lại toàn bộ thay đổi tìm chỗ hở |

Sau mỗi PR dùng Opus/Fable, tôi báo bạn đổi về Sonnet 5.5. Cả kế hoạch có **bốn lần đổi đi và bốn lần đổi về**.

## 5. Giai đoạn 1: chặn ghi sai (khoảng 1 phiên 5 giờ)

Mục tiêu: không còn ca nào ở bảng mục 2 ghi tiền khi người dùng không có ý ghi.

**PR 1.1: Chống xử lý trùng.**
- `repositories/keys.py`: thêm khóa `seen(update_id)`; `repositories/chitieu/updates.py`: `first_time(id)` dùng `kho.put_new(..., 3600)`. Kho lỗi thì coi như chưa thấy (không chặn tin).
- `interface/chitieu/dedupe.py` được `api/chitieu.py:app` gọi trước khi xử lý; trùng thì trả 200 không làm gì. Với nút bấm: khóa theo thẻ (`y:ok:<id>` chạy một lần trong 30 giây), nên bấm đúp hay Telegram gửi lại đều không ghi hai lần.
- Test: hai lần cùng `update_id` ghi một khoản; hai lần `y:ok` liền nhau ghi một khoản; kho lỗi vẫn ghi.

**PR 1.2: Câu hỏi, ý định tương lai, tin dán lại không bao giờ ghi thẳng.**
- `domain/chitieu/guard.py` (thuần): `skip_reason(text)` trả `hoi`, `tuong_lai` (định, dự định, sẽ, sắp, chuẩn bị, mai, ngày mai, tuần sau, tháng sau), `gia_su` (nếu, giả sử, liệu, có nên), `dan_lai` (có "Mình hiểu là", "Đã ghi", "Tổng:", "🔎", ✅ hoặc từ hai dòng trở lên mang dấu hiệu tin bot), hoặc `None`.
- `interface/chitieu/bot.py:respond`: gọi trước nhánh `question`/`wants`/`record_text`. Có lý do thì không gọi `record_text`; dùng thẻ có sẵn `troly.unsure` (💸 Ghi là khoản chi / ❌ Không ghi) với câu mở đầu theo lý do; riêng `dan_lai` chỉ báo "giống tin bot gửi nên mình không ghi", không thẻ.
- Ca không được vỡ: `cà phê 35k`, `hôm qua mua laptop 20tr`, `mua laptop 20tr`, `hôm nay không tiêu gì`.
- Test: toàn bộ bảng mục 2 có dòng "không ghi", cộng các ca giữ nguyên. Chạy `tests/test_hieu.py` để chắc luồng AI không đổi.

**PR 1.3: Tổng thời gian chờ AI không vượt 50 giây.**
- `infrastructure/ai.py`: thêm hạn tuyệt đối cho một lượt xử lý (`with ai.deadline(50)`, đo bằng `time.monotonic`); `chat` lấy `min(budget còn lại, hạn còn lại - 4)` và báo lỗi khi còn dưới 5 giây. `api/chitieu.py:app` đặt hạn cho mỗi tin.
- Hiện đường dài nhất gồm `ask_ai` của troly (25 s) + xếp nhóm AI + số liệu cho AI, có thể vượt 60 s của Vercel.
- Test: giả đồng hồ, hai lượt AI chậm liên tiếp thì lượt hai bị cắt, bot vẫn trả câu "AI đang bận" thay vì treo.

**PR 1.4: Câu hỏi ngoài sổ chi tiêu không trả bằng sổ chi tiêu.**
- Nguyên nhân (đã tái hiện): `respond` dòng 104–106 đưa mọi câu hỏi **không chứa từ khóa BEYOND** thẳng vào `phantich.hoi`, nên "bitcoin giá bao nhiêu" ra tổng chi.
- Sửa: `domain/phantich/query.py: about_spending(text, cfg)` (có khoảng ngày, tên nhóm hoặc từ chi/tiêu/mua/hết); câu hỏi chỉ vào `hoi` khi `about_spending`; còn lại thì AI hiểu (`understand`), AI lỗi hoặc tắt thì trả câu nói thật "chưa trả lời được câu này" kèm nút Tài sản / Nợ / Chi tiêu. Đồng thời `understand` khi `question` và AI lỗi không còn rơi về `hoi` nếu không `about_spending`.
- Test: "bitcoin giá bao nhiêu", "lãi suất kép là gì" không còn ra sổ chi tiêu; "tháng này ăn phở bao nhiêu" vẫn vào `hoi`.

**PR 1.5: Bộ ca hồi quy.** Gom các ca ở mục 2 vào `tests/test_an_toan.py` (mỗi ca một dòng: tin nhắn, có ghi không, bot trả gì). Từ đây mọi PR sau phải xanh bộ này.

Sau PR 1.5: **dừng 2–3 ngày** quan sát tin nhắn thật (`/chuaxep`, `/lichsu`, trang trạng thái), rồi mới sang giai đoạn 2.

## 6. Giai đoạn 2: hiểu đúng ý (khoảng 1–2 phiên)

- 🔁 **PR 2.1: Chính sách rủi ro (Opus 5.5).** `domain/chitieu/risk.py` (thuần): nhận (số tiền, đơn vị rõ hay không, chiều, ngày, có nhiều số không, nguồn: luật/AI/ảnh) và trả `ghi_ngay` / `hoi_lai` / `xac_nhan_kep`. Gom luật rải rác hiện nay (`wants`, cờ `xac_nhan` của `JOBS`, `big_side_buy`) về một chỗ. Chốt ngưỡng với bạn (quyết định A). Đây là PR duy nhất của giai đoạn 2 phải xong trước các PR khác.
- **PR 2.2: Số mơ hồ.** `domain/common/money.py` nhận ra "chục", "rưỡi", "lít", "đô", "1 triệu 5", "nửa triệu"; số trơn dưới 1000 không có đơn vị vẫn là nghìn nhưng với mua sắm lớn thì hỏi lại bằng nút (35k / 350k / 35tr). Không đổi `cà phê 35`.
- **PR 2.3: Chiều thu.** "mẹ cho", "được cho", "lãi", "hoàn tiền", "bán đồ" nhận là thu hoặc hỏi "Đây là khoản thu?"; "tăng lương" là thông tin, hỏi có cập nhật lương không.
- **PR 2.4: Hoàn tác.** Nút ↩️ Hoàn tác dưới mọi khoản ghi ngay, dùng được 24 giờ, xóa đúng khoản đó kể cả khi có khoản khác ghi sau (khóa theo id, không theo "khoản cuối").
- **PR 2.5: Sửa số tiền, ngày, ghi chú.** Nút ✏️ hiện chỉ đổi nhóm; thêm đổi số tiền và ngày. Tin "sửa thành 40k" ngay sau khi ghi sửa khoản vừa ghi (trong 15 phút) thay vì thành khoản mới.
- **PR 2.6: Phản hồi ngắn với thẻ.** "ok", "đúng", "nhầm", "thôi", "hủy" gõ chữ được hiểu như bấm nút của thẻ gần nhất còn hạn.

## 7. Giai đoạn 3: giống Claude chat (khoảng 3–4 phiên)

- 🔁 **PR 3.0: Thiết kế (Opus 5.5).** Viết `docs/thiet-ke-planner.md`: lược đồ JSON của planner, danh sách công cụ, ngân sách token mỗi lượt, những gì được gửi cho AI (quyết định B), rào chắn trả lời.
- **PR 3.1: Việc `tro_chuyen`.** Xã giao, giải thích khái niệm tài chính chung ("lãi suất kép là gì") qua AI, có rào chắn: không khuyên mã cổ phiếu hay quỹ cụ thể, không hứa lợi nhuận, luôn là thông tin chung. Thêm vào `JOBS`/`spec`.
- **PR 3.2: Trí nhớ hội thoại ngắn.** `repositories/troly/memory.py`: 6 lượt gần nhất, hết hạn sau 30 phút, chỉ lưu tóm tắt việc (không lưu ghi chú tự do). Để "còn tháng trước thì sao?" kế thừa chủ đề.
- **PR 3.3: Công cụ chỉ đọc.** `services/troly/tools.py`: bảng công cụ do code viết (`chi_theo_ky`, `chi_theo_nhom`, `tai_san`, `no`, `quy_du_phong`, `tien_do_ngan_sach`) trả dữ liệu có cấu trúc, tái dùng service sẵn có.
- 🔁 **PR 3.4: Planner (Opus 5.5).** Một lượt gọi AI trả kế hoạch `{công cụ cần gọi, câu hỏi cần hỏi lại, việc cần xác nhận}`; code chạy công cụ; một lượt AI thứ hai (hoặc mẫu chữ) soạn câu trả lời từ kết quả. Tin nào luật code xử lý được thì không qua planner.
- **PR 3.5: Kiểm số trong câu trả lời.** Mọi số tiền trong câu AI viết phải khớp một giá trị công cụ trả; không khớp thì thay bằng mẫu chữ do code dựng.
- **PR 3.6: Hạn mức và bậc dự phòng.** Bộ đếm lượt AI trong ngày (một nơi, sửa lệch 50/80 giữa docstring và `CLAUDE.md`); hết lượt thì xuống bậc: luật code, rồi nút gợi ý, không im lặng.
- **PR 3.7: Ghép planner với hoàn tác và thẻ.** Mọi việc ghi do planner đề xuất đều qua thẻ hoặc `risk.py`, không có đường ghi riêng.
- 🔁 **PR 3.8: Rà soát cuối (Fable 5.2, hoặc Opus 5.5).** Đọc toàn bộ diff giai đoạn 3 tìm đường ghi không qua `risk.py`, số không qua kiểm, dữ liệu gửi ra ngoài vượt quyết định B.

## 8. Giai đoạn 4: đo chất lượng (khoảng 1 phiên)

- **PR 4.1:** mở rộng bộ 113 câu lên khoảng 300: xã giao, giả định, nối tiếp, không dấu, số mơ hồ, tin dán lại.
- **PR 4.2:** AI ghi sẵn (`tests/data/planner_fixtures`): test chạy không tốn lượt Gemini.
- **PR 4.3:** chạy thật theo lát nhỏ xoay vòng, khóa Gemini riêng, không đụng hạn mức của bot đang chạy.
- **PR 4.4:** cập nhật `CLAUDE.md` (số test, hạn mức, luồng mới), `docs/luong-tin-nhan.md`, `README.md`.

## 9. Rủi ro và cách giảm

| Rủi ro | Cách giảm |
|---|---|
| Hỏi lại quá nhiều làm bot chậm, phiền | Giữ nguyên đường ghi nhanh `cà phê 35k`; đo tỉ lệ ca phải hỏi trên sổ thật sau PR 1.2 và 2.1 |
| Luật "tương lai"/"giả sử" chặn nhầm khoản thật ("mai" trong tên riêng) | Chặn nhầm chỉ ra thẻ một chạm, không mất dữ liệu; ghi các ca nhầm thấy được vào `test_an_toan.py` |
| Hết hạn mức Gemini | PR 3.6; mặc định luôn có bậc không cần AI |
| Gửi dữ liệu cá nhân cho gói miễn phí | Quyết định B, PR 3.0 và 3.8 |
| Đổi hành vi làm vỡ thứ người dùng quen | Mỗi PR liệt kê tin đổi kết quả, snapshot khác đúng những ca đó, không hơn |
| AI "bịa số" | PR 3.5; hiện chưa đo trên Gemini thật, đo ở PR 4.3 |

## 10. Quy trình mỗi PR

1. Nhánh `claude/refactor-repository` đặt lại từ `main`, sửa, thêm test, chạy `python -m unittest discover -s tests -t . -v` và `tests/test_an_toan.py`.
2. So snapshot cũ/mới trên cùng đầu vào giả, liệt kê chỗ khác (chỉ được khác các ca định đổi).
3. Commit tiếng Việt, đẩy lên, mở PR (nội dung nêu rõ tin nào đổi kết quả), đăng ký theo dõi PR.
4. CI `kiemthu` xanh thì squash merge, chờ deploy, mở `/api/telegram` và `/api/chitieu` (phải thấy "Kho dữ liệu: đã kết nối", "Tin nhắn đang chờ: 0", lịch chạy tiến thêm mỗi 15 phút); lần tick đầu sau deploy là lần thử thật.
5. Không tự chạy bộ đo 113 câu khi không đụng định tuyến (hạn mức Gemini).

## 11. Không làm trong kế hoạch này

- Dùng model trả phí cho bot, hoặc đổi nhà cung cấp AI.
- Cho AI tự ghi hay sửa sổ không qua `risk.py`.
- Lưu lịch sử trò chuyện dài hạn hoặc ghi chú tự do vào trí nhớ.
- Khuyên đầu tư theo mã cụ thể.
