"""
Pluggable AI backends for WebReader (currently: image captioning).

Selected at setup time with environment variables, so the same code serves the
desktop script, Docker Compose and Kubernetes:

  WEBREADER_CAPTION_PROVIDER  local (default) | none | openai | deepseek | kimi
                              | custom | gemini | anthropic
  WEBREADER_LLM_API_KEY       API key for the chosen provider (never logged)
  WEBREADER_LLM_MODEL         model name -- must accept images
  WEBREADER_LLM_BASE_URL      override / required for `custom`
  WEBREADER_LLM_TIMEOUT       seconds per request (default 60)

`local` runs Florence-2 on this machine (see captioning.py); nothing leaves it.
Every other provider sends the image to that third party -- the setup script
says so before it asks for a key.

openai / deepseek / kimi / custom speak the OpenAI chat-completions protocol
(one implementation, different base URLs). gemini and anthropic use their own
native APIs. Only plain `requests` is needed, so the lightweight desktop
install stays lightweight.
"""

import base64
import io
import logging
import os
from typing import Optional

import requests
from PIL import Image

logger = logging.getLogger("SpeedReaderUtils")

# Protocol "openai" = POST {base}/chat/completions with a Bearer key.
OPENAI_COMPATIBLE_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "kimi": "https://api.moonshot.ai/v1",
    "custom": "",  # WEBREADER_LLM_BASE_URL is required
}
NATIVE_PROVIDERS = {"gemini", "anthropic"}
LOCAL_PROVIDERS = {"local", "none"}
ALL_PROVIDERS = LOCAL_PROVIDERS | set(OPENAI_COMPATIBLE_BASE_URLS) | NATIVE_PROVIDERS

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
ANTHROPIC_BASE_URL = "https://api.anthropic.com/v1"
ANTHROPIC_VERSION = "2023-06-01"

MAX_IMAGE_SIDE = 1024
CAPTION_PROMPT = (
    "Describe this image for a blind reader in one or two plain sentences. "
    "State what it shows and any text or numbers in it. No preamble."
)


class ProviderConfigError(RuntimeError):
    """The selected provider is missing something it needs (key, model, URL)."""


def caption_provider() -> str:
    name = os.environ.get("WEBREADER_CAPTION_PROVIDER", "local").strip().lower() or "local"
    if name not in ALL_PROVIDERS:
        logger.error(
            f"Unknown WEBREADER_CAPTION_PROVIDER '{name}' "
            f"(expected one of: {', '.join(sorted(ALL_PROVIDERS))}); captioning disabled."
        )
        return "none"
    return name


def status() -> dict:
    """Non-secret view of the current configuration (safe to show in a UI)."""
    name = caption_provider()
    return {
        "caption_provider": name,
        "sends_images_off_machine": name not in LOCAL_PROVIDERS,
        "model": os.environ.get("WEBREADER_LLM_MODEL", "") if name not in LOCAL_PROVIDERS else "",
        "api_key_set": bool(os.environ.get("WEBREADER_LLM_API_KEY")),
    }


def _settings(provider: str):
    key = os.environ.get("WEBREADER_LLM_API_KEY", "").strip()
    model = os.environ.get("WEBREADER_LLM_MODEL", "").strip()
    base = os.environ.get("WEBREADER_LLM_BASE_URL", "").strip().rstrip("/")
    timeout = float(os.environ.get("WEBREADER_LLM_TIMEOUT", "60"))
    if not key:
        raise ProviderConfigError(f"{provider}: WEBREADER_LLM_API_KEY is not set")
    if not model:
        raise ProviderConfigError(f"{provider}: WEBREADER_LLM_MODEL is not set (pick a vision-capable model)")
    return key, model, base, timeout


def _encode(image: Image.Image) -> str:
    img = image.convert("RGB")
    if max(img.size) > MAX_IMAGE_SIDE:
        img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _post(url: str, headers: dict, payload: dict, timeout: float) -> dict:
    resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    if resp.status_code >= 400:
        # Body can explain "model doesn't support images" etc.; never include headers (they hold the key).
        raise RuntimeError(f"HTTP {resp.status_code} from {url.split('?')[0]}: {resp.text[:200]}")
    return resp.json()


def _caption_openai_compatible(image: Image.Image, provider: str) -> str:
    key, model, base, timeout = _settings(provider)
    base = base or OPENAI_COMPATIBLE_BASE_URLS[provider]
    if not base:
        raise ProviderConfigError(f"{provider}: WEBREADER_LLM_BASE_URL is required")
    data = _post(
        f"{base}/chat/completions",
        {"Authorization": f"Bearer {key}"},
        {
            "model": model,
            "max_tokens": 200,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": CAPTION_PROMPT},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{_encode(image)}"}},
                ],
            }],
        },
        timeout,
    )
    return (data["choices"][0]["message"]["content"] or "").strip()


def _caption_anthropic(image: Image.Image) -> str:
    key, model, base, timeout = _settings("anthropic")
    data = _post(
        f"{base or ANTHROPIC_BASE_URL}/messages",
        {"x-api-key": key, "anthropic-version": ANTHROPIC_VERSION},
        {
            "model": model,
            "max_tokens": 200,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": _encode(image)}},
                    {"type": "text", "text": CAPTION_PROMPT},
                ],
            }],
        },
        timeout,
    )
    return "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text").strip()


def _caption_gemini(image: Image.Image) -> str:
    key, model, base, timeout = _settings("gemini")
    data = _post(
        f"{base or GEMINI_BASE_URL}/models/{model}:generateContent",
        {"x-goog-api-key": key},  # header, not ?key=, so it can't leak into logged URLs
        {
            "contents": [{
                "parts": [
                    {"text": CAPTION_PROMPT},
                    {"inline_data": {"mime_type": "image/jpeg", "data": _encode(image)}},
                ],
            }],
            "generationConfig": {"maxOutputTokens": 200},
        },
        timeout,
    )
    parts = data["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in parts).strip()


def caption_via_api(image: Image.Image, provider: Optional[str] = None) -> str:
    """Caption with a remote provider. Raises on any failure (caller decides how to degrade)."""
    provider = provider or caption_provider()
    if provider in OPENAI_COMPATIBLE_BASE_URLS:
        return _caption_openai_compatible(image, provider)
    if provider == "anthropic":
        return _caption_anthropic(image)
    if provider == "gemini":
        return _caption_gemini(image)
    raise ProviderConfigError(f"{provider} is not a remote captioning provider")
