"""Quỹ dự phòng (bước đầu của lộ trình xây dựng tài chính) cho bot chi tiêu.

- Chi thiết yếu mỗi tháng tính từ sổ chi tiêu 90 ngày qua: ăn uống, đi chợ, đi lại (bỏ khoản đột biến), nhà cửa và
  hóa đơn, sức khỏe, học tập, gia đình, trả nợ. Không tính mua sắm, giải trí, quà... Tự đặt được: /duphong chi 12tr.
- Mục tiêu: đủ 3–12 tháng chi thiết yếu (mặc định 6), mốc khởi đầu 1 tháng; đạt trong N tháng (mặc định 12).
- Số dư quỹ: các tài sản trong /taisan được gắn vào quỹ (mặc định tài khoản "Quỹ dự phòng"; /duphong nap 2tr để
  thêm, /duphong rut 1tr khi phải dùng; /duphong tinh <tên> để tính thêm sổ tiết kiệm có sẵn).
- Gợi ý mỗi tháng cần để bao nhiêu, so với số dư thu − chi trung bình; ngày ghi lương có nút "Để … vào quỹ".
Thông tin tham khảo, không phải lời khuyên tài chính có giấy phép.
"""
import html
import math
from datetime import date, timedelta

import kho
import phantich as pt
import sochitieu as ct
import taisan as ts
from bantin import vn_num

KEY = "chitieu:duphong"  # {"thang": số tháng mục tiêu, "han": đạt trong bao nhiêu tháng, "bat_dau": ngày, "chi": tự đặt}
FUND_NAME = "Quỹ dự phòng"
ESSENTIAL = ["an", "cho", "xe", "nha", "khoe", "hoc", "giadinh"]  # cộng nhóm tự tạo tên "Trả nợ" nếu có
MONTHS_CHOICES, DEADLINE_CHOICES = (3, 6, 9, 12), (6, 12, 18, 24)
MIN_DAYS = 14  # ít nhất 2 tuần ghi chép mới tự tính chi thiết yếu (ít hơn thì một khoản lớn làm sai lệch cả tháng)
NOT_ADVICE = "<i>Tham khảo, không phải lời khuyên tài chính</i>"


def config():
    return kho.get(KEY, {}) or {}


def save(cfg):
    kho.put(KEY, cfg)


def add_months(d, months):
    return ts.add_months(d, months)


def essential_groups():
    codes = [c for c in ESSENTIAL if c in ct.groups()]
    debt = ct.find_group("trả nợ")
    return codes + ([debt] if debt and debt not in codes else [])


def essential(day):
    """(chi thiết yếu/tháng, {nhóm: chi/tháng}, số ngày dữ liệu). Nhóm hằng ngày bỏ khoản đột biến; tiền nhà, hóa
    đơn, trả nợ... tính đủ vì tháng nào cũng có."""
    codes = essential_groups()
    items = [e for e in pt.spending(ct.between(day - timedelta(days=89), day)) if e["nhom"] in codes]
    if not items:
        return 0, {}, 0
    daily = [c for c in pt.daily_groups() if c in codes] + [c for c in ("khoe", "giadinh") if c in codes]
    limits = pt.spike_limits(items, daily)
    kept = [e for e in items if e["nhom"] not in limits or e["tien"] < limits[e["nhom"]]]
    days = (day - date.fromisoformat(min(e["ngay"] for e in items))).days + 1
    by_group = {}
    for e in kept:
        by_group[e["nhom"]] = by_group.get(e["nhom"], 0) + e["tien"]
    scale = 30.4 / days
    by_group = {c: v * scale for c, v in sorted(by_group.items(), key=lambda x: -x[1])}
    return sum(by_group.values()), by_group, days


def fund_rows(day):
    """Các tài sản tính vào quỹ: [(tên, giá trị)] theo giá/lãi hiện tại."""
    data = ts.load()
    ids = {str(it["id"]) for it in data["items"] if it.get("duphong")}
    if not ids:
        return []
    return [(name, value) for kind, rid, name, value, _, _ in ts.valuation(day)["rows"] if rid in ids]


