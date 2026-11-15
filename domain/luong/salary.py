"""Nhắc lương: ngày nhận lương hằng tháng và số tiền."""
from dataclasses import dataclass


@dataclass
class Salary:
    """JSON trong kho: {"ngay": ngày trong tháng (1–31), "tien": số tiền}."""
    day: int
    amount: int

    @classmethod
    def from_dict(cls, data):
        return cls(day=data["ngay"], amount=data["tien"])

    def to_dict(self):
        return {"ngay": self.day, "tien": self.amount}
