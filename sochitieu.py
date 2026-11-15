"""Bot ghi chi tiêu: nhắn "cà phê 35k" là bot ghi lại và tự xếp nhóm; phần nhận tin ở api/chitieu.py.

Mỗi lệnh trả về tin nhắn HTML, hoặc (tin nhắn, nút bấm) như lenh.py; /xuat trả về file CSV.
Xem thử (chỉ đọc và xếp nhóm, không ghi): python sochitieu.py "cà phê 35k"
"""
import base64
import csv
import html
import io
import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.request
from calendar import monthrange
from datetime import date, datetime, timedelta

from domain.chitieu import classify as classify_rules
from domain.chitieu import income as income_rules
from domain.chitieu import period as periods
from domain.chitieu import labels
from domain.chitieu import text as chitieu_text
from domain.chitieu.learn import MAX_LEARNED, NOISE, learn_key, pending  # noqa: F401
from domain.chitieu import parse as parse_rules
from domain.chitieu.categories import (AMBIGUOUS_PLAIN, CATEGORIES, GENERIC, KEYWORDS, plain_pattern,  # noqa: F401
                                       word_pattern)
from domain.chitieu.kinds import INCOME, OTHER  # noqa: F401
from domain.chitieu.parse import DATE, DAY_WORDS, TAG  # noqa: F401
from domain.common import format as format_text
from domain.common.money import MONEY, QUANTITY, UNITS, money, money_count, parse_amount, to_number  # noqa: F401
from domain.common.text import norm, plain  # noqa: F401
from infrastructure import kho
from repositories import keys
from repositories.chitieu import groups as groups_repo
from repositories.chitieu import ledger as ledger_repo
from bantin import VN_TZ, vn_num

MAX_GROUPS, MAX_WORDS = 20, 60  # số nhóm tự tạo, số từ khóa tự thêm cho mỗi nhóm



def token():
    return os.environ.get("CHITIEU_BOT_TOKEN", "").strip()


def owner_chats():
    """Chat được dùng bot: CHITIEU_CHAT_ID (nhiều người thì cách nhau dấu phẩy), mặc định TELEGRAM_CHAT_ID."""
    ids = os.environ.get("CHITIEU_CHAT_ID") or os.environ.get("TELEGRAM_CHAT_ID", "")
    return [x.strip() for x in ids.split(",") if x.strip()]


def today():
    return datetime.now(VN_TZ).date()


# ---- Đọc tin nhắn ----------------------------------------------------------------

# ---- Nhóm tự chỉnh: người dùng thêm nhóm, thêm từ khóa, đổi tên, ẩn nhóm ngay trong Telegram (/nhom) ----
# Lưu ở khóa chitieu:nhomrieng: {"moi": [mã nhóm tự tạo], "ten": {mã: tên}, "tu": {mã: [từ khóa]},
# "an": [mã nhóm đã ẩn], "dem": số nhóm đã tạo}. Nhóm ẩn vẫn giữ tên để khoản cũ hiện đúng.

config, reset, save_config = groups_repo.config, groups_repo.reset, groups_repo.save






# ---- Xếp nhóm bằng AI (tùy chọn) ------------------------------------------------------
# Chỉ hỏi AI những khoản từ khóa không nhận ra (rơi vào Khác); AI cũng hiểu câu hỏi, viết nhận xét.
# Hai nhà cung cấp, cùng kiểu API của OpenAI (chat/completions), có cái nào dùng cái đó:
# - Google Gemini (biến GEMINI_API_KEY), dùng trước: gói miễn phí không giới hạn chung 50 lượt/ngày.
#   Thử ngày 04/11/2026: Gemini 3.5 Flash-Lite xếp đúng 13/13 khoản lạ trong khoảng 1 giây, Flash cũng
#   13/13 (khoảng 8 giây, gói miễn phí 5 lượt/phút). Model trước lỗi, bận, hết lượt thì thử model sau.
# - OpenRouter (biến AI_API_KEY), dự phòng: model miễn phí, cả tài khoản 50 lượt/ngày; AI_MODEL nhiều
#   model cách nhau dấu phẩy thì OpenRouter tự chuyển. AI_API_URL đổi được sang nhà cung cấp khác.
# AI lỗi hết thì khoản vào Khác và bot hỏi người dùng.

from infrastructure import ai as ai_client  # noqa: E402

