"""Tìm nơi theo tên cho lệnh /thoitiet."""
from domain.thoitiet import place
from infrastructure import openmeteo


def find_place(name):
    """Tên địa danh -> ((vĩ độ, kinh độ), tên hiển thị); None nếu không tìm thấy. Ưu tiên Việt Nam."""
    for country in ("VN", None):
        found = openmeteo.geocode(name, country)
        if found:
            return place.place_of(found)
    return None
