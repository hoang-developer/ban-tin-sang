"""Quy tắc thuần của Value Averaging (không đọc/ghi gì): số góp, đường kế hoạch, lệnh nào dành cho quỹ chính."""
from domain.dautu.calendar import months

DEFAULT_FUND, DEFAULT_GOP, DEFAULT_TANG = "VMEEF", 4_000_000, 0.01
MIN_ORDER, STEP = 100_000, 10_000
WATCH = ("VIC", "VHM", "VRE", "VPL")  # nhóm Vingroup: báo nếu vào top 10 của quỹ
SWITCH_DAYS = 7  # hoán đổi quỹ chờ → quỹ chính: bán quỹ chờ, tiền về rồi mới mua quỹ chính, khoảng 1 tuần


def is_active(cfg):
    """Đã bật /dautu và chưa tắt."""
    return bool(cfg.get("ma")) and not cfg.get("tat")


def wait_name(cfg):
    return f"Quỹ chờ {cfg['ma']}"


def holding(data, cfg, code=None):
    code = code or cfg["ma"]
    return next((it for it in data["items"] if it["loai"] == "quy" and it["ma"] == code), None)


def side(cfg):
    """Quỹ chờ là quỹ (ví dụ VFF: vừa là phần trái phiếu của danh mục, vừa là tiền chờ cho VA): {"ma", "id"} hoặc None
    nếu quỹ chờ là tiền gửi."""
    return cfg.get("cho") or None


def pending_main(cfg, o):
    """Lệnh chưa xong mà tiền đã dành cho quỹ chính: lệnh mua chờ khớp, hoán đổi chưa bán hoặc đã bán chờ mua."""
    return o["trang_thai"] in ("cho", "chuyen") and goes_main(cfg, o)


def goes_main(cfg, o):
    """Lệnh làm tăng quỹ chính: mua quỹ chính, hoặc hoán đổi từ quỹ chờ sang."""
    return o.get("loai") == "doi" or o.get("quy", cfg["ma"]) == cfg["ma"]


def them_of(cfg, ym):
    """Số góp thêm mỗi tháng vào quỹ chờ (ngoài phần VA), 0 nếu tháng tạm dừng."""
    if not side(cfg) or (cfg.get("ky", {}).get(ym) or {}).get("bo"):
        return 0
    steps = [(k, v) for k, v in cfg.get("them", {}).items() if k <= ym]
    return max(steps)[1] if steps else 0


def total_of(cfg, ym):
    """Tổng tiền góp của tháng: phần VA + phần góp thêm vào quỹ chờ."""
    return gop_of(cfg, ym) + them_of(cfg, ym)


def gop_of(cfg, ym):
    if (cfg.get("ky", {}).get(ym) or {}).get("bo"):
        return 0
    steps = [(k, v) for k, v in cfg.get("gop", {}).items() if k <= ym]
    return max(steps)[1] if steps else 0


def extra_of(cfg, ym):
    """Phần cộng thêm vào kế hoạch quỹ chính trong tháng ym khi rải một khoản tiền lớn (/dautu taicocau)."""
    return cfg.get("ke_hoach_them", {}).get(ym, 0)


def target(cfg, ym):
    """Giá trị kế hoạch của kỳ ym."""
    value = None
    for m in months(cfg["bat_dau"], ym):
        add = gop_of(cfg, m) + extra_of(cfg, m)
        value = cfg.get("goc", 0) + add if value is None else value * (1 + cfg.get("tang", DEFAULT_TANG)) + add
    return value or 0


def contributed_of(cfg):
    """Tổng tiền đã góp: góp hằng tháng + khoản góp một lần (tái cơ cấu) + giá trị có sẵn lúc bắt đầu."""
    return sum(cfg.get("nap", {}).values()) + sum(cfg.get("ngoai", {}).values()) + cfg.get("goc", 0)