def status(day):
    cfg = config()
    months = cfg.get("thang", 6)
    deadline_months = cfg.get("han", 12)
    start = date.fromisoformat(cfg["bat_dau"]) if cfg.get("bat_dau") else day
    auto, by_group, days = essential(day)
    monthly = cfg.get("chi") or (auto if days >= MIN_DAYS else 0)
    rows = fund_rows(day)
    balance = sum(v for _, v in rows)
    target = monthly * months
    missing = max(0, target - balance)
    deadline = add_months(start, deadline_months)
    months_left = (deadline.year - day.year) * 12 + deadline.month - day.month - (deadline.day < day.day)
    months_left = max(1, months_left)
    spend, income, flow_days = ts.monthly_flows(day)
    surplus = income - spend if income and flow_days >= 20 else None
    return {"months": months, "deadline_months": deadline_months, "deadline": deadline, "monthly": monthly,
            "auto": auto, "manual": bool(cfg.get("chi")), "by_group": by_group, "days": days, "rows": rows,
            "balance": balance, "target": target, "missing": missing, "covered": balance / monthly if monthly else 0,
            "months_left": months_left, "per_month": missing / months_left if missing else 0, "surplus": surplus,
            "overdue": deadline <= day and missing > 0}


def bar(ratio, width=10):
    full = max(0, min(width, round(ratio * width)))
    return "▓" * full + "░" * (width - full)


def money(x):
    return pt.short(x) if x >= 1000 else "0đ"


def text(day):
    if not kho.ready():
        return ct.NEED_STORE
    s = status(day)
    if not s["monthly"]:
        return ("🛟 <b>Quỹ dự phòng</b>\n"
                f"Sổ mới có {s['days']} ngày, cần ít nhất {MIN_DAYS} ngày ghi chép để tự tính chi thiết yếu mỗi tháng. "
                "Trong lúc chờ, tự đặt luôn: /duphong chi 12tr (tiền ăn, đi chợ, đi lại, tiền nhà, điện nước, trả nợ… "
                "mỗi tháng)"), None
    ratio = s["balance"] / s["target"] if s["target"] else 0
    lines = [f"🛟 <b>Quỹ dự phòng: {money(s['balance'])} / {money(s['target'])}</b> ({s['months']} tháng chi thiết yếu)",
             f"{bar(ratio)} {ratio * 100:.0f}% · đủ {vn_num(s['covered'], 1)} tháng chi"]
    if s["covered"] < 1:
        lines.append(f"🚩 Mốc đầu tiên: đủ 1 tháng chi ({money(s['monthly'])}), còn thiếu {money(s['monthly'] - s['balance'])}")
    elif s["covered"] < 3 <= s["months"]:
        lines.append(f"✅ Đã qua mốc 1 tháng · mốc tiếp theo 3 tháng ({money(3 * s['monthly'])})")
    basis = "bạn tự đặt" if s["manual"] else f"từ sổ {s['days']} ngày qua"
    parts = " · ".join(f"{ct.name(c).split()[0]} {money(v)}" for c, v in list(s["by_group"].items())[:6])
    lines.append(f"Chi thiết yếu: <b>{money(s['monthly'])}/tháng</b> ({basis})" + (f"\n   {parts}" if parts and not s["manual"] else ""))
    if s["missing"]:
        plan = (f"📅 Để đủ trong {s['months_left']} tháng tới (hạn {s['deadline']:%m/%Y}): để <b>{money(s['per_month'])}/tháng</b>"
                if not s["overdue"] else f"📅 Đã quá hạn {s['deadline']:%m/%Y}: đặt hạn mới bằng nút bên dưới")
        lines.append(plan)
        if s["surplus"] is not None:
            if s["surplus"] <= 0:
                lines.append(f"⚠️ 3 tháng qua chi nhiều hơn thu ({money(-s['surplus'])}/tháng): cần bớt chi trước")
            else:
                share = s["per_month"] / s["surplus"] * 100
                lines.append(f"💰 Dư TB mỗi tháng {money(s['surplus'])}: mức trên bằng {share:.0f}% số dư"
                             + (" · vừa sức" if share <= 70 else
                                f" · hơi căng: để 70% phần dư ({money(0.7 * s['surplus'])}) thì cần khoảng "
                                f"{math.ceil(s['missing'] / (0.7 * s['surplus']))} tháng, đổi hạn bằng nút bên dưới"))
    else:
        lines.append("🎉 Quỹ dự phòng đã đủ! Bước tiếp theo: trả nợ lãi cao, rồi đầu tư (tiết kiệm, vàng, ETF...)")
    if s["rows"]:
        lines.append("Đang tính vào quỹ: " + " · ".join(f"{html.escape(n)} {money(v)}" for n, v in s["rows"]))
    else:
        lines.append("<i>Chưa có tài sản nào trong quỹ: bấm ➕ hoặc /duphong nap 2tr; đã có sổ tiết kiệm thì /duphong tinh "
                     "tên sổ</i>")
    lines.append(NOT_ADVICE)
    return "\n".join(lines), buttons(s)


