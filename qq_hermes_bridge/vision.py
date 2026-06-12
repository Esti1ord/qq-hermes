"""Vision/OCR provider abstractions for media recognition.

The fastest available implementation uses Hermes' existing ``chat --image``
support. Providers return ``MediaRecognition`` so bridge code can add recognized
image text to prompts/context without depending on a specific OCR backend.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any, Callable, Protocol
from urllib.parse import urlsplit, urlunsplit

import httpx

from .media import MediaRecognition
from .media_fetch import MediaFetchResult


DEFAULT_IMAGE_PROMPT = "请对这张图片做OCR，输出可见的主要文字内容和一句简短概括。不要编造看不清的内容。"


class VisionProvider(Protocol):
    name: str

    def recognize_image(self, image: MediaFetchResult, *, prompt: str = DEFAULT_IMAGE_PROMPT) -> MediaRecognition:
        """Recognize one fetched image and return structured OCR/description text."""


@dataclass(frozen=True)
class NoopVisionProvider:
    name: str = "none"

    def recognize_image(self, image: MediaFetchResult, *, prompt: str = DEFAULT_IMAGE_PROMPT) -> MediaRecognition:
        return MediaRecognition(index=image.ref.index, type=image.ref.type, status="skipped", provider=self.name, error="ocr_disabled")


@dataclass(frozen=True)
class MockVisionProvider:
    text: str = ""
    description: str = ""
    status: str = "ok"
    name: str = "mock"

    def recognize_image(self, image: MediaFetchResult, *, prompt: str = DEFAULT_IMAGE_PROMPT) -> MediaRecognition:
        return MediaRecognition(
            index=image.ref.index,
            type=image.ref.type,
            status=self.status,
            text=self.text,
            description=self.description,
            provider=self.name,
            error="" if self.status == "ok" else self.status,
        )


@dataclass(frozen=True)
class ModelVisionProvider:
    """OpenAI-compatible model vision provider.

    ``api_key_env`` is the name of the environment variable containing the API
    key. The key value is read at call time and never included in return errors.
    """

    base_url: str
    model: str
    api_key_env: str
    timeout: float = 60.0
    max_result_chars: int = 1200
    transport: httpx.BaseTransport | None = None
    name: str = "model"

    def recognize_image(self, image: MediaFetchResult, *, prompt: str = DEFAULT_IMAGE_PROMPT) -> MediaRecognition:
        if image.status != "ok":
            return MediaRecognition(index=image.ref.index, type=image.ref.type, status="error", provider=self.name, error=image.error or image.status)
        if not image.content:
            return MediaRecognition(index=image.ref.index, type=image.ref.type, status="error", provider=self.name, error="empty_image")

        url = normalize_chat_completions_url(self.base_url)
        if not url:
            return MediaRecognition(index=image.ref.index, type=image.ref.type, status="error", provider=self.name, error="missing_base_url")
        if not str(self.model or "").strip():
            return MediaRecognition(index=image.ref.index, type=image.ref.type, status="error", provider=self.name, error="missing_model")
        api_key_env = str(self.api_key_env or "").strip()
        if not api_key_env:
            return MediaRecognition(index=image.ref.index, type=image.ref.type, status="error", provider=self.name, error="missing_api_key_env")
        api_key = os.getenv(api_key_env, "").strip()
        if not api_key:
            return MediaRecognition(index=image.ref.index, type=image.ref.type, status="error", provider=self.name, error="missing_api_key")

        body = build_openai_compatible_vision_request(
            model=str(self.model).strip(),
            prompt=prompt,
            image=image,
            max_result_chars=self.max_result_chars,
        )
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        try:
            with httpx.Client(timeout=self.timeout, trust_env=False, transport=self.transport) as client:
                response = client.post(url, headers=headers, json=body)
        except httpx.TimeoutException:
            return MediaRecognition(index=image.ref.index, type=image.ref.type, status="error", provider=self.name, error="timeout")
        except httpx.HTTPError:
            return MediaRecognition(index=image.ref.index, type=image.ref.type, status="error", provider=self.name, error="http_error")
        except Exception as exc:
            return MediaRecognition(index=image.ref.index, type=image.ref.type, status="error", provider=self.name, error=type(exc).__name__)

        if response.status_code < 200 or response.status_code >= 300:
            return MediaRecognition(index=image.ref.index, type=image.ref.type, status="error", provider=self.name, error="http_status")

        try:
            payload = response.json()
        except ValueError:
            return MediaRecognition(index=image.ref.index, type=image.ref.type, status="error", provider=self.name, error="invalid_json")

        text = extract_openai_compatible_text(payload)
        if not text:
            return MediaRecognition(index=image.ref.index, type=image.ref.type, status="error", provider=self.name, error="malformed_response")
        return MediaRecognition(
            index=image.ref.index,
            type=image.ref.type,
            status="ok",
            text=clip_result(text, self.max_result_chars),
            provider=self.name,
        )


@dataclass(frozen=True)
class HermesVisionProvider:
    hermes_bin: str
    model: str = ""
    provider: str = ""
    timeout: float = 60.0
    max_result_chars: int = 1200
    cwd: Path | None = None
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run
    name: str = "hermes"

    def recognize_image(self, image: MediaFetchResult, *, prompt: str = DEFAULT_IMAGE_PROMPT) -> MediaRecognition:
        if image.status != "ok":
            return MediaRecognition(index=image.ref.index, type=image.ref.type, status="error", provider=self.name, error=image.error or image.status)
        if not image.content:
            return MediaRecognition(index=image.ref.index, type=image.ref.type, status="error", provider=self.name, error="empty_image")

        suffix = _suffix_for_content_type(image.content_type)
        temp_path = ""
        try:
            with tempfile.NamedTemporaryFile(prefix="qq-hermes-ocr-", suffix=suffix, delete=False) as tmp:
                tmp.write(image.content)
                temp_path = tmp.name
            cmd = [self.hermes_bin, "chat", "-q", prompt, "--image", temp_path, "--quiet"]
            if self.model:
                cmd.extend(["--model", self.model])
            if self.provider:
                cmd.extend(["--provider", self.provider])
            result = self.runner(
                cmd,
                text=True,
                capture_output=True,
                timeout=self.timeout,
                cwd=str(self.cwd) if self.cwd else None,
            )
        except subprocess.TimeoutExpired:
            return MediaRecognition(index=image.ref.index, type=image.ref.type, status="error", provider=self.name, error="TimeoutExpired")
        except FileNotFoundError:
            return MediaRecognition(index=image.ref.index, type=image.ref.type, status="error", provider=self.name, error="FileNotFoundError")
        except Exception as exc:
            return MediaRecognition(index=image.ref.index, type=image.ref.type, status="error", provider=self.name, error=type(exc).__name__)
        finally:
            if temp_path:
                try:
                    Path(temp_path).unlink(missing_ok=True)
                except Exception:
                    pass

        output = clean_hermes_vision_output(result.stdout or "")
        if result.returncode != 0:
            return MediaRecognition(
                index=image.ref.index,
                type=image.ref.type,
                status="error",
                provider=self.name,
                error=f"returncode:{result.returncode}",
                description=clean_hermes_vision_output(result.stderr or "")[: self.max_result_chars],
            )
        return MediaRecognition(
            index=image.ref.index,
            type=image.ref.type,
            status="ok",
            text=clip_result(output, self.max_result_chars),
            provider=self.name,
        )


OPENAI_COMPATIBLE_PROVIDER_ALIASES = {
    "model",
    "model_vision",
    "openai",
    "openai_compatible",
    "openai-gpt",
    "custom",
    "axonhub",
    "siliconflow",
    "silicon-flow",
}


def build_vision_provider(
    provider: str,
    *,
    hermes_bin: str,
    model: str = "",
    hermes_provider: str = "",
    base_url: str = "",
    api_key_env: str = "",
    timeout: float = 60.0,
    max_result_chars: int = 1200,
    cwd: Path | None = None,
    transport: httpx.BaseTransport | None = None,
) -> VisionProvider:
    name = str(provider or "none").strip().lower()
    if name in {"hermes", "hermes_vision", "vision"}:
        return HermesVisionProvider(
            hermes_bin=hermes_bin,
            model=model,
            provider=hermes_provider,
            timeout=timeout,
            max_result_chars=max_result_chars,
            cwd=cwd,
        )
    if name in OPENAI_COMPATIBLE_PROVIDER_ALIASES:
        return ModelVisionProvider(
            base_url=base_url,
            model=model,
            api_key_env=api_key_env,
            timeout=timeout,
            max_result_chars=max_result_chars,
            transport=transport,
        )
    if name == "mock":
        return MockVisionProvider(text="mock ocr result")
    return NoopVisionProvider()


def build_openai_compatible_vision_request(
    *,
    model: str,
    prompt: str,
    image: MediaFetchResult,
    max_result_chars: int,
) -> dict[str, Any]:
    content_type = _data_url_content_type(image.content_type)
    encoded = base64.b64encode(image.content).decode("ascii")
    return {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": str(prompt or DEFAULT_IMAGE_PROMPT)},
                    {"type": "image_url", "image_url": {"url": f"data:{content_type};base64,{encoded}"}},
                ],
            }
        ],
        "max_tokens": max_tokens_for_result_chars(max_result_chars),
    }


def normalize_chat_completions_url(base_url: str) -> str:
    raw = str(base_url or "").strip()
    if not raw:
        return ""
    parts = urlsplit(raw)
    path = parts.path.rstrip("/")
    if not path.lower().endswith("/chat/completions"):
        path = f"{path}/chat/completions" if path else "/chat/completions"
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


def extract_openai_compatible_text(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if isinstance(message, dict):
        return _content_text(message.get("content"))
    return _content_text(first.get("text"))


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                value = item.strip()
            elif isinstance(item, dict):
                raw_text = item.get("text")
                if isinstance(raw_text, str):
                    value = raw_text.strip()
                elif isinstance(raw_text, dict) and isinstance(raw_text.get("value"), str):
                    value = str(raw_text.get("value") or "").strip()
                else:
                    value = ""
            else:
                value = ""
            if value:
                parts.append(value)
        return "\n".join(parts).strip()
    return ""


def max_tokens_for_result_chars(max_chars: int) -> int:
    try:
        chars = int(max_chars)
    except (TypeError, ValueError):
        chars = 1200
    if chars <= 0:
        return 1024
    return max(64, min(4096, int(chars * 0.75) + 64))


def clean_hermes_vision_output(text: str) -> str:
    lines = []
    for line in str(text or "").splitlines():
        if line.strip().startswith("session_id:"):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def clip_result(text: str, max_chars: int) -> str:
    clean = str(text or "").strip()
    if max_chars > 0 and len(clean) > max_chars:
        return clean[:max_chars].rstrip() + "…"
    return clean


def _suffix_for_content_type(content_type: str) -> str:
    normalized = str(content_type or "").split(";", 1)[0].strip().lower()
    if normalized == "image/jpeg":
        return ".jpg"
    if normalized == "image/webp":
        return ".webp"
    if normalized == "image/gif":
        return ".gif"
    return ".png"


def _data_url_content_type(content_type: str) -> str:
    normalized = str(content_type or "").split(";", 1)[0].strip().lower()
    if normalized.startswith("image/"):
        return normalized
    return "image/png"
