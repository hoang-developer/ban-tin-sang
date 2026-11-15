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

Workflow GitHub chạy thẳng `python3 bantin.py` và `python3 canhbao.py`: đổi sang `python3 -m interface.bantin.…` khi chuyển xong.

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
| 6.2 `tietkiem` (tiết kiệm từ khi dùng bot) | đang làm |
| 6.3… các chức năng còn lại | chưa |
| Cuối: dọn | chưa |

Bước 1–4 mới làm xong tầng lưu trữ (repo); các repo ở gốc `repositories/` và `domain/` sẽ xếp vào thư mục chức năng ở bước 5.

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
| File `.py` ở gốc repo (không tính `api/`) | 26 | 22 | 0 |
| File gọi dữ liệu qua `kho.*` trực tiếp (số chỗ gọi) | 18 (~170) | 16 (137) | 1 (`repositories/store.py`) |
| Chức năng đã tách vào đủ các lớp | 0 | 2 (`duphong`, `tietkiem`) | mọi chức năng ở bảng "module cũ đi đâu" |
| Chuỗi khóa Redis viết cứng ngoài `keys.py` | ~20 | 0 | 0 |
| Hàm nạp muộn né import vòng | 9 | 9 | 0 |
| Hàm nghiệp vụ trả HTML | nhiều | nhiều | 0 |
| Vi phạm chiều phụ thuộc giữa các lớp (test kiến trúc) | chưa đo | 0 | 0 |
| Bộ đo 113 câu | 98–100 | chưa đo lại | ≥ 98 |
