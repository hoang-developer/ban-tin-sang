"""SalaryRepo: ngày và số tiền lương để nhắc hằng tháng (khóa keys.SALARY)."""
from domain.luong.salary import Salary
from repositories import keys, store


def load():
    """Salary hoặc None nếu chưa đặt."""
    data = store.get(keys.SALARY)
    return Salary.from_dict(data) if data else None


def save(salary):
    store.put(keys.SALARY, salary.to_dict())


def clear():
    store.delete(keys.SALARY)
