"""Đọc ảnh hóa đơn bằng AI và ghi các khoản đọc được vào sổ chi tiêu."""
import sys

from domain.chitieu import classify
from domain.chitieu.kinds import INCOME, OTHER
from domain.docanh import receipt
from infrastructure import ai, telegram
from repositories.chitieu import groups as groups_repo
from repositories.chitieu import ledger as ledger_repo
from repositories.docanh import receipts as repo
from services.chitieu import ledger as ledger_service

MAX_BYTES = telegram.MAX_FILE_BYTES


def download(file_id, tok):
    return telegram.download_file(file_id, tok)


def prompt(owners=()):
    owner = f"Chủ tài khoản tên: {', '.join(owners).upper()}. " if owners else ""
    cfg = groups_repo.config()
    groups = ", ".join(f"{code} ({classify.bare(label)})" for code, (label, _, _) in classify.groups(cfg).items()
                       if code != INCOME)
    return ("Ảnh này có thể là: hóa đơn/biên lai (1 khoản); màn hình MỘT giao dịch chuyển khoản; hoặc DANH SÁCH "
            "nhiều giao dịch (lịch sử tài khoản, biến động số dư ngân hàng) của người Việt. Trả lời đúng một dòng "
            "JSON, không giải thích:\n"
            '{"loai": "hoa_don" | "chuyen_khoan" | "danh_sach" | "khac", "giao_dich": [{'
            '"so_tien": số nguyên đồng, '
            '"chieu": "chi" hoặc "thu" (tiền vào tài khoản, dấu + là thu), '
            '"ngay": "dd/mm/yyyy" hoặc null, '
            '"noi_dung": ghi chú ngắn tiếng Việt, viết thường, PHẢI có dấu kể cả khi ảnh in không dấu (vd "phin sữa '
            'đá highlands", "lương tháng 10/2026", "trả nợ vay", "trả thẻ tín dụng", "hoàn tiền mua vé máy bay"), '
            '"noi_ban": tên cửa hàng hoặc người nhận/gửi, '
            '"diem": phần trả bằng voucher, phiếu quà tặng, điểm thưởng (Got It, Urbox...), 0 nếu không có, '
            '"kieu": "chi_tieu" (mua bán, dịch vụ, chuyển cho người khác) | "thu_nhap" (lương, thưởng, người khác '
            'chuyển cho) | "tra_no" (trả nợ vay, trả góp khoản vay) | "tra_the" (thanh toán / trích nợ sao kê thẻ tín '
            'dụng) | "chuyen_noi_bo" (chuyển giữa các tài khoản của CHÍNH chủ tài khoản: cùng tên người; người trả nợ '
            'thẻ tín dụng thường chính là chủ tài khoản), '
            '"nhom": một mã trong ' + groups + "}]}\n"
            "Riêng khi ảnh là XÁC NHẬN LỆNH QUỸ MỞ (mua hoặc hoán đổi chứng chỉ quỹ, ví dụ trên Fmarket), ĐƠN MUA VÀNG "
            "tích trữ (vàng nhẫn, vàng miếng, vàng ép vỉ) hoặc KẾT QUẢ LỆNH CỔ PHIẾU (mua/bán, khối lượng, giá khớp) thì "
            'trả {"loai": "tai_san", "giao_dich": [], "viec": {...}}, với "viec" là một trong ba dạng:\n'
            '{"viec": "quy", "chieu": "mua" | "hoan_doi", "ma": mã quỹ mua, "tien": số tiền mua (đồng), "ccq": số ccq đem '
            'hoán đổi, "ngay": "YYYY-MM-DD" ngày đặt lệnh}\n'
            '{"viec": "vang", "loai": "nhan" (nhẫn, 24k, ép vỉ) | "sjc" (vàng miếng SJC), "chi": TỔNG số chỉ (số vỉ × số '
            'chỉ mỗi vỉ; 1 lượng = 10 chỉ), "tien": số tiền thực trả (Thành tiền, sau giảm giá)}\n'
            '{"viec": "co_phieu", "chieu": "mua" | "ban", "ma": mã cổ phiếu, "sl": khối lượng, "gia": giá khớp tính bằng '
            'nghìn đồng như trên ảnh (12.00 là 12), "gia_von": giá vốn hoặc giá hòa vốn nếu ảnh có}\n'
            "Trường nào ảnh không ghi thì bỏ hẳn, không đoán.\n"
            "Hóa đơn: 1 phần tử, so_tien là TỔNG GIÁ TRỊ (dòng TỔNG CỘNG / Tong tien / TỔNG THANH TOÁN, kể cả phần trả "
            "bằng voucher hay điểm; không lấy tiền khách đưa, tiền thừa, số dư hay từng dòng phương thức thanh toán). "
            + owner +
            "Danh sách: mỗi dòng giao dịch một phần tử, đúng thứ tự trên ảnh; dòng bị cắt mất số tiền thì bỏ; tiêu đề "
            '"Hôm nay" thì ngay là null. Không phải hóa đơn hay giao dịch thì {"loai": "khac", "giao_dich": []}.')


