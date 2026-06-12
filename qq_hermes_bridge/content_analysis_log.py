"""Opt-in contentful chat analysis logging helpers.

Unlike runtime_stats, this module may preserve bounded chat text and bot replies
for local qualitative behavior analysis. It is intentionally separate from the
content-safe statistics stream and applies best-effort redaction for obvious
secrets before writing JSONL.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Iterable

SECRET_KEY_FRAGMENTS = {
    "authorization",
    "headers",
    "cookie",
    "token",
    "access_token",
    "api_key",
    "apikey",
    "secret",
    "password",
    "passwd",
    "qr",
    "qrcode",
    "raw_event",
    "prompt",
    "stdout",
    "stderr",
    "response",
}

TEXT_REDACTIONS = [
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"(?i)\b(authorization\s*[:=]\s*)\S+"),
    re.compile(r"(?i)\b(cookie|set-cookie)\s*[:=]\s*[^\s]+"),
    re.compile(r"(?i)\b(access[_-]?token|api[_-]?key|secret|password|passwd|token)\s*[:=]\s*[^\s&]+"),
    re.compile(r"(?i)\b(qr|qrcode)\s*[:=]\s*[^\s]+"),
    re.compile(r"(?i)https?://\S*(?:qr|qrcode|login|token|cookie|ticket)\S*"),
    re.compile(r"\b[A-Za-z0-9_\-]{32,}\b"),
]

MESSAGE_ID_KEYS = ("message_id", "id", "message_seq", "real_id")
SAFE_CONTEXT_KEYS = {"user_id", "name", "role", "text", *MESSAGE_ID_KEYS}
SAFE_LABEL_KEYS = {
    "type",
    "kind",
    "group_id",
    "user_id",
    "sender",
    "message_id",
    "trigger",
    "log_type",
    "reason",
    "score",
    "direct_name_trigger",
    "generation_failed",
    "failure_notice_sent",
    "queue_size",
    "queue_remaining",
    "truncated",
    "chars",
    "redacted_chars",
}


def enabled_from_env(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def parse_group_ids(raw: str) -> set[int]:
    ids: set[int] = set()
    for part in str(raw or "").replace(";", ",").split(","):
        item = part.strip()
        if not item:
            continue
        try:
            ids.add(int(item))
        except ValueError:
            continue
    return ids


def _is_forbidden_key(key: Any) -> bool:
    lowered = str(key or "").strip().lower()
    return any(fragment in lowered for fragment in SECRET_KEY_FRAGMENTS)


def redact_text(text: str) -> str:
    redacted = str(text or "")
    for pattern in TEXT_REDACTIONS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def sanitize_text(text: Any, max_chars: int) -> dict[str, Any]:
    raw = "" if text is None else str(text)
    redacted = redact_text(raw)
    limit = max(0, int(max_chars or 0))
    truncated = len(redacted) > limit
    if truncated:
        redacted = redacted[:limit]
    return {
        "text": redacted,
        "chars": len(raw),
        "redacted_chars": len(redacted),
        "truncated": truncated,
    }


def _looks_like_sanitized_text(value: dict[str, Any]) -> bool:
    return {"text", "chars", "redacted_chars", "truncated"}.issubset(value.keys())


def sanitize_record(value: Any, *, max_chars: int, _depth: int = 0) -> Any:
    if _depth > 8:
        return "[MAX_DEPTH]"
    if isinstance(value, str):
        return sanitize_text(value, max_chars)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [sanitize_record(item, max_chars=max_chars, _depth=_depth + 1) for item in value[:50]]
    if isinstance(value, dict):
        if _looks_like_sanitized_text(value):
            return value
        out: dict[str, Any] = {}
        for key, item in value.items():
            if _is_forbidden_key(key):
                continue
            clean_key = str(key)[:80]
            if clean_key in SAFE_LABEL_KEYS and isinstance(item, (str, int, float, bool, type(None))):
                out[clean_key] = item
            else:
                out[clean_key] = sanitize_record(item, max_chars=max_chars, _depth=_depth + 1)
        return out
    return sanitize_text(str(type(value).__name__), max_chars)


def _context_item_snapshot(item: dict[str, Any], *, max_chars: int) -> dict[str, Any]:
    snap: dict[str, Any] = {}
    for key in SAFE_CONTEXT_KEYS:
        if key not in item:
            continue
        if key == "text":
            snap[key] = sanitize_text(item.get(key), max_chars)
        else:
            snap[key] = sanitize_record(item.get(key), max_chars=max_chars)
    return snap


def context_snapshot(
    messages: Iterable[dict[str, Any]],
    summaries: Iterable[str] = (),
    *,
    max_messages: int,
    max_chars: int,
    include_summaries: bool = True,
) -> dict[str, Any]:
    message_list = list(messages)
    visible = message_list[-max(0, int(max_messages or 0)) :]
    snapshot: dict[str, Any] = {
        "message_count_total": len(message_list),
        "message_count_included": len(visible),
        "messages": [_context_item_snapshot(item, max_chars=max_chars) for item in visible],
    }
    if include_summaries:
        summary_list = list(summaries)
        snapshot["summary_count_total"] = len(summary_list)
        snapshot["summaries"] = [sanitize_text(summary, max_chars) for summary in summary_list[-max(0, int(max_messages or 0)) :]]
    return snapshot


def json_log_line(record: dict[str, Any], *, now_fn=time.strftime) -> str:
    return json.dumps({"ts": now_fn("%Y-%m-%d %H:%M:%S"), "event": record}, ensure_ascii=False)


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existed = path.exists()
    line = json_log_line(record)
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    if not existed:
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
