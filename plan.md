# Kế hoạch refactor: Repository + Service Layer

Nhánh: `claude/refactor-repository` (tách từ `main`). Mỗi bước là một PR nhỏ, hành vi không đổi.

## 1. Vì sao

Đo trên `main` (13.000 dòng, 30 file phẳng):

| Vấn đề | Số liệu |
|---|---|
| Gọi Redis trực tiếp | 18 file, ~170 chỗ `kho.get/put/command`, ~35 khóa |
| Khóa viết cứng, lặp | `"vivang"` ở `lenh.py`, `lich.py` (trong khi `taisan.py` có `K_GOLD`); `"chitieu:dautu"` viết lại ở `taisan.py:251` |
| Hình dạng dữ liệu chỉ nằm trong comment | mỗi nơi tự `kho.get(K, {}) or {}` + `setdefault` |
| Nghiệp vụ + lưu trữ + HTML trong một hàm | `taisan.sell_gold`, `close_saving`, `sell_fund`, `collect_loan` đều vừa tính, vừa ghi, vừa trả chuỗi HTML |
| Import vòng, né bằng hàm nạp muộn | 9 hàm `ct.taisan()`, `ct.dautu()`… trong `sochitieu.py` |
| Ghi đè cả cục JSON | `chitieu:taisan` (items + dem + lailo) bị webhook và cron tick cùng đọc rồi ghi cả cục |

## 2. Đích đến

Chia **theo lớp trước**; trong mỗi lớp có **thư mục theo chức năng**; mỗi file chức năng nằm đúng một lớp.
Gốc repo chỉ còn `api/` (Vercel bắt buộc), tài liệu, cấu hình và các lớp.

```
interface/<chức năng>/        tầng vào: định tuyến tin nhắn, lệnh /…, nút bấm, cron; gọi services, nhờ presentation dựng tin
services/<chức năng>/         một hàm cho mỗi việc người dùng làm; nối repositories + domain; trả kết quả có cấu trúc
presentation/<chức năng>/     kết quả → HTML Telegram + bàn phím; không logic nghiệp vụ, không I/O
domain/<chức năng>/           dataclass + quy tắc thuần + kiểu kết quả của service (không I/O, không HTML)
repositories/<chức năng>/     mỗi aggregate một repo, bọc infrastructure/kho
infrastructure/               cổng ra ngoài: kho (Redis), telegram, AI (Gemini/OpenRouter), nguồn giá/tin/thời tiết
```

Chức năng (tên thư mục trong mỗi lớp): `chitieu` (sổ thu chi, ngân sách, nhóm), `phantich` (hỏi đáp, báo cáo chi tiêu),
`taisan`, `vang`, `dautu`, `tietkiem`, `duphong`, `no`, `luong`, `kehoach`, `doichieu`, `troly` (AI hiểu câu, thẻ xác nhận),
`anh` (đọc ảnh), `menu`, `bantin` (bot bản tin: bản tin sáng, giá, chứng khoán, nhận định, lịch). Thư mục chỉ tạo khi có file đầu tiên.

Phụ thuộc chỉ đi một chiều (test kiến trúc canh, xem mục 3):

| Lớp | Được import |
|---|---|
| `domain` | thư viện chuẩn, `domain` |
| `infrastructure` | thư viện chuẩn, `infrastructure` |
| `repositories` | `domain`, `infrastructure`, `repositories` |
| `services` | `domain`, `repositories`, `infrastructure`, `services` |
| `presentation` | `domain`, `presentation` (kiểu kết quả của service nằm ở `domain`) |
| `interface` | mọi lớp dưới, `interface` |
| `api/` | `interface` |

Hết import vòng thì bỏ 9 hàm nạp muộn (`ct.taisan()`…).

Pattern: Layered Architecture, Repository, Domain Model, Service Layer (Use Case), Presenter. Chuyển đổi theo Strangler Fig,
không viết lại một lượt.

Tên lớp bằng tiếng Anh; tên chức năng và file trong lớp theo nghĩa nghiệp vụ (`gold`, `assets`, `ledger`…).

### Mỗi module cũ đi đâu

