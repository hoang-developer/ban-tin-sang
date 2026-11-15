"""Máy khách AI (mạng giả): nhà cung cấp theo biến môi trường, thử lần lượt model, ảnh, lỗi HTTP, lượt dùng OpenRouter."""
import io
import json
import os
import unittest
import urllib.error
import urllib.request

from tests import harness as h

from infrastructure import ai

chat = h.REAL_AI_CHAT  # harness thay ai.chat bằng AI giả: dùng bản thật

ENV = ("GEMINI_API_KEY", "AI_API_KEY", "AI_API_URL", "AI_MODEL", "GEMINI_MODEL", "AI_VISION_MODEL")


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class May(unittest.TestCase):
    def setUp(self):
        self.saved_env = {k: os.environ.pop(k, None) for k in ENV}
        self.real = urllib.request.urlopen
        self.mode, self.log = "ok", []
        urllib.request.urlopen = self.fake
        self.addCleanup(self.restore)

    def restore(self):
        urllib.request.urlopen = self.real
        for k, v in self.saved_env.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v

    def fake(self, req, timeout=None):
        body = json.loads(req.data) if req.data else None
        self.log.append((req.full_url.split("/")[2], (body or {}).get("model"), (body or {}).get("models")))
        if "api/v1/key" in req.full_url:
            if self.mode == "quota401":
                raise urllib.error.HTTPError(req.full_url, 401, "x", {}, io.BytesIO(b"no"))
            return Resp(json.dumps({"data": {"free_model_daily_requests": {"used": 12, "limit": 50}}}).encode())
        if self.mode == "http429":
            raise urllib.error.HTTPError(req.full_url, 429, "x", {}, io.BytesIO(json.dumps({"error": {"message": "hết lượt"}}).encode()))
        if self.mode == "first_fail" and len(self.log) == 1:
            raise RuntimeError("mạng đứt")
        self.last_body = body
        return Resp(json.dumps({"model": "m-thật", "choices": [{"message": {"content": "<think>nghĩ</think> {\"1\": \"an\"} "}}]}).encode())

    def test_khong_co_key(self):
        self.assertEqual((ai.key(), ai.providers()), ("", []))
        with self.assertRaises(RuntimeError) as err:
            chat("s", "u")
        self.assertIn("chưa bật AI", str(err.exception))

    def test_nha_cung_cap(self):
        os.environ.update(GEMINI_API_KEY=" g ", AI_API_KEY="o", GEMINI_MODEL="a,b", AI_MODEL="x,y")
        providers = ai.providers()
        self.assertEqual([(p[0], p[3]) for p in providers], [("Gemini", ["a", "b"]), ("OpenRouter", ["x", "y"])])
        self.assertEqual(providers[0][2], "g")
        self.assertEqual(ai.providers(vision=True)[1][3], ["nvidia/nemotron-3.5-super-vl:free"])
        os.environ["AI_API_URL"] = "https://api.example.com/v1/chat"
        self.assertEqual(ai.providers()[1][0], "AI")  # không phải OpenRouter

    def test_hoi_va_bo_phan_suy_nghi(self):
        os.environ["GEMINI_API_KEY"] = "g"
        text, model = chat("hệ thống", "câu hỏi")
        self.assertEqual((text, model), ('{"1": "an"}', "m-thật"))
        self.assertEqual(self.last_body["messages"][0], {"role": "system", "content": "hệ thống"})
        self.assertEqual(self.log[0][1], "gemini-3.5-flash-lite")  # model đầu tiên

    def test_model_dau_loi_thi_thu_model_sau(self):
        os.environ["GEMINI_API_KEY"] = "g"
        self.mode = "first_fail"
        chat("s", "u")
        self.assertEqual([x[1] for x in self.log], ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"])

    def test_loi_http_va_openrouter_tu_chuyen_model(self):
        os.environ.update(GEMINI_API_KEY="g", AI_API_KEY="o", AI_MODEL="x,y")
        self.mode = "http429"
        with self.assertRaises(RuntimeError) as err:
            chat("s", "u")
        self.assertIn("AI báo lỗi 429: hết lượt", str(err.exception))
        hosts = [x[0] for x in self.log]
        self.assertEqual(hosts.count("generativelanguage.googleapis.com"), 3)  # thử hết model Gemini
        self.assertEqual(self.log[-1][2], ["x", "y"])  # OpenRouter nhận danh sách model một lần

    def test_gui_kem_anh(self):
        os.environ["GEMINI_API_KEY"] = "g"
        chat("s", "u", image=(b"abc", "image/png"))
        content = self.last_body["messages"][1]["content"]
        self.assertEqual(content[1]["image_url"]["url"], "data:image/png;base64,YWJj")

    def test_het_thoi_gian_cho(self):
        os.environ["GEMINI_API_KEY"] = "g"
        with self.assertRaises(RuntimeError) as err:
            chat("s", "u", budget=1)
        self.assertIn("hết thời gian chờ", str(err.exception))
        self.assertEqual(self.log, [])

    def test_luot_dung_openrouter(self):
        self.assertIsNone(ai.quota())
        os.environ["AI_API_KEY"] = "o"
        self.assertEqual(ai.quota(), (12, 50))
        os.environ["AI_API_URL"] = "https://api.example.com/v1/chat"
        self.assertIsNone(ai.quota())

    def test_doc_json(self):
        self.assertEqual(ai.first_json('x {"a": 1} y'), {"a": 1})
        self.assertEqual(ai.first_json('```json\n{"b": [1, 2]}\n```'), {"b": [1, 2]})
        for bad in ("không có", "{hỏng", ""):
            self.assertIsNone(ai.first_json(bad))
        self.assertEqual(ai.env_list("KHONG_CO_BIEN_NAY", " a, b ,,c "), ["a", "b", "c"])


if __name__ == "__main__":
    unittest.main()
