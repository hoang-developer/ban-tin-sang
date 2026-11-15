"""GroupsRepo: cấu hình nhóm tự chỉnh của người dùng (khóa keys.GROUPS) và các câu AI đã xếp nhóm (keys.AI_CACHE)."""
from infrastructure import kho
from repositories import keys


def load():
    return kho.get(keys.GROUPS, {})


def save(cfg):
    """Lưu cấu hình nhóm; nhóm đã khác nên các câu AI trả lời trước đó không còn đúng danh sách nhóm."""
    kho.put(keys.GROUPS, cfg)
    kho.delete(keys.AI_CACHE)


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
