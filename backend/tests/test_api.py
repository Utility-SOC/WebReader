import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

def test_read_main():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "WebReader API", "version": "1.0"}

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "running"}


def _tiny_pdf(text: str) -> bytes:
    """Hand-built one-page 200x200 PDF with `text` at the top-left (no extra deps)."""
    stream = f"BT /F1 8 Tf 10 170 Td ({text}) Tj ET"
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = "%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n"
    out += "".join(f"{off:010d} 00000 n \n" for off in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF"
    return out.encode("latin-1")


def test_box_text_preview(tmp_path):
    from backend.utils import box_text_preview
    pdf = tmp_path / "t.pdf"
    pdf.write_bytes(_tiny_pdf("alpha beta gamma delta epsilon zeta"))
    # Relative box covering the top strip of the page, where the text sits
    res = box_text_preview(str(pdf), 0, {"x": 0, "y": 0, "w": 1, "h": 0.3, "relative": True}, n=2)
    assert res["word_count"] == 6
    assert res["first"] == "alpha beta"
    assert res["last"] == "epsilon zeta"
    # Out-of-range page is rejected
    with pytest.raises(IndexError):
        box_text_preview(str(pdf), 3, {"x": 0, "y": 0, "w": 1, "h": 1, "relative": True})


# ---- AI provider selection (no network: requests.post is stubbed) ----

class _Resp:
    def __init__(self, body, status=200):
        self._b, self.status_code, self.text = body, status, str(body)

    def json(self):
        return self._b


def _img():
    from PIL import Image
    return Image.new("RGB", (40, 30), "white")


@pytest.fixture
def captured(monkeypatch):
    from backend import providers
    class Calls(list):
        post = None

    calls = Calls()

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append({"url": url, "headers": headers, "json": json})
        return fake_post.reply

    fake_post.reply = _Resp({})
    monkeypatch.setattr(providers.requests, "post", fake_post)
    monkeypatch.setenv("WEBREADER_LLM_API_KEY", "sk-secret")
    monkeypatch.setenv("WEBREADER_LLM_MODEL", "m1")
    monkeypatch.delenv("WEBREADER_LLM_BASE_URL", raising=False)
    calls.post = fake_post
    return calls


def test_openai_compatible_request_and_parse(captured, monkeypatch):
    from backend import providers
    monkeypatch.setenv("WEBREADER_CAPTION_PROVIDER", "kimi")
    captured.post.reply = _Resp({"choices": [{"message": {"content": " A bar chart. "}}]})
    assert providers.caption_via_api(_img()) == "A bar chart."
    c = captured[0]
    assert c["url"] == "https://api.moonshot.ai/v1/chat/completions"
    assert c["headers"]["Authorization"] == "Bearer sk-secret"
    assert c["json"]["model"] == "m1"
    assert c["json"]["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_custom_provider_needs_base_url_and_uses_it(captured, monkeypatch):
    from backend import providers
    monkeypatch.setenv("WEBREADER_CAPTION_PROVIDER", "custom")
    with pytest.raises(providers.ProviderConfigError):
        providers.caption_via_api(_img())
    monkeypatch.setenv("WEBREADER_LLM_BASE_URL", "http://localhost:11434/v1/")
    captured.post.reply = _Resp({"choices": [{"message": {"content": "ok"}}]})
    providers.caption_via_api(_img())
    assert captured[0]["url"] == "http://localhost:11434/v1/chat/completions"


def test_anthropic_native(captured, monkeypatch):
    from backend import providers
    monkeypatch.setenv("WEBREADER_CAPTION_PROVIDER", "anthropic")
    captured.post.reply = _Resp({"content": [{"type": "text", "text": "A dog."}]})
    assert providers.caption_via_api(_img()) == "A dog."
    c = captured[0]
    assert c["url"] == "https://api.anthropic.com/v1/messages"
    assert c["headers"]["x-api-key"] == "sk-secret" and "anthropic-version" in c["headers"]
    assert c["json"]["messages"][0]["content"][0]["source"]["type"] == "base64"


def test_gemini_native_key_in_header_not_url(captured, monkeypatch):
    from backend import providers
    monkeypatch.setenv("WEBREADER_CAPTION_PROVIDER", "gemini")
    captured.post.reply = _Resp({"candidates": [{"content": {"parts": [{"text": "A tree."}]}}]})
    assert providers.caption_via_api(_img()) == "A tree."
    c = captured[0]
    assert c["url"].endswith("/models/m1:generateContent") and "sk-secret" not in c["url"]
    assert c["headers"]["x-goog-api-key"] == "sk-secret"


def test_caption_image_degrades_without_leaking_key(captured, monkeypatch, caplog):
    from backend import captioning
    monkeypatch.setenv("WEBREADER_CAPTION_PROVIDER", "openai")
    captured.post.reply = _Resp("boom", status=401)
    with caplog.at_level("ERROR"):
        assert captioning.caption_image(_img()) == ""
    assert "401" in caplog.text and "sk-secret" not in caplog.text


def test_none_and_unknown_provider_never_call_out(captured, monkeypatch):
    from backend import captioning
    for name in ("none", "bogus"):
        monkeypatch.setenv("WEBREADER_CAPTION_PROVIDER", name)
        assert captioning.caption_image(_img()) == ""
    assert captured == []


def test_ai_status_hides_key(monkeypatch):
    monkeypatch.setenv("WEBREADER_CAPTION_PROVIDER", "openai")
    monkeypatch.setenv("WEBREADER_LLM_API_KEY", "sk-secret")
    monkeypatch.setenv("WEBREADER_LLM_MODEL", "m1")
    body = client.get("/ai/status").json()
    assert body == {"caption_provider": "openai", "sends_images_off_machine": True, "model": "m1", "api_key_set": True}
    assert "sk-secret" not in str(body)
