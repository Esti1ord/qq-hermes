"""Shared OpenAI-compatible chat/completions response helpers."""
from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit, urlunsplit


def normalize_chat_completions_url(base_url: str) -> str:
    raw = str(base_url or "").strip()
    if not raw:
        return ""
    parts = urlsplit(raw)
    path = parts.path.rstrip("/")
    if not path.lower().endswith("/chat/completions"):
        path = f"{path}/chat/completions" if path else "/chat/completions"
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


def extract_chat_text(payload: Any) -> str:
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
        return content_text(message.get("content"))
    return content_text(first.get("text"))


def content_text(content: Any) -> str:
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
