"""GroupsRepo: cấu hình nhóm tự chỉnh của người dùng (khóa keys.GROUPS) và các câu AI đã xếp nhóm (keys.AI_CACHE)."""
from infrastructure import kho
from repositories import keys

_config = None  # đọc một lần mỗi lượt xử lý; reset() ở đầu mỗi tin nhắn, lượt bấm nút, lịch chạy


def reset():
    global _config
    _config = None


def load():
    return kho.get(keys.GROUPS, {})


def config():
    """Cấu hình nhóm của lượt xử lý này (đọc một lần); chưa nối kho thì rỗng."""
    global _config
    if _config is None:
        if not kho.ready():
            return {}
        _config = load()
    return _config


def save(cfg):
    """Lưu cấu hình nhóm; nhóm đã khác nên các câu AI trả lời trước đó không còn đúng danh sách nhóm."""
    global _config
    kho.put(keys.GROUPS, cfg)
    _config = cfg
    kho.delete(keys.AI_CACHE)


def learned():
    """Các cụm từ người dùng đã chọn nhóm: {khóa: mã nhóm}."""
    return kho.get(keys.LEARN, {})


def save_learned(data):
    kho.put(keys.LEARN, data)


def ai_cache():
    return kho.get(keys.AI_CACHE, {})


def save_ai_cache(cache):
    kho.put(keys.AI_CACHE, cache)


def add_ai_guessed(count):
    kho.command("HINCRBY", keys.AI_STATS, "doan", count)


def ai_stats():
    """(số khoản AI đã xếp, số khoản người dùng phải sửa lại)."""
    flat = kho.command("HGETALL", keys.AI_STATS) or []
    stats = dict(zip(flat[::2], flat[1::2]))
    return int(stats.get("doan", 0)), int(stats.get("sua", 0))
