"""Constrained media fetch helpers for future OCR/image recognition.

This module fetches only media references that were extracted from OneBot image
segments. It does not write bytes to disk and returns structured failures so the
bridge can fall back to the existing ``[图片]`` behavior.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any
from urllib.parse import urlparse

import httpx

from .media import MediaRef


@dataclass(frozen=True)
class MediaFetchResult:
    """Result of fetching bytes for a media reference."""

    ref: MediaRef
    status: str
    content: bytes = b""
    content_type: str = ""
    source_host: str = ""
    status_code: int = 0
    error: str = ""


_ALLOWED_SCHEMES = {"http", "https"}


def safe_url_host(url: str) -> str:
    """Return only the hostname for log-safe URL summaries."""
    try:
        return urlparse(str(url or "")).hostname or ""
    except Exception:
        return ""


def short_hash(value: str, *, length: int = 12) -> str:
    """Return a short deterministic hash for opaque ids in logs/tests."""
    if not value:
        return ""
    return hashlib.sha1(value.encode("utf-8", errors="replace")).hexdigest()[:length]


def media_ref_log_summary(ref: MediaRef, *, include_url: bool = False) -> dict[str, Any]:
    """Build a redacted summary for logs without exposing full URL/file id."""
    summary: dict[str, Any] = {
        "type": ref.type,
        "index": ref.index,
        "has_file_id": bool(ref.file_id),
        "has_url": bool(ref.url),
        "file_id_hash": short_hash(ref.file_id),
        "url_host": safe_url_host(ref.url),
    }
    if include_url:
        summary["url"] = ref.url
    return summary


def _same_origin(left: str, right: str) -> bool:
    try:
        a = urlparse(left)
        b = urlparse(right)
    except Exception:
        return False
    return bool(a.scheme and b.scheme and a.scheme == b.scheme and a.netloc == b.netloc)


def _auth_headers_for_url(url: str, *, onebot_http_url: str, access_token: str) -> dict[str, str]:
    if access_token and onebot_http_url and _same_origin(url, onebot_http_url):
        return {"Authorization": f"Bearer {access_token}"}
    return {}


def _normalized_content_type(value: str) -> str:
    return str(value or "").split(";", 1)[0].strip().lower()


def _failure(ref: MediaRef, error: str, *, url: str = "", status_code: int = 0, content_type: str = "") -> MediaFetchResult:
    return MediaFetchResult(
        ref=ref,
        status="error",
        source_host=safe_url_host(url or ref.url),
        status_code=status_code,
        content_type=_normalized_content_type(content_type),
        error=error,
    )


async def fetch_onebot_image(
    ref: MediaRef,
    *,
    onebot_http_url: str,
    access_token: str = "",
    timeout: float,
    max_bytes: int,
    allowed_content_types: set[str],
    transport: httpx.AsyncBaseTransport | None = None,
) -> MediaFetchResult:
    """Fetch image bytes for a OneBot image reference under strict limits.

    The current implementation fetches a URL already present on the image
    segment. File-id-only resolution through OneBot/NapCat APIs is intentionally
    left as a later step because adapter behavior differs by deployment.
    """
    if ref.type != "image":
        return MediaFetchResult(ref=ref, status="skipped", error="unsupported_media_type")
    url = str(ref.url or "").strip()
    if not url:
        return MediaFetchResult(ref=ref, status="skipped", error="missing_url")

    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        return _failure(ref, "unsupported_url_scheme", url=url)
    if not parsed.netloc:
        return _failure(ref, "missing_url_host", url=url)
    if max_bytes <= 0:
        return _failure(ref, "invalid_max_bytes", url=url)

    normalized_allowed = {_normalized_content_type(x) for x in allowed_content_types if str(x or "").strip()}
    headers = _auth_headers_for_url(url, onebot_http_url=onebot_http_url, access_token=access_token)

    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            trust_env=False,
            follow_redirects=False,
            transport=transport,
        ) as client:
            async with client.stream("GET", url, headers=headers) as response:
                content_type = _normalized_content_type(response.headers.get("content-type", ""))
                if 300 <= response.status_code < 400:
                    return _failure(ref, "redirect_not_followed", url=url, status_code=response.status_code, content_type=content_type)
                if response.status_code >= 400:
                    return _failure(ref, "http_error", url=url, status_code=response.status_code, content_type=content_type)
                if normalized_allowed and content_type not in normalized_allowed:
                    return _failure(ref, "unsupported_content_type", url=url, status_code=response.status_code, content_type=content_type)
                declared_length = response.headers.get("content-length")
                try:
                    if declared_length is not None and int(declared_length) > max_bytes:
                        return _failure(ref, "max_bytes_exceeded", url=url, status_code=response.status_code, content_type=content_type)
                except ValueError:
                    pass

                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > max_bytes:
                        return _failure(ref, "max_bytes_exceeded", url=url, status_code=response.status_code, content_type=content_type)
                    chunks.append(chunk)
                content = b"".join(chunks)
                return MediaFetchResult(
                    ref=ref,
                    status="ok",
                    content=content,
                    content_type=content_type,
                    source_host=safe_url_host(url),
                    status_code=response.status_code,
                )
    except httpx.TimeoutException:
        return _failure(ref, "timeout", url=url)
    except httpx.HTTPError as exc:
        return _failure(ref, type(exc).__name__, url=url)
    except Exception as exc:
        return _failure(ref, type(exc).__name__, url=url)