Hầu hết module cũ trộn nhiều lớp (ví dụ `sochitieu.py` vừa là router, vừa là sổ, vừa là hiển thị), nên không chuyển nguyên file:
tách theo lớp rồi đặt từng mảnh vào `<lớp>/<chức năng>/`; file cũ xóa khi hết nội dung.

| Module hiện tại | Tách thành |
|---|---|
| `kho.py`, `tg.py` | `infrastructure/kho.py`, `infrastructure/telegram.py` |
| khung gọi AI trong `sochitieu.py` (`ai_chat`, khóa, thử lần lượt nhà cung cấp) | `infrastructure/ai.py` |
| `chungkhoan.py`, `thoitiet.py`, `tintuc.py` | `infrastructure/` (nguồn giá, thời tiết, tin) |
| `amlich.py` | `domain/bantin/amlich.py` (tính lịch âm thuần) |
| `sochitieu.py` | `domain/chitieu` (đọc tiền/ngày/dòng, luật xếp nhóm), `services/chitieu` (ghi, xóa, học nhóm, ngân sách), `presentation/chitieu` (dòng khoản, định dạng số), `interface/chitieu` (`respond`, lệnh, nút) |
| `phantich.py` | `domain/phantich` (bộ lọc, tính), `services/phantich`, `presentation/phantich`, `interface/phantich` |
| `taisan.py` | `domain/taisan` (định giá, lãi sổ…), `services/taisan` (bán, tất toán, chuyển), `presentation/taisan` (bảng, tổng quan), `interface/taisan` (`/taisan`, nút `ts:`); phần vàng sang `*/vang` |
| `dautu.py` | `domain/dautu` (Value Averaging, phiên khớp, trạng thái lệnh), `services/dautu`, `presentation/dautu`, `interface/dautu` |
| `sono.py`, `duphong.py`, `tietkiem.py`, `doichieu.py`, `kehoach.py` | cùng cách, mỗi chức năng một bộ bốn lớp |
| `troly.py` | `services/troly` (hiểu câu thành việc, làm việc, thẻ gộp), `presentation/troly` (`describe`, thẻ), `interface/troly` (nút `y:`, hội thoại dở) |
| `docanh.py` | `infrastructure/ai.py` (đọc ảnh), `services/anh`, `interface/anh` |
| `menu.py`, `thongbao.py` | `presentation/menu`, `interface/menu`; thông báo sáng/tối: `services` + `presentation` |
| `lich.py`, `lenh.py`, `bantin.py`, `canhbao.py`, `nhandinh.py` | `services/bantin`, `presentation/bantin`, `interface/bantin` (lịch tick, lệnh bot bản tin) |
| `danhgia.py`, `danhgia_cau.py` | `tools/danhgia/` (công cụ đo, không phải lớp của app) |

Workflow `bantin.yml` đã chạy `python3 -m interface.bantin.bulletin`; `canhbao.py` còn chạy trực tiếp tới khi chuyển xong.

## 3. Luật bất di bất dịch

1. **Không đổi schema Redis.** Repo đọc/ghi đúng JSON đang có (`from_dict/to_dict`). Dữ liệu thật đang chạy, không migrate.
2. **Chỉ thư viện chuẩn** (`dataclasses`, `typing`): giữ zero-dependency trên Vercel.
3. **Hành vi không đổi.** Mỗi PR: toàn bộ test xanh; PR nào đụng `troly`/`sochitieu`/định tuyến thì chạy lại bộ đo 113 câu trên production (`do.sh`), điểm không được tụt dưới lần đo trước (98–100).
4. **`kho.memo` giữ nguyên** ở tầng dưới repo. Test giả Redis ở `kho.send` giữ nguyên (không cần repo giả).
5. **Mỗi PR chỉ một mối quan tâm.** Không gộp "đổi chỗ" với "sửa hành vi".
6. **Chạy được ở cả 3 nơi vào code:** Vercel (`api/*.py`), GitHub Actions (`bantin.py` chạy dòng lệnh), test. Gói mới phải import được từ cả ba (`sys.path` gốc repo).
7. Lỗi nào phát hiện trong lúc refactor: ghi lại, sửa ở PR riêng, không lẫn vào bước đang làm.

