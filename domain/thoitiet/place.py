"""Địa danh: ghép tên hiển thị từ kết quả tìm kiếm."""


def place_of(r):
    """Kết quả tìm kiếm -> ((vĩ độ, kinh độ), tên hiển thị): 'Đà Nẵng', 'Paris, Île-de-France, France'."""
    label = r["name"]
    if r.get("admin1") and r["admin1"] != r["name"]:
        label += f", {r['admin1']}"
    if r.get("country_code") != "VN":
        label += f", {r.get('country', '')}"
    return (r["latitude"], r["longitude"]), label
