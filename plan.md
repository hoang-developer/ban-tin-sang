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

```
interface/      router, LLM điều phối, api/*, lịch tick
   ↓
services/       một hàm cho mỗi việc người dùng làm; trả kết quả có cấu trúc (dataclass), không trả HTML
   ↓                                  ↘
repositories/   mỗi aggregate một repo, bọc kho.py       presentation/   kết quả → HTML Telegram + bàn phím
domain/         dataclass + quy tắc thuần (không I/O, không HTML)
```

Phụ thuộc chỉ đi một chiều xuống. Hết import vòng thì bỏ 9 hàm nạp muộn.

Pattern: Repository, Domain Model, Service Layer (Use Case), Presenter. Chuyển đổi theo Strangler Fig, không viết lại một lượt.

Tên gói bằng tiếng Anh (tên tầng), tên khái niệm trong gói theo nghĩa nghiệp vụ (`gold`, `assets`, `ledger`…).

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
- `repositories/gold.py`: `GoldRepo.all()`, `.save(lots)`, `.add(lot)`.
- Thay các chỗ `kho.get("vivang")` / `kho.put("vivang")`.

Xong khi: không file nào ngoài repo đọc/ghi ví vàng; test bán vàng/mua vàng/hiển thị bảng vàng xanh; thêm test thuần cho `sell_fifo`.

### Bước 3: `AssetRepo`
`taisan.load/save` đã gần là repository.
- `domain/assets.py`: `AssetItem`, `RealizedGain`, `new_id`, `find_item`.
- `repositories/assets.py`: `AssetRepo.load()/save()`, gom `dem` và `lailo`, lịch sử tài sản (`K_HISTORY`), lương (`K_SALARY`).
- `taisan.py` chỉ gọi repo.

Xong khi: `kho` không còn được gọi trong `taisan.py`.

### Bước 4: `LedgerRepo` (sổ chi tiêu)
Dùng nhiều nhất (`sochitieu.load/save/HSET/HGET/HDEL`).
- `domain/ledger.py`: `Entry`.
- `repositories/ledger.py`: `month(ym)`, `add(entry)`, `remove(id)`, `find(id)`, bộ đếm id.

Xong khi: `sochitieu.py` không gọi `HSET/HGET/HDEL/HGETALL` trực tiếp.

### Bước 5: tách `taisan.py` thành domain / service / presentation
- `sell_gold`, `close_saving`, `sell_fund`, `collect_loan`, `remove_named` trả `SaleResult` / `CloseResult`…; phần HTML chuyển sang `presentation/`.
- `troly.run_many` ghép kết quả có cấu trúc thành tin gộp thay vì cắt chuỗi.

Xong khi: không hàm service nào trả HTML; chạy bộ đo (đụng `troly`).

### Bước 6: các repo còn lại và gỡ hàm nạp muộn
- `SettingsRepo` (ngân sách, nhóm riêng, nhóm dự báo, cờ bàn phím, bật/tắt), `ConversationRepo` (trạng thái dở, thẻ chờ), `FundRepo` (cấu hình, NAV, thông tin quỹ), `DebtRepo`, `ReserveRepo`, `SavingRepo`, `ReconcileRepo`, `CacheRepo` (AI học, thống kê, dedup ảnh).
- Gỡ 9 hàm nạp muộn `ct.taisan()`… khi hết import vòng.

Xong khi: chỉ `repositories/store.py` còn gọi `kho`; không còn hàm nạp muộn; chạy bộ đo.

### Bước 7 (tùy chọn): chống ghi đè
Thêm số phiên bản vào `AssetRepo` để webhook và tick không ghi đè nhau (Upstash REST hỗ trợ `EVAL`). Làm riêng, có test mô phỏng hai lần ghi chen nhau.

## 5. Chưa làm

- Không viết lại một lượt; không DDD đầy đủ; không interface/port trừu tượng khi chỉ có một nơi lưu trữ (Redis).
- Chưa động `phantich.py`, `lenh.py` (trừ khóa/ví vàng), `bantin.py`, `chungkhoan.py`: phần lớn là đọc và hiển thị.
- Không đổi schema Redis, không đổi giao diện tin nhắn.

## 6. Rủi ro và cách giữ

| Rủi ro | Giữ bằng |
|---|---|
| Đổi tên khóa nhầm, mất dữ liệu | Khóa chép nguyên chuỗi cũ; test so khóa với danh sách chốt từ `main` |
| Gói mới không vào bundle Vercel / Actions | Kiểm tra trang tình trạng bot sau mỗi deploy; bước 1 deploy riêng để phát hiện sớm |
| Hành vi lệch khi gom hàm | Test hiện có (hơn 80 test) + bộ đo 113 câu + test mới cho phần thuần |
| PR quá lớn | Mỗi bước tách tiếp nếu quá ~500 dòng đổi |
| Hết lượt Gemini miễn phí khi chạy bộ đo | Chỉ chạy bộ đo ở bước 5, 6 (và khi đụng `troly`) |

Hoàn tác: mỗi bước là một PR riêng, `git revert` được.

## 7. Số đo hoàn thành

| Chỉ số | Hiện tại | Đích |
|---|---|---|
| File gọi `kho.*` trực tiếp | 18 | 1 (`repositories/store.py`) |
| Chuỗi khóa Redis viết cứng ngoài `keys.py` | ~20 | 0 |
| Hàm nạp muộn né import vòng | 9 | 0 |
| Hàm nghiệp vụ trả HTML | nhiều (`taisan.*`) | 0 |
| Bộ đo 113 câu | 98–100 | ≥ 98 |