## 4. Các bước

Mỗi bước: PR → CI `kiemthu` xanh → merge → chờ deploy → mở trang tình trạng bot kiểm tra → (nếu cần) chạy bộ đo.

### Bước 0: nền (xong khi tạo nhánh)
- Tách nhánh từ `main`, viết `plan.md`.
- Mốc để so sánh: toàn bộ test xanh, bộ đo 113 câu: 98–100.

### Bước 1: `keys.py` + `Store`
Làm: 
- `repositories/keys.py`: mọi khóa Redis (cả bot chi tiêu lẫn bot bản tin: `theodoi`, `nhac`, `vang_lichsu`, `doan:*`, `canhbao`, `bangdien`, `tukhoa`, `cotuc_daxem`, `tick_cuoi`, `khoa:tick`, `xong:*`…), mỗi khóa một dòng kèm comment hình dạng giá trị. Khóa có tham số là hàm (`month(ym)`, `reminder_debt(id, ym, stage)`).
- `repositories/store.py`: `Store` mỏng bọc `kho` (`get`, `put`, `put_new`, `hash_all`, `hash_set`, `incr`…), là chỗ duy nhất `repositories/` gọi `kho`.
- Thay mọi chuỗi khóa viết cứng và hằng `K_*` rải rác bằng khóa trong `keys.py`.

Xong khi:
- `grep` không còn chuỗi khóa Redis viết cứng ngoài `keys.py`.
- Có test chặn tái phát (quét mã nguồn tìm `kho.(get|put|command)("literal"`).
- Test xanh; không đổi hành vi; không cần chạy bộ đo (không đụng logic).

### Bước 2: `GoldRepo` (bài thử)
Ví vàng được 3 file dùng chung (`lenh`, `lich` ×2, `taisan` ×6), cả hai bot.
- `domain/gold.py`: `GoldLot` (loai, luong, gia, ngay), `sell_fifo(lots, chi, kind)` thuần → (lô còn lại, vốn).
- `repositories/gold.py`: repo là module hàm (không dùng lớp): `load()`, `save(lots)`, `add(lot)`, `remove_at(i)`, `clear()`.
  Thứ tự danh sách giữ nguyên vì là mã dòng `v0`, `v1`… ở màn hình tài sản.
- Thay các chỗ `kho.get("vivang")` / `kho.put("vivang")`.

Xong khi: không file nào ngoài repo đọc/ghi ví vàng (test `test_vi_vang_chi_qua_repository` chặn); test bán vàng/mua vàng/hiển thị bảng vàng xanh; thêm test thuần cho `sell_fifo`; các giá trị ghi vào `vivang` trong toàn bộ test giống `main` từng lần.

### Bước 3: `AssetRepo` (+ lương, cấu hình quỹ)
`taisan.load/save` đã gần là repository. `ts.load()/ts.save()` được 8 module gọi ở ~60 chỗ, nên bước này giữ nguyên cửa vào đó
và cho chúng ủy quyền cho repo; kiểu dữ liệu riêng cho từng loại tài sản (`AssetItem`…) làm cùng bước 5, khi tách `taisan.py`.
- `repositories/assets.py`: `load()/save()` (cục `{"items", "dem", "lailo"}` giữ dạng dict), lịch sử tài sản ròng
  (`save_snapshot`, `history`), giá đã lấy (`price_cache`, `save_price_cache`).
- `domain/salary.py` + `repositories/salary.py`: `Salary(day, amount)`, `load/save/clear` (thay 4 chỗ đọc `keys.SALARY`).
- `repositories/fund.py`: `load/save` cấu hình quỹ (taisan và dautu cùng đọc); NAV và thông tin quỹ thêm ở bước 6.
- `taisan.py`, `dautu.py`, `kehoach.py`, `sono.py` không còn gọi kho với các khóa này.

