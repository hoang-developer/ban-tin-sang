# Kế hoạch cải thiện nghiệp vụ (giai đoạn 0)

Trạng thái: **đã duyệt các mặc định ở mục 2** (25/11/2026). Nguồn: hội đồng 4 Business Analyst chấm nghiệp vụ chi tiêu, tài sản – nợ – dự phòng,
đầu tư – thị trường, và xuyên suốt. Điểm trung bình: đúng nghiệp vụ 5,5 · đầy đủ 6,5 · **nhất quán 4,8** · hữu ích 7,0.
26 lỗi trong báo cáo đã được chạy lại bằng `tests/harness.py` (AI giả) và cả 26 tái hiện được.

## Tiến độ (cập nhật 25/11/2026)

- **Xong và đã deploy:** PR 0.1 (#89), PR 0.2 (#90), giai đoạn 1 của kế hoạch trợ lý (#91: chống xử lý trùng, không ghi thẳng dự định/giả định/tin bot dán lại, hạn AI 50 giây, câu hỏi ngoài sổ chi tiêu, bộ ca hồi quy `tests/test_an_toan.py`).
- **PR 0.3 (tiền phải có nguồn):** làm xong, khác kế hoạch ở một điểm: khoản nợ mới chỉ có nút «💰 Tiền vay đã vào <tài khoản chính>» (không nút "tài khoản khác"; không bấm nghĩa là khai báo nợ đang có). Tiền vào ví khác thì khai báo ví đó ở `/taisan`.
- **PR 0.4 (sổ tiết kiệm đáo hạn và tất toán sớm):** làm xong. Lãi không kỳ hạn mặc định 0,5%/năm, chỉnh theo sổ bằng trường `lai_kkh` (chưa có lệnh riêng; người dùng nhập số thật nhận về khi tất toán).
- **PR 0.5 (nợ có lãi giảm dần):** làm xong: lãi dồn theo ngày, trả lãi trước gốc, số kỳ theo công thức trả góp, cảnh báo mức trả không đủ lãi và trả dư. Dư nợ trong tài sản ròng vẫn là gốc đã ghi (chưa cộng lãi dồn chưa trả); phần lãi trong khoản trả chưa được tách ra khỏi "chi" (làm ở PR 0.6).
- **PR 0.6 (một định nghĩa dòng tiền):** làm xong (`domain/chitieu/flow.py`). Hoàn tiền lưu là khoản số âm ở nhóm gốc (cờ `hoan`), nên mọi tổng cộng thẳng là đúng mà không cần sửa từng chỗ. "Để dành thật" không còn tính trả nợ.
- **Việc kế tiếp:** PR 0.7 (kế hoạch theo kỳ lương), PR 2.1 (chính sách rủi ro), vẫn Opus.

Giai đoạn này đứng **trước** các giai đoạn của `docs/ke-hoach-tro-ly.md` vì trợ lý hội thoại (giai đoạn 3) đưa chính các con số này
cho AI viết thành lời; số sai thì lời càng thuyết phục càng nguy hiểm.

## 1. Nguyên tắc

1. **Một định nghĩa, một chỗ.** "Chi", "thu", "mỗi ngày được tiêu" chỉ tính ở một hàm; mọi màn hình gọi hàm đó. Có test so chéo.
2. **Thiếu dữ liệu thì nói thiếu**, không hiện số suy ra như số thật (quỹ chờ ảo, dự báo từ 1 ngày, mốc của người khác).
3. **Mọi khoản tiền vào/ra có nguồn.** Không cộng tiền vào ngăn nào mà không trừ ở nơi đi hoặc không có xác nhận của người dùng.
4. **Không đổi cấu trúc Redis**: trường mới chỉ là tùy chọn, dữ liệu cũ đọc được không cần chuyển đổi (luật hợp đồng trong `CLAUDE.md`).
5. **Mỗi PR liệt kê tin nhắn/màn hình nào đổi kết quả** và đính kèm so sánh snapshot cũ/mới chỉ khác đúng các ca đó.

## 2. Quyết định đã chốt

| # | Quyết định |
|---|---|
| 1 | Thẻ tín dụng tính **lúc quẹt**; trả thẻ không phải chi |
| 2 | **Trả gốc nợ** không tính là chi, hiện thành dòng riêng "Trả gốc nợ" |
| 3 | **Lãi/lỗ đầu tư** là dòng riêng "Đầu tư", ghi cả lỗ, không vào thu nhập để tiêu |
| 4 | Nợ có lãi tính theo **dư nợ giảm dần** (lãi dồn theo ngày) |
| 5 | Kế hoạch theo **kỳ lương**; phần dư sau chia lương mặc định **để dành**, cho chỉnh |
| 6 | **Hoàn tiền** giảm chi của nhóm gốc, không thành Thu nhập |
| 7 | Ngày "dd/mm" sau hôm nay thì **hỏi lại** |
| 8 | Nhận định tự gửi chỉ nêu **ngành và số liệu**; nêu mã khi người dùng hỏi |

Không đổi: tiền trả nợ vẫn **không** tính vào chi thiết yếu của quỹ dự phòng (yêu cầu ngày 18/11).

## 3. Thứ tự thực hiện và mốc đổi model

| Bước | PR | Model |
|---|---|---|
| A | 0.1, 0.2 | Sonnet 5.5 |
| B | Giai đoạn 1 của `ke-hoach-tro-ly.md`: 1.1 → 1.5, rồi **dừng 2–3 ngày** xem bot chạy với tin thật | Sonnet 5.5 |
| C | 0.3, 0.4, 0.5 | Sonnet 5.5 |
| D | 🔁 **đổi sang Opus 5.5**: 0.6, 0.7, rồi PR 2.1 (chính sách rủi ro) | Opus 5.5 |
| E | 🔁 **đổi về Sonnet 5.5**: 0.8, 0.9, 0.10, 0.11, rồi PR 2.2 → 2.6 | Sonnet 5.5 |
| F | Giai đoạn 3 và 4 như `ke-hoach-tro-ly.md` (3.0, 3.4 dùng Opus; 3.8 dùng Fable hoặc Opus) | theo plan cũ |

Mốc đổi model đầu tiên nằm sau PR 0.5, tức sau khoảng 9 PR. Trước đó chỉ dùng Sonnet.

## 4. Chi tiết từng PR

Kích cỡ: S nhỏ, M vừa, L lớn (có thể tách đôi nếu diff quá 600 dòng).

### PR 0.1: Tài sản không mất lãi, không bị ghi đè (S–M)
- **Đối chiếu sổ tiết kiệm không đặt lại ngày gửi.** `services/doichieu/reconcile.py:94` ghi `it["ngay"]`, mà với sổ tiết kiệm trường này là ngày gửi. Sổ chỉ ghi ngày đối chiếu vào trường riêng; ngày gửi, kỳ hạn, lãi suất không đổi.
- **Cho cùng một người vay lần hai thì cộng dồn.** `services/taisan/declare.py:28-29` đang ghi đè số tiền.
- **Đối chiếu lệch dương thì hỏi trước.** Thay "Ghi 50k là thu chưa ghi" bằng câu "Có khoản chi tiền mặt/thẻ chưa ghi không?", nút "ghi là thu" để sau.
- Tin đổi kết quả: tin báo cho vay lần hai ("Đã cộng thêm… tổng 3tr"), màn đối chiếu khi lệch dương.
- Chấp nhận: sổ 100tr 6% 12 tháng gửi 01/01/2026, đối chiếu khớp ngày 15/11 thì ngày gửi vẫn 01/01/2026, đáo hạn 01/01/2027, lãi tới nay không về 0. Cho vay 2tr rồi 1tr ra 3tr; thu 1tr còn 2tr; tài sản ròng không đổi qua các lần cho vay.

### PR 0.2: Sổ chi tiêu, ngày mơ hồ và học nhóm an toàn (M)
- **Ngày "dd/mm" sau hôm nay** (`domain/chitieu/parse.py:13-31` đang lùi về năm trước, im lặng). Trong 31 ngày tới thì **chưa ghi**, hỏi bằng thẻ: «27/11/2026 (sắp tới)» / «27/11/2025» / «Hôm nay». Xa hơn 31 ngày thì giữ năm trước nhưng tin báo hiện đủ năm.
- **"tối qua", "đêm qua", "sáng qua", "chiều qua", "trưa qua"** hiểu là hôm qua (hiện ghi vào hôm nay).
- **Học nhóm không lan.** `domain/chitieu/learn.py:15-17`: cụm học được 1 chữ chỉ khớp khi **cả ghi chú** bằng cụm đó; cụm từ 2 chữ trở lên vẫn khớp trong câu. Áp lúc so khớp nên dữ liệu đã học không cần chuyển đổi. Thêm `/nhom hoc` (xem các cụm đã học) và `/nhom hoc xoa <cụm>`.
- Chấp nhận: ngày 20/11 nhắn "27/11 đóng học 3tr" thì hiện thẻ hỏi, chọn xong khoản vào đúng tháng. Học "bò" sang Đi chợ rồi "phở bò", "bún bò", "bò bía" giữ nhóm cũ, còn "bò" riêng vào Đi chợ. Học "mua" sang Gia đình rồi "mua áo" không đổi nhóm. Lúc 00:30, "tối qua ăn lẩu 300k" ghi vào hôm qua.

### PR 0.3: Tiền phải có nguồn (M)
- **Vay mới.** Thẻ `no_moi` và `/no …` hỏi "Tiền vay đã vào tài khoản nào?" với nút: tài khoản chính / tài khoản khác / "Không, khai báo nợ cũ". Chọn tài khoản thì cộng số dư qua `move_main`.
- **Quỹ chờ không tự sinh tiền.** `services/dautu/status.py:140-143` đang tự cộng phần góp vào "Quỹ chờ" khi hết kỳ; đổi thành thẻ "Đã để 4tr vào quỹ chờ chưa?" (Có thì trừ tài khoản chính và cộng quỹ chờ). `money_now` (`status.py:170`) không coi phần chưa để là đã có.
- **Rút quỹ dự phòng trừ vào "đã nạp tháng"** (`services/duphong/reserve.py:75-88` và kế hoạch).
- **Tiền nhà không bị tính hai lần** khi có 31–45 ngày dữ liệu (`domain/duphong/reserve.py:41` làm tròn số tháng): gom khoản hóa đơn theo tháng lịch.
- Chấp nhận: vay 10tr vào VCB thì tài sản ròng không đổi; chọn "khai báo nợ cũ" thì như hiện nay. `/dautu batdau 4tr VMEEF` ngày 9/9, không góp, xem ngày 13/11: không có "Quỹ chờ 8tr", "nên mua" không vượt tiền thật có. Nạp 2,6tr rồi rút 2tr thì "đã nạp" là 0,6tr. Tiền nhà 5tr ngày 01/10 và 01/11, ăn 100k/ngày, xem 14/11: tiền nhà 5tr/tháng, mục tiêu quỹ 48,24tr (hiện 78,24tr).

### PR 0.4: Sổ tiết kiệm, đáo hạn và tất toán sớm (S–M)
- **Tất toán trước hạn** chỉ được lãi không kỳ hạn (mặc định 0,5%/năm, chỉnh được theo sổ). Hiện bot cộng đủ lãi có kỳ hạn (5.391.781đ cho sổ ACB ở kịch bản đã chạy) làm thu nhập và tài khoản chính dư vài triệu.
- **Sổ đã đáo hạn không bị đóng băng**: tin sáng hỏi "Sổ X đã đáo hạn: tái tục hay rút về tài khoản chính?" kèm nút; chưa trả lời thì tài sản ròng ghi rõ "đã tới hạn, chờ xử lý" (không cộng thêm lãi).
- Chấp nhận: tất toán sổ 100tr 6% sau 10 tháng, trước hạn, nhận gốc + lãi không kỳ hạn; thu nhập không tăng 5tr. Sổ đáo hạn 01/01/2026, xem 25/11/2026: hiện nút tái tục/rút.

### PR 0.5: Nợ có lãi tính theo dư nợ giảm dần (M)
- `domain/no/debt.py:240-248, 91-100`: khi nợ có `lai > 0`, lãi dồn theo ngày từ lần cập nhật dư nợ gần nhất (lãi = dư nợ × lãi% × số ngày / 365, thêm trường tùy chọn `ngay_lai`). Mỗi lần trả: trừ lãi trước rồi gốc. Số kỳ còn lại: `n = −ln(1 − r·B/P) / ln(1 + r)` với `r = lãi/1200`; nếu mức trả không lớn hơn lãi một kỳ thì cảnh báo "mức trả không đủ trả lãi". Nợ không lãi giữ nguyên.
- Trả dư hơn số còn nợ thì báo phần dư (`debt.py:242`), không mất lặng lẽ.
- Tin báo mỗi lần trả hiện "trong đó lãi X, gốc Y".
- Chấp nhận: khai nợ 100tr lãi 12%, trả 10tr/tháng, trả lần đầu đúng 30 ngày sau: còn ≈ 90,99tr, còn 10 kỳ (tổng 11 kỳ, hiện bot báo 10 kỳ), tổng lãi ≈ 5,9tr. Nợ 0% không đổi kết quả so với hiện nay.

### PR 0.6: Một định nghĩa dòng tiền (L) 🔁 Opus
Hiện có 27 chỗ so sánh nhóm với `INCOME` (99 lần nhắc `INCOME`, `no`, `is_debt_payment` ở 37 file); báo cáo (`presentation/chitieu/view.py:105-108`, `services/chitieu/budget.py:20`) tính chi là mọi thứ không phải thu nhập, còn kế hoạch (`services/kehoach/plan.py:34,66`) bỏ nhóm Trả nợ và khoản gắn nợ. Vì vậy `/thang` và `/menu` cho hai số "đã chi" khác nhau.
- `domain/chitieu/flow.py` (thuần): `kind(entry, debt_group)` trả `thu`, `chi`, `tra_goc` (có `e["no"]`, thuộc nhóm Trả nợ, hoặc ghi chú khớp `classify.is_debt_payment`) hoặc `hoan` (hoàn tiền). Suy từ trường có sẵn, không đổi dữ liệu cũ.
- Thay 27 chỗ bằng các hàm tổng chung (`spending`, `income`, `repaid`); báo cáo thêm dòng "🏦 Trả gốc nợ X (không tính là chi)".
- Hoàn tiền: bỏ "hoàn tiền", "cashback" khỏi từ khóa Thu nhập (`domain/chitieu/categories.py:57-59`); mục hoàn tiền xếp nhóm theo phần còn lại của ghi chú và tính là chi âm của nhóm đó.
- "Để dành thật" của `/tietkiem` không tính `tra_goc` (`services/tietkiem/progress.py:42-54`).
- Test chéo `tests/test_dongtien_nhat_quan.py`: dữ liệu mẫu cố định, mọi màn hình (`/thang`, `/menu`, `/ngansach`, `/dubao`, `/kehoach`, tin gộp, số liệu gửi AI) cho cùng một số "đã chi".
- Chấp nhận: lương 20tr, quẹt thẻ mua tivi 10tr, trả thẻ 10tr, ăn trưa 50k: mọi màn hình báo đã chi 10,05tr, trả gốc 10tr ở dòng riêng; ngân sách tổng 15tr báo 67%, không phải 134%. `hoàn tiền áo 50k` giảm chi Mua sắm 50k, Thu nhập không đổi.
- Rủi ro: PR có tác động lớn nhất. Số "chi" của `/thang` giảm với người có khoản trả nợ. PR nêu rõ điều này.

### PR 0.7: Kế hoạch theo kỳ lương, một con số "mỗi ngày được tiêu" (L) 🔁 Opus
- **Kỳ lương.** Nếu đã khai `/luong <ngày> <số>` thì kỳ chạy từ ngày lương gần nhất tới trước ngày lương kế (`services/kehoach/plan.py:58-66`); chưa khai thì giữ tháng dương lịch.
- **Thu kế hoạch** = max(lương thật đã ghi trong kỳ, lương dự kiến) + các khoản thu khác. Ghi "+100k" không làm mức giảm. Khoản sinh từ đối chiếu có cờ riêng và không tính vào thu kế hoạch.
- **Một nguồn cho "mỗi ngày".** Hàm `kehoach.spendable` là nguồn duy nhất cho tin sau khi ghi chi, màn Hôm nay, tin tối, `/kehoach` và `finance_facts`. Tin ghi chi thôi hiện "hôm nay 35k/324k" (mốc tiết kiệm cũ).
- **Phần dư mặc định để dành**, không cộng vào mức tiêu (`domain/kehoach/plan.py:68-77`); chỉnh được theo tỷ lệ.
- **Ngân sách hằng ngày tính đủ mọi khoản** (`services/phantich/analysis.py:41-43`, `domain/phantich/numbers.py:107-115`); chỉ dự báo mới được bỏ khoản đột biến.
- Chấp nhận: lương về ngày 28/10: mức hằng ngày giữ ổn định cả kỳ (hiện 2,9tr ngày 28/10 rồi 11,7tr ngày 31/10), không tính lương hai lần khi sang 1/11. Ghi "+ hoàn tiền 100k" ngày 3/11 không làm mức rơi từ ~577k xuống 3.571đ. Đối chiếu ghi lệch +535k là thu không đổi mức. Ghi siêu thị 600k và đổ xăng 700k với ngân sách hằng ngày 3tr hiện "1,3tr/3tr".

### PR 0.8: Bỏ mốc cá nhân, số ước có độ tin cậy (M)
- `domain/tietkiem/progress.py:19-23`: bỏ mốc 323.700đ và ngày 04/11/2026 lấy từ sao kê của chủ bot. Mốc của mỗi người = trung bình chi lặt vặt 14 ngày ghi đầu tiên của chính họ. Trước đó hiện "đang đo mốc, còn N ngày". Ngày không có khoản lặt vặt nào không được cộng mốc.
- Gợi ý chuyển tiền dựa vào phần dư thật của kế hoạch (PR 0.7), không dựa vào "đã bớt"; "đã bớt" chỉ để động viên.
- Dự báo dưới 7 ngày ghi hiện "ước rất thô"; dưới 3 ngày không hiện "cả tháng".
- Tổng kết tuần/tháng ghi rõ "N/7 ngày có ghi" và không báo "🔻71%" chỉ vì thiếu ngày ghi.
- Lưu ý: số "đã bớt" của chủ bot sẽ đổi; PR nêu rõ.

### PR 0.9: Đầu tư, lãi/lỗ dòng riêng và bán quỹ (M)
- Lãi/lỗ đã chốt khi bán cổ phiếu, quỹ, vàng ghi thành khoản `dau_tu` có dấu, không vào Thu nhập, không vào mức tiêu (`services/taisan/trade.py:189-194`, `services/taisan/sales.py:18-25`). Lô vàng không ghi giá vốn thì không ghi lãi, hỏi giá vốn.
- `/xoa` trên dòng `dau_tu` từ chối và hướng dẫn cách hoàn giao dịch (hoàn tác theo việc nằm ở PR 2.4).
- Bán quỹ: `contributed` trừ khoản rút để lãi/lỗ và "nên mua" của `/dautu` không nhảy.
- Quỹ dự phòng dưới mốc: `/dautu` ghi "Nên tạm dừng" ở dòng chính, đồng nhất với chia lương.
- Chấp nhận: mua FPT 1000@95, bán 400@120 rồi 600@80: sổ có hai dòng đầu tư (+9.952.000đ và −9.048.000đ), Thu nhập = 0, dòng "Đầu tư +904k". Bán vàng lỗ 2tr ghi −2tr. Bán 30 ccq VMEEF lãi 36k: lãi/lỗ của `/dautu` vẫn −23k, "nên mua" không đổi từ 7,06tr lên 7,51tr.

### PR 0.10: Nhận định, khuyến nghị và cảnh báo (M)
- Khuyến nghị CTCK (`nhandinh/rules.py:82-94`): hiện "3 CTCK: 1 Mua · 1 Giữ · 1 Bán", mục tiêu là trung bình các báo cáo trong 30 ngày kèm ngày mới nhất.
- Chân tin cố định "Thông tin tổng hợp, không phải khuyến nghị đầu tư" cho nhận định tự gửi và "👉 Mua X" của `/dautu`. Nhận định tự gửi chỉ nêu ngành và số liệu, bỏ "mã đáng chú ý" (`services/nhandinh/ai.py:47-82`).
- Cảnh báo VN-Index theo chiều (`canhbao/rules.py:106-118`): đảo chiều từ 1,5% so với mốc báo gần nhất thì báo.
- Tin theo từ khóa (`canhbao/checks.py:91`): tin vượt 5 gom thành "+N tin khác", chỉ đánh dấu tin đã thật sự gửi.
- Vàng: nguồn lỗi và chưa có giá lưu thì dùng giá gần nhất kèm ngày, không tính vàng bằng 0 (`services/taisan/valuation.py:280`).
- Chấp nhận: AAA có HSC Mua, VCI Giữ, SSI Bán không còn dòng "MUA". VN-Index −1,6% báo, hồi +1,6% cũng báo. Bản nhận định tự gửi không chứa mã cổ phiếu và có chân tin.

### PR 0.11: Lệnh `/kiemtra` (chỉ đọc) (S)
Các lỗi trên đã chạy từ trước nên dữ liệu thật có thể đã bị ảnh hưởng. `/kiemtra` không sửa gì, chỉ liệt kê nghi vấn phát hiện được từ dữ liệu có sẵn:
- khoản có ngày lùi hơn 90 ngày so với khoản đầu tiên (nghi bị đẩy về năm trước);
- sổ tiết kiệm có ngày gửi trùng một ngày đã đối chiếu (nghi bị đặt lại);
- "Quỹ chờ" lớn hơn tổng tiền đã ghi nhận để vào;
- mục nào không phát hiện được thì ghi cách tự kiểm.
Có thể kéo PR này lên ngay sau 0.2 nếu bạn nghi dữ liệu đã bẩn.

## 5. Truy vết lỗi → PR

| Báo cáo BA | Lỗi | PR |
|---|---|---|
| Chi tiêu | P1 thẻ tín dụng cộng hai lần | 0.6 |
| | P2 học nhóm lan | 0.2 |
| | P3 ngày tương lai về năm trước | 0.2 |
| | P4 ngân sách hằng ngày bỏ khoản lớn | 0.7 |
| | P6 dự báo ít dữ liệu | 0.8 |
| | P7 "đã bớt", mốc cá nhân | 0.8 |
| | P8 trả thẻ là "để dành thật" | 0.6 |
| | P9 hoàn tiền | 0.6 |
| | P10 giờ quanh nửa đêm | 0.2 |
| Tài sản | P1 nợ có lãi | 0.5 |
| | P2 đối chiếu đặt lại ngày gửi | 0.1 |
| | P3 cho vay ghi đè | 0.1 |
| | P4 tiền nhà nhân đôi | 0.3 |
| | P5 chi tiền mặt/trả thẻ, lệch dương | 0.1, 0.6 |
| | P6 đáo hạn, tất toán sớm | 0.4 |
| | P7 trả gốc nợ tính là chi | 0.6 |
| Đầu tư | P1 quỹ chờ tự sinh tiền | 0.3 |
| | P2 lãi vào thu, lỗ mất | 0.9 |
| | P3, P4 nhãn CTCK, miễn trừ | 0.10 |
| | P5 lời khuyên ngược nhau | 0.9 (dưới mốc thì tạm dừng) |
| | P6 VN-Index đảo chiều | 0.10 |
| | P7 vàng = 0 khi nguồn lỗi | 0.10 |
| | P8 tin từ khóa bị mất | 0.10 |
| | P9 bán quỹ làm hỏng VA | 0.9 |
| Xuyên suốt | #1, #2, #3 kỳ lương, thu nhỏ, hai con số | 0.7 |
| | #4 mốc tiết kiệm | 0.8 |
| | #5 vay mới | 0.3 |
| | #6 `/xoa` xóa sai việc | PR 2.4 (hoàn tác theo việc), 0.9 |
| | #7 rút dự phòng | 0.3 |
| | #8 lãi vào thu | 0.9 |
| | #9 quên ghi làm méo số | 0.8 |

**Hoãn có lý do** (ghi rõ để khỏi thất lạc):
- Khoản định kỳ bị trừ hai lần khi đổi ghi chú (Chi tiêu P5): cần khái niệm khoản định kỳ, làm sau.
- `/hoi` bỏ sót cách viết khác khi AI bận (P11): phụ thuộc giai đoạn 3.
- Chia hóa đơn, "2 ly x 45k", sổ phải thu (P9 phần còn lại): tính năng mới, không phải lỗi số.
- Ghi đè cả cục JSON khi chạy song song (Xuyên suốt #10): cần thiết kế ghi có điều kiện; rủi ro đã biết, chưa có ca thật.
- Ví vàng dùng chung với bot bản tin (#11), thống nhất một nguồn giá vàng (Đầu tư P7 phần còn lại), onboarding (#12), tin tối giãn tần suất (#13), xuất/xóa toàn bộ dữ liệu (#15), trần phân bổ cổ phiếu, phí theo công ty chứng khoán, các mục mức Thấp còn lại.

## 6. Rủi ro

| Rủi ro | Cách giảm |
|---|---|
| PR 0.6 đổi số "chi" ở nhiều màn hình cùng lúc | Test chéo; so snapshot; PR nêu rõ số nào đổi; tách đôi nếu quá lớn |
| Thẻ hỏi lại nhiều hơn làm phiền (ngày mơ hồ, vay mới, quỹ chờ) | Chỉ hỏi đúng ca mơ hồ; ca rõ ràng vẫn ghi ngay |
| Dữ liệu cũ đã sai | `/kiemtra` chỉ đọc, người dùng tự sửa; không có chuyển đổi tự động |
| Công thức nợ có lãi lệch với app ngân hàng | Ghi rõ phương pháp trong tin; lần đối chiếu nợ hằng tháng sửa số thật |
| Mốc, kỳ lương làm thay đổi con số quen thuộc | Nêu trong PR; chủ bot xem `/menu` trước và sau |

## 7. Ước tính

11 PR, khoảng 2,6 triệu token mới và khoảng 120 triệu token đọc cache (ước tính thô theo mốc 0,22 triệu token mới mỗi PR, PR 0.6 và 0.7 nặng gấp rưỡi), khoảng 3 phiên 5 giờ, chưa tính các PR của giai đoạn 1 và 2. Tổng cả kế hoạch tăng từ khoảng 6,5 triệu lên khoảng 9 triệu token mới.
