"""Structured media parsing helpers for OneBot messages.

The bridge keeps ``onebot.message_to_text`` as the stable plain-text fallback
(``[图片]`` for images). This module extracts opaque media references alongside
that fallback so future OCR/image-recognition code can opt in without changing
normal message routing or context behavior.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


_CQ_CODE_RE = re.compile(r"\[CQ:(?P<type>[^,\]]+)(?P<params>(?:,[^\]]*)?)\]")


@dataclass(frozen=True)
class MediaRef:
    """Opaque reference to media carried by a OneBot message segment.

    ``file_id`` and ``url`` are intentionally treated as untrusted identifiers.
    Callers should not log them raw and should only pass them to a constrained
    fetch layer when OCR/image recognition is explicitly enabled.
    """

    index: int
    type: str
    file_id: str = ""
    url: str = ""
    summary: str = ""
    sub_type: str = ""
    raw_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class MediaRecognition:
    """Result of an OCR/image-recognition attempt for one media reference."""

    index: int
    type: str
    status: str
    text: str = ""
    description: str = ""
    provider: str = ""
    error: str = ""


def _cq_unescape(value: str) -> str:
    return (
        str(value or "")
        .replace("&#44;", ",")
        .replace("&#91;", "[")
        .replace("&#93;", "]")
        .replace("&amp;", "&")
    )


def _parse_cq_params(raw: str) -> dict[str, str]:
    params: dict[str, str] = {}
    for item in str(raw or "").lstrip(",").split(","):
        if not item or "=" not in item:
            continue
        key, value = item.split("=", 1)
        key = key.strip()
        if key:
            params[key] = _cq_unescape(value.strip())
    return params


def _media_ref_from_data(index: int, typ: str, data: dict[str, Any]) -> MediaRef:
    return MediaRef(
        index=index,
        type=typ,
        file_id=str(data.get("file") or data.get("file_id") or data.get("id") or ""),
        url=str(data.get("url") or ""),
        summary=str(data.get("summary") or data.get("title") or ""),
        sub_type=str(data.get("sub_type") or data.get("subType") or data.get("subtype") or ""),
        raw_keys=tuple(sorted(str(key) for key in data.keys())),
    )


def extract_media_refs(message: Any, *, max_refs: int | None = None) -> list[MediaRef]:
    """Extract image media references from OneBot segment arrays or CQ strings.

    The returned references preserve message order. Only image media is exposed
    for now because OCR/image recognition is the planned first consumer; other
    segment types can be added later without changing the fallback text parser.
    """
    refs: list[MediaRef] = []

    def append(ref: MediaRef) -> None:
        if max_refs is not None and len(refs) >= max_refs:
            return
        refs.append(ref)

    if isinstance(message, list):
        for seg in message:
            if max_refs is not None and len(refs) >= max_refs:
                break
            if not isinstance(seg, dict) or seg.get("type") != "image":
                continue
            data = seg.get("data") or {}
            if not isinstance(data, dict):
                data = {}
            append(_media_ref_from_data(len(refs), "image", data))
        return refs

    if isinstance(message, str):
        for match in _CQ_CODE_RE.finditer(message):
            if max_refs is not None and len(refs) >= max_refs:
                break
            typ = match.group("type")
            if typ != "image":
                continue
            append(_media_ref_from_data(len(refs), "image", _parse_cq_params(match.group("params"))))
    return refs


def has_processable_media(message: Any) -> bool:
    """Return whether a message contains at least one extractable media ref."""
    return bool(extract_media_refs(message, max_refs=1))


def format_media_context(results: list[MediaRecognition], *, max_chars: int, include_failures: bool = True) -> str:
    """Format recognition results as a prompt-safe Chinese context block."""
    lines: list[str] = []
    for result in results:
        label = f"图片{result.index + 1}"
        if result.status == "ok":
            detail_parts = []
            if result.text:
                detail_parts.append(f"文字：{result.text}")
            if result.description:
                detail_parts.append(f"描述：{result.description}")
            detail = "；".join(detail_parts).strip()
            lines.append(f"- {label}：{detail or '识别完成但没有可用文本/描述'}")
        elif include_failures and result.status == "skipped":
            lines.append(f"- {label}：未识别")
        elif include_failures:
            lines.append(f"- {label}：识别失败")
    text = "\n".join(lines).strip()
    if not text:
        return "（当前消息没有图片识别结果）"
    if max_chars > 0 and len(text) > max_chars:
        return text[:max_chars].rstrip() + "…"
    return text


def merge_text_and_media_context(user_text: str, media_context: str) -> str:
    """Combine original user text with formatted media context for optional use."""
    base = str(user_text or "").strip()
    media = str(media_context or "").strip()
    if not media or media == "（当前消息没有图片识别结果）":
        return base
    if not base:
        return media
    return f"{base}\n{media}"