Xong khi: không file nào ngoài repo dùng `keys.ASSETS/ASSET_HISTORY/SALARY/FUND/price_cache` (test chặn); toàn bộ lệnh ghi Redis
trong test giống `main` từng lệnh. Trong `taisan.py` còn gọi kho: `INCR` bộ đếm sổ chi (bước 4), cờ nhắc đáo hạn (bước 6),
và `kho.ready()` (kiểm tra cấu hình, không phải truy cập dữ liệu, được phép ở mọi nơi).

### Bước 4: `LedgerRepo` (sổ chi tiêu)
Dùng nhiều nhất (`sochitieu.load/save/HSET/HGET/HDEL`, và 8 chỗ xin mã khoản mới ở `docanh`, `doichieu`, `sono`, `taisan`).
- `repositories/ledger.py`: `load(ym)`, `save(entry)`, `find(ym, id)`, `remove(ym, id)`, `next_id()`, `last_id()`.
- Khoản thu/chi giữ dạng dict (như mục tài sản): kiểu `Entry` riêng làm cùng bước 5–6, vì `e["nhom"]`, `e["tien"]`… có ở hầu
  hết module. `ct.load/save/find/delete` giữ làm cửa vào, ủy quyền cho repo.

Xong khi: không file nào ngoài repo dùng `keys.COUNTER`, `keys.ledger_month` hay lệnh hash `HSET/HGET/HDEL` cho sổ (test chặn);
toàn bộ lệnh ghi Redis trong test giống `main` từng lệnh.

### Bước 5: dựng khung lớp và luật phụ thuộc, chuyển `infrastructure`
- `tests/test_kientruc.py`: quét import bằng AST, báo đỏ khi một file trong lớp import sai chiều (bảng mục 2) hoặc lớp mới
  import module cũ còn ở gốc; số file ở gốc tối đa (`ROOT_PY_MAX`) chỉ được giảm qua từng bước (ratchet); import thử mọi module, cả `api/*.py`.
- `infrastructure/`: `kho.py`, `telegram.py` (hai module chỉ dùng thư viện chuẩn, chuyển nguyên). Khung gọi AI (`ai_chat`…) và nguồn
  giá/tin/thời tiết đang lẫn với logic trong `sochitieu.py`, `chungkhoan.py`…: tách cùng chức năng sở hữu chúng ở bước 6…, không chuyển nguyên file.
- Repo và domain đã có xếp vào thư mục chức năng: `repositories/{vang,taisan,chitieu,luong,dautu}/`, `domain/{vang,luong}/`.
  `repositories/keys.py` và `repositories/store.py` ở gốc của lớp (dùng chung mọi chức năng).
- Viết lại import bằng script (31 file).

Xong khi: `kho.py`, `tg.py` không còn ở gốc; test kiến trúc xanh; test và lệnh ghi Redis giống `main`.

### Bước 6…: từng chức năng, tách theo lớp rồi đặt vào `<lớp>/<chức năng>/`
Thứ tự từ nhỏ tới lớn, mỗi chức năng một PR (nếu quá ~500 dòng đổi thì tách tiếp): `duphong` → `tietkiem` → `doichieu` → `no` →
`kehoach` → `vang`+`dautu` → `taisan` → `chitieu`+`phantich` → `anh`+`menu`+thông báo → `troly` → `bantin`.

Mỗi PR chức năng:
- Tách module cũ thành `domain/`, `services/`, `presentation/`, `interface/` của chức năng đó; xóa file cũ.
- Service trả kết quả có cấu trúc (kiểu nằm ở `domain/<chức năng>/`), presentation dựng HTML từ kết quả; không hàm service nào trả HTML.
- Gỡ các hàm nạp muộn liên quan; chuyển repo còn lại của chức năng (`SettingsRepo`, `ConversationRepo`, NAV quỹ, `CacheRepo`…).
- Kiểu dữ liệu riêng (`Entry`, `AssetItem`…) thêm khi tách tới chức năng cần nó, thay dần dict.
- File mới còn tạm import module cũ ở gốc (vì module cũ đó chưa được chuyển) thì khai báo trong `LEGACY_IMPORTS` của
  `tests/test_kientruc.py`; danh sách phải khớp chính xác với thực tế nên chỉ rút ngắn được: chuyển xong module cũ nào thì
  phải gỡ nó khỏi danh sách.