def buttons(s):
    rows = [[(f"➕ {money(a)}", f"dp:nap:{a}") for a in (1_000_000, 2_000_000, 5_000_000)]]
    if s["per_month"] >= 100_000:
        rows[0].insert(0, (f"➕ {money(round(s['per_month'], -5))}", f"dp:nap:{int(round(s['per_month'], -5))}"))
    rows.append([(f"{'🎯' if s['months'] == m else ''}{m} tháng", f"dp:thang:{m}") for m in MONTHS_CHOICES])
    rows.append([(f"{'⏳' if s['deadline_months'] == m else ''}đạt trong {m}t", f"dp:han:{m}") for m in DEADLINE_CHOICES])
    rows.append([("🏦 Để quỹ ở đâu?", "dp:noi")])
    return rows


def fund_item(data):
    item = next((it for it in data["items"] if it["loai"] == "tien" and ts.same_name(it["ten"], FUND_NAME)), None)
    if item is None:
        item = {"id": ts.new_id(data), "loai": "tien", "ten": FUND_NAME, "tien": 0, "ngay": ct.today().isoformat(),
                "duphong": True}
        data["items"].append(item)
    item["duphong"] = True
    return item


def change(amount, day):
    """Thêm (amount > 0) hoặc rút (amount < 0) tiền ở tài khoản "Quỹ dự phòng"; trả câu báo."""
    data = ts.load()
    item = fund_item(data)
    before = status(day)
    item["tien"] = max(0, item["tien"] + amount)
    item["ngay"] = day.isoformat()
    ts.save(data)
    if not config().get("bat_dau"):
        save({**config(), "bat_dau": day.isoformat()})
    after = status(day)
    if amount >= 0:
        note = f"✅ Đã thêm {money(amount)} vào quỹ dự phòng: {money(after['balance'])} / {money(after['target'])}"
        for mark, label in ((1, "đủ 1 tháng chi"), (3, "đủ 3 tháng chi"), (after["months"], "ĐẠT MỤC TIÊU")):
            if after["monthly"] and before["covered"] < mark <= after["covered"]:
                note += f"\n🎉 Chúc mừng: quỹ đã {label}!"
                break
    else:
        note = (f"Đã rút {money(-amount)} khỏi quỹ dự phòng, còn {money(after['balance'])}. Dùng xong nhớ bù lại dần: "
                f"/duphong")
    return note + "\n<i>Đây là chuyển tiền vào quỹ, không tính là khoản chi</i>"


def toggle(name):
    data = ts.load()
    target = next((it for it in data["items"] if it["loai"] in ("tien", "tietkiem", "quy")
                   and ts.same_name(it.get("ten") or it.get("ma", ""), name)), None)
    if not target:
        own = [it.get("ten") or it.get("ma") for it in data["items"] if it["loai"] in ("tien", "tietkiem", "quy")]
        return ("Không thấy tài sản tên «" + html.escape(name) + "» trong /taisan. Có: "
                + html.escape(", ".join(own) or "chưa có tài khoản, sổ tiết kiệm nào"))
    target["duphong"] = not target.get("duphong")
    ts.save(data)
    label = target.get("ten") or target.get("ma")
    return (f"✅ Đã tính «{html.escape(label)}» vào quỹ dự phòng" if target["duphong"]
            else f"Đã bỏ «{html.escape(label)}» khỏi quỹ dự phòng") + "\nXem: /duphong"


def where_text(day):
    lines = ["🏦 <b>Để quỹ dự phòng ở đâu</b>",
             "Cần: rút được ngay hoặc trong vài ngày, không mất vốn, lãi là phụ.",
             "• Tiết kiệm không kỳ hạn, hoặc tiết kiệm online kỳ hạn 1–3 tháng: rút trước hạn chỉ mất lãi, không mất "
             "gốc; nên chia vài sổ nhỏ để cần bao nhiêu rút bấy nhiêu",
             "• Có thể để 1 tháng chi ở tài khoản thanh toán, phần còn lại gửi tiết kiệm"]
    savings = [it for it in ts.load()["items"] if it["loai"] == "tietkiem"]
    if savings:
        lines.append("   Sổ của bạn: " + " · ".join(
            f"{html.escape(it['ten'])} {ts.qty_text(it['lai'])}%" + (" ✅" if it.get("duphong") else "") for it in savings))
    lines.append("• Không để quỹ dự phòng ở cổ phiếu, ETF, vàng (giá lên xuống, lúc cần có thể đang lỗ); các khoản này "
                 "dành cho bước đầu tư sau khi quỹ đủ")
    lines.append("Tính sổ tiết kiệm có sẵn vào quỹ dự phòng: /duphong tinh <tên sổ>")
    return "\n".join(lines + [NOT_ADVICE])


