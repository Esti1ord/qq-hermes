"""Vision/OCR provider abstractions for media recognition.

The fastest available implementation uses Hermes' existing ``chat --image``
support. Providers return ``MediaRecognition`` so bridge code can add recognized
image text to prompts/context without depending on a specific OCR backend.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
import tempfile
from typing import Callable, Protocol

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


def build_vision_provider(
    provider: str,
    *,
    hermes_bin: str,
    model: str = "",
    hermes_provider: str = "",
    timeout: float = 60.0,
    max_result_chars: int = 1200,
    cwd: Path | None = None,
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
    if name == "mock":
        return MockVisionProvider(text="mock ocr result")
    return NoopVisionProvider()


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