def read_receipt(data, mime):
    """Nhờ AI đọc ảnh: {"loai", "giao_dich": [{tien, chieu, ngay, noi_dung, noi_ban, diem, nhom, kieu}], "model"}."""
    # Lúc Gemini đông có khi mất 10–20 giây/ảnh: chờ mỗi model tới 30 giây, tổng không quá 48 giây
    text, model = ai.chat("Bạn đọc hóa đơn và màn hình giao dịch ngân hàng của người Việt, trả lời bằng JSON.",
                          prompt(repo.owners()), max_tokens=4000, image=(data, mime), timeout=30, budget=48)
    raw = ai.first_json(text)
    if not isinstance(raw, dict):
        raise RuntimeError(f"AI trả lời không đúng dạng: {text[:100]!r}")
    txs = receipt.transactions(raw)
    print(f"[ảnh] đọc bằng {model}: {raw.get('loai')}, {len(txs)} giao dịch", file=sys.stderr)
    return {"loai": raw.get("loai"), "giao_dich": txs, "model": model, "viec": raw.get("viec")}


def remember_owners(txs):
    """Nhận ra chủ tài khoản từ ảnh này, nhớ lại cho các ảnh sau; trả danh sách tên."""
    known = repo.owners()
    names = receipt.owner_names(known, txs)
    if names != known:
        repo.save_owners(names)
    return names


def mark_own_transfers(txs):
    receipt.mark_own_transfers(txs, remember_owners(txs))


def prepare_list(txs, day):
    """Danh sách nhiều giao dịch: chuẩn hóa, đánh dấu đã ghi, lưu chờ người dùng chọn."""
    receipt.prepare_list(txs, day, lambda ngay, tien, chieu: repo.recorded(ngay, tien, chieu) is not None)


def entry_from(tx, learned, cfg):
    """Khoản để ghi từ một giao dịch đọc được."""
    note = tx["noi_dung"] or receipt.norm(tx["noi_ban"])
    e = {"ngay": tx["ngay"], "tien": tx["tien"], "ghichu": note, "anh": True}
    if tx["chieu"] == "thu":
        e["nhom"] = INCOME
        return e
    active = classify.groups(cfg)
    e["nhom"] = classify.classify(note, learned, cfg)  # nhóm bạn đã dạy, từ khóa: đáng tin hơn AI đoán
    if e["nhom"] == OTHER and tx["kieu"] == "tra_no":
        e["nhom"] = classify.find_group("trả nợ", cfg, False) or OTHER  # có nhóm Trả nợ (tự tạo) thì vào đó
    if e["nhom"] == OTHER and tx["nhom"] in active and tx["nhom"] not in (OTHER, INCOME):
        e["nhom"], e["ai"] = tx["nhom"], True
    return e


def _save(e, tx, now):
    e["id"] = ledger_repo.next_id()
    e["gio"] = now.strftime("%H:%M")
    ledger_repo.save(e)
    repo.mark_recorded(e["ngay"], e["tien"], tx["chieu"], e["id"])


def record(txs, now):
    learned, cfg, out = repo.learned(), groups_repo.config(), []
    for tx in txs:
        e = entry_from(tx, learned, cfg)
        _save(e, tx, now)
        out.append(e)
    return out


def record_one(tx, now, chosen=None):
    """Ghi một giao dịch; chosen là nhóm người dùng chọn bằng #nhóm trong chú thích ảnh (dạy bot nhớ)."""
    e = entry_from(tx, repo.learned(), groups_repo.config())
    if chosen and tx["chieu"] == "chi":
        e["nhom"] = chosen
        e.pop("ai", None)
        ledger_service.learn(e["ghichu"], chosen)
    _save(e, tx, now)
    return e


def record_points(amount, day, now):
    """Phần trả bằng điểm/voucher ghi vào Thu nhập."""
    ledger_repo.save({"id": ledger_repo.next_id(), "ngay": day.isoformat(), "gio": now.strftime("%H:%M"),
                      "tien": amount, "ghichu": "đổi điểm, voucher", "nhom": INCOME})