- Kiểm chứng tin nhắn không đổi: chụp trước/sau (trên `main` và nhánh) chữ + nút của mọi màn hình và lệnh của chức năng, cả các
  màn hình khác có đọc dữ liệu của chức năng (kế hoạch, menu, khám sức khỏe, tổng kết…), rồi so từng chữ cùng stderr.

Xong khi: file cũ không còn; test kiến trúc xanh; ratchet giảm; toàn bộ lệnh ghi Redis trong test giống `main`; tin nhắn bot gửi
không đổi (test hiện có, so thêm các chuỗi hiển thị chính); chạy bộ đo khi đụng `troly`/định tuyến.

### Bước cuối: dọn
- Gốc chỉ còn `api/`, tài liệu, cấu hình, các lớp; workflow đổi sang `python -m`; xóa hàm nạp muộn; ratchet về 0.
- (Tùy chọn) số phiên bản cho `assets` repo để webhook và tick không ghi đè nhau (Upstash REST hỗ trợ `EVAL`), có test mô phỏng.

## 4b. Tiến độ

| Bước | Trạng thái |
|---|---|
| 0 Nền, `plan.md` | xong, đã deploy ([#52](https://github.com/hoang-developer/ban-tin-sang/pull/52)) |
| 1 `keys.py` + `Store` | xong, đã deploy ([#52](https://github.com/hoang-developer/ban-tin-sang/pull/52)) |
| 2 `GoldRepo` | xong, đã deploy ([#53](https://github.com/hoang-developer/ban-tin-sang/pull/53)) |
| 3 `AssetRepo`, `SalaryRepo`, `FundRepo` | xong, đã deploy ([#54](https://github.com/hoang-developer/ban-tin-sang/pull/54)) |
| 4 `LedgerRepo` | xong, đã deploy ([#55](https://github.com/hoang-developer/ban-tin-sang/pull/55)) |
| 5 Khung lớp, luật phụ thuộc, `infrastructure` | xong, đã deploy ([#56](https://github.com/hoang-developer/ban-tin-sang/pull/56)) |
| 6.1 `duphong` (quỹ dự phòng) | xong, đã deploy ([#57](https://github.com/hoang-developer/ban-tin-sang/pull/57)) |
| 6.2 `tietkiem` (tiết kiệm từ khi dùng bot) | xong, đã deploy ([#58](https://github.com/hoang-developer/ban-tin-sang/pull/58)) |
| 6.3 `doichieu` (đối chiếu tài sản tháng) | xong, đã deploy ([#59](https://github.com/hoang-developer/ban-tin-sang/pull/59)); tick sau deploy chạy bình thường |
| 6.4 `no` (sổ nợ) | xong, đã deploy ([#60](https://github.com/hoang-developer/ban-tin-sang/pull/60)); tick sau deploy chạy bình thường |
| 6.5 `kehoach` (kế hoạch chia lương, lộ trình) | xong, đã deploy (#61) |
| 6.6a `dautu`: dữ liệu Fmarket (`infrastructure/fmarket`, `repositories/dautu/market`), lịch phiên (`domain/dautu/calendar`), phiên kế tiếp (`services/dautu/market`) | xong, đã deploy (#62) |
| 6.6b `dautu`: quy tắc VA (`domain/dautu/plan`), tình trạng kỳ + chốt kỳ (`services/dautu/status`) | xong, đã deploy (#63) |
| 6.6c `dautu`: lệnh, khớp lệnh, hoán đổi (`services/dautu/{orders,switch}`), định dạng số dùng chung (`domain/common/format`, `domain/dautu/text`) | xong, chờ deploy (câu báo còn nằm trong service, tách sang presentation ở bước sau) |
| 6.6d dọn lớp `interface`: `interface/common.py` dùng chung (chặn khi chưa nối kho, nhận biết tin, bỏ nút, cắt thông báo), hàm nội bộ đổi tên riêng tư, bỏ import thừa | xong, đã deploy (#65) |
| 6.6e `dautu`: màn hình (`presentation/dautu/view`): màn chính, nhắc hạn, lịch sử lệnh, biểu đồ, nút | xong, đã deploy (#66) |
| 6.6f `dautu`: lệnh và nút (`interface/dautu/fund`), việc phục vụ chỗ khác (`services/dautu/reports`), xóa `dautu.py` | xong, đã deploy (#67): **`dautu` xong đủ 4 lớp** (câu báo của `orders`, `switch`, `reports` còn trong service) |
| 6.7a `taisan`: nguồn giá (`infrastructure/{clock,crypto,vietcombank,fmarket}`, `services/taisan/prices`, `domain/taisan/kinds`) | xong, đã deploy (#68) |
| 6.7b `taisan`: định giá và tài khoản chính (`services/taisan/{valuation,accounts}`, `domain/taisan/{rules,text}`, `domain/chitieu/kinds`, `ledger.between`) | xong, đã deploy (#69) |
| 6.7c `taisan`: bán, rút, thu về (`services/taisan/sales`; `find_item`, `removable` về `domain/taisan/rules`, `gain_line` về `domain/taisan/text`) | xong, đã deploy (#70) |
| 6.7d `taisan`: mua bán cổ phiếu, khai báo, nhắc lương/đáo hạn, dòng tiền (`domain/taisan/trade`, `services/taisan/{trade,declare,flows,reminders}`) | xong, chờ deploy |
| 6.7e `taisan`: màn hình (`presentation/taisan/view`), khám sức khỏe (`services/taisan/health`), lệnh và nút (`interface/taisan/assets`), xóa `taisan.py`, services/presentation không còn import module cũ `taisan` | xong, chờ deploy: **`taisan` xong đủ 4 lớp** |
| 6.8a `chitieu`: máy khách AI (`infrastructure/ai`), xếp nhóm và đọc dòng chi tiêu (`domain/chitieu/{categories,classify,parse}`), cấu hình nhóm (`repositories/chitieu/groups`) | xong, đã deploy (#72) |
| 6.8b `chitieu`: ghi sổ, học nhóm, xếp lại khoản ở Khác, AI xếp nhóm và tình trạng AI (`domain/chitieu/learn`, `services/chitieu/{ledger,ai_sort}`, cấu hình nhóm nhớ một lượt ở `repositories/chitieu/groups`) | xong, đã deploy (#73) |
| 6.8c `chitieu`: báo cáo, kỳ báo cáo, ngân sách, tin báo khoản vừa ghi, nút chọn nhóm (`domain/chitieu/{period,income,refs,text}`, `services/chitieu/{budget,report}`, `presentation/chitieu/view`) | xong, chờ deploy |
| 6.8d `chitieu`: lệnh /baocao /thang /lichsu /xoa /ngansach /nhom /chuaxep /xuat (`interface/chitieu/{commands,context}`, `domain/chitieu/labels`) | xong, chờ deploy |
| 6.8e `chitieu`: định tuyến bot (bảng lệnh, trả lời tin nhắn, nút bấm) ở `interface/chitieu/{bot,features}`, `sochitieu.py` chỉ còn tên cũ dùng tạm (174 dòng) | xong, chờ deploy |
| 6.9 `phantich`: số liệu và câu hỏi ở `domain/phantich`, đọc sổ ở `services/phantich` + `repositories/chitieu/analysis`, màn hình ở `presentation/phantich`, lệnh ở `interface/phantich`, vẽ biểu đồ ở `infrastructure/quickchart` (xóa `phantich.py`, file gốc còn 16) | xong, chờ deploy |
| 6.10 `amlich` vào `domain/amlich`; `bantin.py` tách: thời tiết/vàng/chỉ số/RSS ở `infrastructure/{openmeteo,marketdata,web}`, gợi ý ở `domain/bantin`, lấy số liệu ở `services/bantin/data`, chữ ở `presentation/bantin/view`, ghép và gửi ở `interface/bantin/bulletin` (workflow chạy `python3 -m interface.bantin.bulletin`; file gốc còn 14) | xong, chờ deploy |
| 6.11 `canhbao.py` tách: luật báo ở `domain/canhbao/rules`, các bước kiểm tra ở `services/canhbao/checks`, chữ ở `presentation/canhbao/view`, chạy và gửi ở `interface/canhbao/runner` (workflow chạy `python3 -m interface.canhbao.runner`; file gốc còn 13) | xong, chờ deploy |
| 6.12 `chungkhoan.py` tách (`infrastructure/stockfeeds`, `domain/chungkhoan`, `services/chungkhoan`, `presentation/chungkhoan`, `interface/chungkhoan`); 6.13 `tintuc.py` và `thoitiet.py` tách theo cùng khuôn (`*/tintuc`, `*/thoitiet`); file gốc còn 10 | xong, chờ deploy |
| 6.14 `thongbao.py` → `interface/thongbao/digest.py` (gộp tin sáng/tối, thuộc lớp giao diện); `danhgia.py`, `danhgia_cau.py` → `interface/danhgia/{benchmark,questions}.py` (công cụ đo bot hiểu câu); file gốc còn 7 | xong, chờ deploy |
| 6.15 `menu.py` tách: chữ và nút ở `presentation/menu/view`, màn hình và nút bấm ở `interface/menu/screens` (đọc từ nhiều chức năng nên ở lớp giao diện); file gốc còn 6 | xong, chờ deploy |
| 6.16 `docanh.py` tách: chuẩn hóa giao dịch ở `domain/docanh`, trạng thái ảnh ở `repositories/docanh`, đọc ảnh bằng AI và ghi sổ ở `services/docanh`, danh sách chọn ở `presentation/docanh`, luồng ảnh và nút bấm ở `interface/docanh`, tải file ở `infrastructure/telegram`; file gốc còn 5 | xong, chờ deploy |
| 6.17 `nhandinh.py` tách: ngành, khuyến nghị, tin gộp ở `domain/nhandinh`, kho tạm và công tắc ở `repositories/nhandinh`, lấy dữ liệu và AI tổng hợp ở `services/nhandinh`, chữ ở `presentation/nhandinh`, lệnh và nút ở `interface/nhandinh`; file gốc còn 4 (troly, lenh, lich, sochitieu) | xong, chờ deploy |
| 6.18 `lich.py` → `interface/lich/jobs.py` (việc theo giờ là điểm vào của lớp giao diện); khung giờ, ngày giao dịch, từ khóa cổ tức ở `domain/lich`, đánh dấu việc đã làm ở `repositories/lich`; chữ các tin tối/bảng điện còn trong jobs.py (hoãn, ghi ở mục dọn dẹp); file gốc còn 3 | xong, chờ deploy |
| 6.19 `lenh.py` → `interface/lenh/bot.py`; giới hạn, mẫu số tiền/thời gian, đơn vị vàng, đổi tiền ra chữ ở `domain/lenh`, câu đoán xanh/đỏ và mức giá báo ở `presentation/lenh`; giá trị nhập ví vàng dùng chung cho `services/taisan/declare`; file gốc còn 2 (troly, sochitieu) | xong, chờ deploy |
| 6.20 `troly.py` → `interface/troly/assistant.py`; khuôn việc (`F`), chữ báo hiệu, mẫu câu trả lời ngắn ở `domain/troly/spec`, ví dụ và menu ➕ ở `presentation/troly`; JOBS, AI hiểu câu, trạng thái hội thoại, thẻ xác nhận còn trong assistant.py (tách tiếp ở mục dọn dẹp); file gốc còn 1 (sochitieu) | xong, chờ deploy |
| 7.1 dọn `sochitieu`, giai đoạn A: `presentation/*` và `services/*` không còn import `sochitieu` (nút ⬅️ lấy ở `presentation/chitieu/view`, sổ ở `repositories/chitieu`, nhóm chi ở `services/chitieu/groups` mới); `LEGACY_IMPORTS` bớt 12 mục | xong, chờ deploy |
| 7.2 dọn `sochitieu`, giai đoạn B: các file `interface/*` và `api/chitieu` không còn import `sochitieu` (dùng `interface/chitieu/{context,bot,commands,features}` và các module đúng lớp); `token`, `owner_chats`, `find` chuyển vào `interface/chitieu/context`; `LEGACY_IMPORTS` về rỗng | xong, chờ deploy |
| 6.8… dọn `sochitieu.py` khi các module còn lại (`troly`, `menu`, `phantich`, `docanh`...) bỏ `ct.`; rồi `phantich`, `troly`, `menu`, `docanh`, `thongbao`, `lich`, bot bản tin | chưa |
| Cuối: dọn | chưa |

Bước 1–4 mới làm xong tầng lưu trữ (repo); các repo ở gốc `repositories/` và `domain/` sẽ xếp vào thư mục chức năng ở bước 5.

## 4c. Lỗi phát hiện trong lúc refactor (sửa ở PR riêng, không lẫn vào bước đang làm)

| Lỗi | Phát hiện ở | Trạng thái |
|---|---|---|
| Đọc câu khai báo nợ: "ngày 5**,** lãi 12%" (có dấu phẩy sau số ngày) không nhận là hạn trả và còn dính vào tên khoản nợ. Mẫu `ngay` chặn ký tự `,` phía sau để khỏi nhầm số thập phân (`ngày 5,5`), nên chặn luôn dấu phẩy ngăn mệnh đề. Có sẵn trên `main`. | `domain/no/debt.py` (`PATTERNS`) | chưa sửa |

## 5. Chưa làm

- Không viết lại một lượt; không DDD đầy đủ; không interface/port trừu tượng khi chỉ có một nơi lưu trữ (Redis).
- Không đổi schema Redis, không đổi nội dung tin nhắn bot gửi.

## 6. Rủi ro và cách giữ

| Rủi ro | Giữ bằng |
|---|---|
| Đổi tên khóa nhầm, mất dữ liệu | Khóa chép nguyên chuỗi cũ; test so khóa với danh sách chốt từ `main` |
| Gói mới không vào bundle Vercel / Actions | Kiểm tra trang tình trạng bot sau mỗi deploy; bước 1 deploy riêng để phát hiện sớm |
| Hành vi lệch khi gom hàm | Test hiện có (hơn 80 test) + bộ đo 113 câu + test mới cho phần thuần |
| PR quá lớn | Mỗi bước tách tiếp nếu quá ~500 dòng đổi |
| Hết lượt Gemini miễn phí khi chạy bộ đo (80 lượt/ngày) | Chỉ chạy khi đụng `troly`/định tuyến; gom nhiều thay đổi trước khi đo |
| Import sót sau khi chuyển file | Script viết lại import + test import thử mọi module (cả `api/*.py`) + test kiến trúc |
| Workflow GitHub chạy file ở gốc | Đổi workflow cùng PR chuyển file; kiểm tra bằng chạy thử workflow |
| Tách module làm đổi chữ hiển thị | Test hiện có phủ nhiều chuỗi; thêm test so chuỗi cho các màn hình chính trước khi tách |

Hoàn tác: mỗi bước là một PR riêng, `git revert` được.

## 7. Số đo hoàn thành

| Chỉ số | Lúc đầu | Hiện tại | Đích |
|---|---|---|---|
| File `.py` ở gốc repo (không tính `api/`) | 26 | 17 | 0 |
| File gọi dữ liệu qua `kho.*` trực tiếp (số chỗ gọi) | 18 (~170) | 11 (116, đếm lại; lớp `interface` chỉ còn gọi qua `interface/common.py`) | 1 (`repositories/store.py`) |
| Chức năng đã tách vào đủ các lớp | 0 | 7 (`duphong`, `tietkiem`, `doichieu`, `no`, `kehoach`, `dautu`, `taisan`) | mọi chức năng ở bảng "module cũ đi đâu" |
| Chuỗi khóa Redis viết cứng ngoài `keys.py` | ~20 | 0 | 0 |
| Hàm nạp muộn né import vòng | 9 | 9 | 0 |
| Hàm nghiệp vụ trả HTML | nhiều | nhiều | 0 |
| Vi phạm chiều phụ thuộc giữa các lớp (test kiến trúc) | chưa đo | 0 | 0 |
| Bộ đo 113 câu | 98–100 | chưa đo lại | ≥ 98 |