env_list, gemini_key, openrouter_key = ai_client.env_list, ai_client.gemini_key, ai_client.openrouter_key
ai_key, ai_models, ai_providers = ai_client.key, ai_client.openrouter_models, ai_client.providers
ai_post, ai_chat, first_json = ai_client.post, ai_client.chat, ai_client.first_json
from services.chitieu import ai_sort, ledger as ledger_service  # noqa: E402
from interface.chitieu import commands  # noqa: E402
from presentation.chitieu import view as cview  # noqa: E402
from interface.chitieu.context import (BACK, CHI_BUTTONS, INCOME_KINDS, REPORT_BUTTONS, SORT_TITLE, bare, budget_label,  # noqa: E402,F401
                                       budget_lines, budget_status, button_ref, classify, entries_message, entry_text,
                                       find_group, full_month, groups, income_kind, income_kinds, name, parse_date,
                                       parse_line, period, pick, picker, read_tag, ref, report, rules, short, vnd,
                                       with_picker)

baocao, thang, lichsu, delete, xoa_cuoi, ngansach = (commands.baocao, commands.thang, commands.lichsu, commands.delete,
                                                     commands.xoa_cuoi, commands.ngansach)
from interface import common  # noqa: E402
from interface.chitieu import bot, features  # noqa: E402

COMMANDS, VISIBLE, MENU = bot.COMMANDS, bot.VISIBLE, bot.MENU
answer, respond, record_text, on_button = bot.answer, bot.respond, bot.record_text, bot.on_button
salary_fund_hint, debt_after, refs_in, render, period_kind = (bot.salary_fund_hint, bot.debt_after, bot.refs_in, bot.render,
                                                              bot.period_kind)
keyboard_rows, from_menu, NEED_STORE = common.keyboard_rows, common.from_menu, cview.NEED_STORE
taisan, duphong, phantich, sono, kehoach, menu, dautu, tietkiem, troly = (
    features.taisan, features.duphong, features.phantich, features.sono, features.kehoach, features.menu,
    features.dautu, features.tietkiem, features.troly)
nhom_cmd, chuaxep, xuat = commands.nhom_cmd, commands.chuaxep, commands.xuat
nhom_them, nhom_tukhoa, nhom_doiten, nhom_xoa = (commands.nhom_them, commands.nhom_tukhoa, commands.nhom_doiten,
                                                 commands.nhom_xoa)
add_words, after_change, NHOM_USAGE = commands.add_words, commands.after_change, commands.NHOM_USAGE
split_spec, make_label = labels.split_spec, labels.make_label


def find_category(text):
    """Tên nhóm người dùng gõ ('ăn uống', 'di lai', 'tổng') -> mã, None nếu không rõ."""
    return classify_rules.find_category(text, config())

add, recent, learn_all, learn, tidy = (ledger_service.add, ledger_service.recent, ledger_service.learn_all,
                                       ledger_service.learn, ledger_service.tidy)
ai_prompt, ai_request, ask_ai, ai_stats = ai_sort.ai_prompt, ai_sort.ai_request, ai_sort.ask_ai, ai_sort.ai_stats
quota_text, ai_status = ai_sort.quota_text, ai_sort.ai_status


def ai_quota():
    return ai_client.quota()
AI_URL, AI_TIMEOUT = ai_client.AI_URL, ai_client.AI_TIMEOUT  # noqa: F401


# ---- Lưu trữ: mỗi tháng một Redis hash, mỗi khoản một mục (id -> JSON) ---------------
# Ghi/sửa/xóa từng mục riêng nên hai tin nhắn tới cùng lúc không đè mất khoản của nhau.

def load(ym):
    return ledger_repo.load(ym)


def save(e):
    ledger_repo.save(e)


def find(reference):
    """'2026-11:12' -> khoản đó, None nếu đã xóa."""
    ym, _, rid = reference.partition(":")
    return ledger_repo.find(ym, rid)


def between(start, end):
    """Các khoản từ ngày start tới end (tính cả hai đầu)."""
    return ledger_repo.between(start, end)




# ---- Hiển thị ---------------------------------------------------------------------



# ---- Báo cáo ------------------------------------------------------------------------


# ---- Lệnh ---------------------------------------------------------------------------



def main():
    sys.stdout.reconfigure(encoding="utf-8")
    for line in " ".join(sys.argv[1:]).split("\\n"):
        e = parse_line(line, today())
        print(f"{line!r} -> " + (f"{vnd(e['tien'])} · {name(e['nhom'])} · {e['ghichu']!r} · {e['ngay']}"
                                 if e else "không thấy số tiền"))


if __name__ == "__main__":
    main()
