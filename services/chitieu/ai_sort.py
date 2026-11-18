"""Xếp nhóm bằng AI (tùy chọn): chỉ hỏi AI những khoản từ khóa không nhận ra (rơi vào Khác), nhớ câu trả lời; AI lỗi hết
thì khoản vào Khác và bot hỏi người dùng. Câu tình trạng AI cho trang cài đặt."""
import sys
import urllib.error
from datetime import datetime

from domain.chitieu import classify
from domain.chitieu import learn as learn_rules
from domain.chitieu.kinds import INCOME, OTHER
from infrastructure import ai
from repositories.chitieu import groups as groups_repo


def ai_prompt(learned=None):
    """Lời dặn cho AI: các nhóm đang dùng (kể cả nhóm tự tạo) kèm vài từ khóa gợi ý, và những khoản
    người dùng đã tự xếp làm ví dụ để AI đoán theo thói quen của người dùng."""
    cfg = groups_repo.config()
    active = {c: g for c, g in classify.groups(cfg).items() if c != INCOME}
    lines = []
    for code, (label, own, builtin) in active.items():
        hint = ", ".join(list(dict.fromkeys(own + builtin))[:8])
        lines.append(f"{code}: {classify.bare(label)}" + (f" (vd: {hint})" if hint else ""))
    examples = [f"{note} -> {code}" for note, code in list((learned or {}).items())[-30:] if code in active]
    return ("Bạn phân loại khoản chi tiêu cá nhân của người Việt. Các nhóm (mã: tên):\n" + "\n".join(lines)
            + ("\nNgười dùng này đã tự xếp như sau, hãy theo đúng thói quen đó:\n" + "\n".join(examples)
               if examples else "")
            + "\nTrả lời đúng một dòng JSON, khóa là số thứ tự, giá trị là mã nhóm, ví dụ "
            '{"1": "an", "2": "xe"}. Chỉ chọn nhóm khi khá chắc chắn; không chắc thì dùng "khac" '
            "(bot sẽ hỏi người dùng). Không giải thích.")

def ai_request(notes, learned=None):
    """Hỏi AI nhóm của các ghi chú: ({ghi chú: mã}, model đã trả lời). Lỗi mạng, hết lượt... thì báo lỗi."""
    numbered = "\n".join(f"{i}. {note}" for i, note in enumerate(notes, 1))
    text, model = ai.chat(ai_prompt(learned), numbered)
    found = ai.first_json(text)
    if not isinstance(found, dict):
        raise RuntimeError(f"AI trả lời không đúng dạng: {text[:100]!r}")
    answer = {k: str(v).strip().lower() for k, v in found.items()}
    active = classify.groups(groups_repo.config())
    return {note: answer[str(i)] for i, note in enumerate(notes, 1) if answer.get(str(i)) in active}, model

def ask_ai(entries, learned=None):
    """Khoản rơi vào Khác thì hỏi AI (có nhớ câu trả lời cũ); đánh dấu khoản do AI xếp. Trả về số khoản AI xếp."""
    # tiền trả nợ, đóng thẻ tín dụng: AI hay xếp nhầm vào nhà cửa, hóa đơn nên để ở Khác cho người dùng chọn
    unknown = [e for e in entries if learn_rules.pending(e) and e["ghichu"] and not e.get("_chon")
               and not classify.is_debt_payment(e["ghichu"])]
    if not unknown or not ai.key():
        return 0
    cache = groups_repo.ai_cache()
    ask = list(dict.fromkeys(e["ghichu"] for e in unknown if learn_rules.learn_key(e["ghichu"]) not in cache))
    if ask:
        try:
            for note, code in ai_request(ask, learned)[0].items():
                cache[learn_rules.learn_key(note)] = code
            groups_repo.save_ai_cache(dict(list(cache.items())[-learn_rules.MAX_LEARNED:]))
        except Exception as e:
            print(f"[lỗi] xếp nhóm bằng AI: {e!r}", file=sys.stderr)
    active, done = classify.groups(groups_repo.config()), 0
    for e in unknown:
        code = cache.get(learn_rules.learn_key(e["ghichu"]), OTHER)
        if code in active and code not in (OTHER, INCOME):  # khoản thu chỉ nhận khi người dùng tự ghi
            e["nhom"], e["ai"] = code, True
            done += 1
    if done:
        groups_repo.add_ai_guessed(done)
    return done

def ai_stats():
    """(số khoản AI đã xếp, số khoản người dùng phải sửa lại)."""
    return groups_repo.ai_stats()

def quota_text():
    """Lượt OpenRouter: 'đã dùng 12/50 lượt miễn phí hôm nay' hoặc báo hết lượt; rỗng nếu không dùng OpenRouter."""
    try:
        quota = ai.quota()
    except urllib.error.HTTPError as e:
        return "LỖI – key không hợp lệ, kiểm tra biến AI_API_KEY" if e.code == 401 else f"không xem được lượt dùng ({e})"
    except Exception as e:
        return f"không xem được lượt dùng ({e!r})"
    if not quota:
        return ""
    used, limit = quota
    return f"hôm nay đã dùng {used}/{limit} lượt miễn phí" + (
        " – HẾT LƯỢT, 7h sáng mai có lại" if used >= limit else "")

def ai_status(test=False):
    """Một dòng tình trạng AI cho trang cài đặt. test=True thì thử xếp một khoản mẫu (tốn 1 lượt)."""
    if not ai.key():
        return "AI xếp nhóm: tắt (chưa có biến GEMINI_API_KEY hoặc AI_API_KEY)"
    chain = " → ".join(f"{name_} ({', '.join(models)})" for name_, _, _, models in ai.providers())
    if not test:
        quota = quota_text()
        return (f"AI xếp nhóm: bật, thử lần lượt {chain}" + (f". OpenRouter {quota}" if quota else "")
                + ". Thêm ?thu=1 vào địa chỉ trang để thử gọi AI")
    start = datetime.now()
    try:
        got, model = ai_request(["thay má phanh"])
    except Exception as e:
        return f"AI xếp nhóm ({chain}): LỖI – {e}"
    seconds = (datetime.now() - start).total_seconds()
    return (f"AI xếp nhóm: hoạt động ({model}, {seconds:.1f} giây), thử 'thay má phanh' → "
            f"{classify.name(got.get('thay má phanh', OTHER), groups_repo.config())}")
