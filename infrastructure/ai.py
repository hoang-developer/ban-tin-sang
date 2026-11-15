"""Cổng ra AI (kiểu API chat/completions của OpenAI): Gemini dùng trước, OpenRouter dự phòng. Chỉ gọi và đọc kết quả.

Hai nhà cung cấp, có cái nào dùng cái đó:
- Google Gemini (biến GEMINI_API_KEY), dùng trước: gói miễn phí không giới hạn chung 50 lượt/ngày.
  Thử ngày 04/11/2026: Gemini 3.5 Flash-Lite xếp đúng 13/13 khoản lạ trong khoảng 1 giây, Flash cũng
  13/13 (khoảng 8 giây, gói miễn phí 5 lượt/phút). Model trước lỗi, bận, hết lượt thì thử model sau.
- OpenRouter (biến AI_API_KEY), dự phòng: model miễn phí, cả tài khoản 50 lượt/ngày; AI_MODEL nhiều
  model cách nhau dấu phẩy thì OpenRouter tự chuyển. AI_API_URL đổi được sang nhà cung cấp khác.
"""
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
# 05/11/2026: 3.1 Flash-Lite cũng đúng 13/13, đọc đúng ảnh hóa đơn và lịch sử giao dịch (1–2 giây); nằm ở nhóm máy
# chủ khác nên lúc 3.5 báo quá tải (503) vẫn trả lời được
GEMINI_MODELS = "gemini-3.5-flash-lite,gemini-3.1-flash-lite,gemini-3.5-flash"
AI_URL = "https://openrouter.ai/api/v1/chat/completions"
# Chọn ngày 04/11/2026: thử 13 khoản lạ, Nemotron 3 Ultra đúng 12, Dots 3 đúng 12 (dự phòng).
# Không thêm openrouter/free: nó chọn ngẫu nhiên model miễn phí, có lần chỉ đúng 7/13.
AI_MODELS = "nvidia/nemotron-3-ultra-550b-a55b:free,dots-studio/dots-3-note-preview:free"
AI_TIMEOUT = 25  # giây; model miễn phí có "suy nghĩ" trước khi trả lời nên chậm, quá thì thôi
# Đọc ảnh: model Gemini ở trên đều xem được ảnh; trên OpenRouter phải dùng model riêng (thử 04/11/2026:
# Nemotron 3.5 Super VL đọc đúng số tiền 6/6 ảnh mẫu)
AI_VISION_MODELS = "nvidia/nemotron-3.5-super-vl:free"


def env_list(name, default):
    return [m.strip() for m in os.environ.get(name, default).split(",") if m.strip()]


def gemini_key():
    return os.environ.get("GEMINI_API_KEY", "").strip()


def openrouter_key():
    return os.environ.get("AI_API_KEY", "").strip()


def key():
    """Có AI không (Gemini hoặc OpenRouter)."""
    return gemini_key() or openrouter_key()


def openrouter_models():
    """Các model OpenRouter (hoặc nhà cung cấp AI_API_URL)."""
    return env_list("AI_MODEL", AI_MODELS)


def providers(vision=False):
    """[(tên, địa chỉ, key, các model)] theo thứ tự thử: Gemini trước, OpenRouter dự phòng.
    vision=True: model xem được ảnh."""
    out = []
    if gemini_key():
        out.append(("Gemini", GEMINI_URL, gemini_key(), env_list("GEMINI_MODEL", GEMINI_MODELS)))
    if openrouter_key():
        url = os.environ.get("AI_API_URL", AI_URL)
        models = env_list("AI_VISION_MODEL", AI_VISION_MODELS) if vision else openrouter_models()
        out.append(("OpenRouter" if "openrouter.ai" in url else "AI", url, openrouter_key(), models))
    return out


def post(payload, url=None, key_=None, timeout=AI_TIMEOUT):
    req = urllib.request.Request(url or os.environ.get("AI_API_URL", AI_URL), data=json.dumps(payload).encode(), headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {key_ or key()}", "X-Title": "ban-tin-sang"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = (e.read() or b"").decode(errors="replace")
        try:
            message = json.loads(body)["error"]["message"]
        except (ValueError, KeyError, TypeError):
            message = body[:200]
        raise RuntimeError(f"AI báo lỗi {e.code}: {message}") from None


def chat(system, user, max_tokens=2000, image=None, timeout=AI_TIMEOUT, budget=45):
    """Hỏi AI một lượt: (câu trả lời đã bỏ phần "suy nghĩ", model đã trả lời). Thử lần lượt từng nhà cung cấp,
    từng model; tất cả đều lỗi (mạng, bận, hết lượt...) thì báo lỗi. image=(bytes, kiểu ảnh) để gửi kèm ảnh.
    timeout: chờ mỗi model tối đa bao lâu; budget: tổng thời gian cho mọi lần thử (Vercel cắt hàm ở 60 giây)."""
    started = datetime.now()
    if image:
        data, mime = image
        user = [{"type": "text", "text": user}, {"type": "image_url", "image_url": {
            "url": f"data:{mime};base64,{base64.b64encode(data).decode()}"}}]
    errors = []
    for provider, url, key_, models in providers(vision=bool(image)):
        # OpenRouter tự chuyển model khi nhận danh sách "models"; nơi khác thì bot tự thử từng model
        tries = [(models[0], {"models": models})] if "openrouter.ai" in url and len(models) > 1 else \
            [(m, {}) for m in models]
        for model, extra in tries:
            left = budget - (datetime.now() - started).total_seconds()
            if left < 5:
                errors.append(f"{provider} {model}: hết thời gian chờ")
                continue
            payload = {
                # Model có "suy nghĩ" tiêu nhiều token trước khi trả lời; ít quá thì câu trả lời bị cắt rỗng
                "model": model, "temperature": 0, "max_tokens": max_tokens, **extra,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
            try:
                res = post(payload, url, key_, min(timeout, left))
                text = res["choices"][0]["message"].get("content") or ""
                return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip(), res.get("model", model)
            except Exception as e:
                print(f"[lỗi] AI {provider} {model}: {e!r}", file=sys.stderr)
                errors.append(f"{provider} {model}: {e}")
    raise RuntimeError("; ".join(errors) or "chưa bật AI (thiếu GEMINI_API_KEY hoặc AI_API_KEY)")


def first_json(text):
    """Đối tượng JSON đầu tiên trong câu trả lời của AI (bỏ qua chữ, khối ```json bao quanh)."""
    start = text.find("{")
    try:
        return json.JSONDecoder().raw_decode(text[start:])[0] if start >= 0 else None
    except ValueError:
        return None


def quota():
    """(đã dùng, giới hạn) lượt gọi model miễn phí hôm nay của key OpenRouter (không tốn lượt);
    None nếu không dùng OpenRouter. Lượt tính lại lúc 0h giờ quốc tế, tức 7h sáng ở Việt Nam."""
    if not openrouter_key() or "openrouter.ai" not in os.environ.get("AI_API_URL", AI_URL):
        return None
    req = urllib.request.Request("https://openrouter.ai/api/v1/key",
                                 headers={"Authorization": f"Bearer {openrouter_key()}"})
    with urllib.request.urlopen(req, timeout=10) as r:
        used = (json.loads(r.read())["data"].get("free_model_daily_requests") or {})
    return (used["used"], used["limit"]) if "used" in used and "limit" in used else None