def salary_hint(entries, day):
    """Ghi lương xong: (dòng gợi ý, hàng nút) để tiền vào quỹ dự phòng; None nếu quỹ đã đủ hoặc không có lương."""
    salary = [e for e in entries if e["nhom"] == ct.INCOME and "luong" in ct.plain(e.get("ghichu") or "")]
    if not salary or not kho.ready():
        return None
    s = status(day)
    if not s["monthly"] or not s["missing"]:
        return None
    amount = min(s["missing"], max(s["per_month"], 100_000))
    amount = int(round(amount, -5)) or 100_000
    line = (f"🛟 Quỹ dự phòng {money(s['balance'])}/{money(s['target'])}: tháng này nên để {money(amount)}")
    return line, [(f"🛟 Để {money(amount)} vào quỹ dự phòng", f"dp:nap:{amount}")]


def duphong(args):
    if not kho.ready():
        return ct.NEED_STORE
    day = ct.today()
    word = ct.plain(args[0]) if args else ""
    rest = " ".join(args[1:])
    usage = ("🛟 /duphong: xem quỹ · /duphong nap 2tr · /duphong rut 1tr · /duphong muctieu 6 (tháng chi) · "
             "/duphong han 12 (đạt trong bao nhiêu tháng) · /duphong chi 10tr (tự đặt chi thiết yếu; /duphong chi tu dong "
             "để bot tự tính) · /duphong tinh <tên sổ/quỹ trong /taisan>")
    if not word:
        return text(day)
    if word in ("nap", "them", "de", "rut"):
        found = ct.parse_amount(rest)
        if not found:
            return usage
        return change(found[0] if word != "rut" else -found[0], day)
    if word in ("muctieu", "thang"):
        n = rest.split()[0] if rest.split() else ""
        if not n.isdigit() or not 1 <= int(n) <= 24:
            return usage
        save({**config(), "thang": int(n)})
        return text(day)
    if word == "han":
        n = rest.split()[0] if rest.split() else ""
        if not n.isdigit() or not 1 <= int(n) <= 60:
            return usage
        save({**config(), "han": int(n), "bat_dau": day.isoformat()})
        return text(day)
    if word == "chi":
        if ct.plain(rest).replace(" ", "") in ("tudong", "auto"):
            cfg = config()
            cfg.pop("chi", None)
            save(cfg)
            return text(day)
        found = ct.parse_amount(rest)
        if not found:
            return usage
        save({**config(), "chi": found[0]})
        return text(day)
    if word == "tinh":
        return toggle(rest) if rest.strip() else usage
    if word in ("noi", "odau"):
        return where_text(day)
    return usage


def on_button(arg, message, now):
    """Nút "dp:...": (thông báo nhỏ, việc tiếp theo)."""
    kind, _, value = arg.partition(":")
    day = now.date()
    if kind == "nap" and value.isdigit():
        lines = change(int(value), day).split("\n")
        toast = lines[0][2:] + "".join(f" · {x[2:]}" for x in lines[1:] if x.startswith("🎉"))
        if (message.get("text") or "").startswith("🛟 Quỹ dự phòng"):  # nút trên tin quỹ: vẽ lại tin
            return toast, ("edit", lambda: text(day))
        rows = [row for row in ct.keyboard_rows(message) if not any(d.startswith("dp:nap") for _, d in row)]
        return toast, ("buttons", lambda: rows)  # nút dưới tin "Đã ghi lương": bỏ nút đó
    if kind in ("thang", "han") and value.isdigit():
        cfg = config()
        cfg[kind] = int(value)
        if kind == "han":
            cfg["bat_dau"] = day.isoformat()
        save(cfg)
        return None, ("edit", lambda: text(day))
    if kind == "noi":
        return None, ("send", lambda: where_text(day))
    return None, None
