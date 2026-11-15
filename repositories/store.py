"""Store: chỗ duy nhất của tầng repositories gọi kho.py. Các repo dùng Store, không gọi kho trực tiếp."""
from infrastructure import kho


def get(key, default=None):
    return kho.get(key, default)


def put(key, value, seconds=None):
    kho.put(key, value, seconds)


def put_new(key, value, seconds):
    return kho.put_new(key, value, seconds)


def delete(key):
    kho.delete(key)


def incr(key):
    return kho.command("INCR", key)


def hash_all(key):
    """Hash -> {trường: chuỗi JSON}."""
    flat = kho.command("HGETALL", key) or []
    return dict(zip(flat[::2], flat[1::2]))


def hash_get(key, field):
    return kho.command("HGET", key, field)


def hash_set(key, field, raw):
    kho.command("HSET", key, field, raw)


def hash_del(key, field):
    kho.command("HDEL", key, field)


def ready():
    return kho.ready()
