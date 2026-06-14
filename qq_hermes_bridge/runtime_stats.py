"""Content-safe runtime analytics helpers for QQ/Hermes bridge.

This module intentionally records labels, lengths, counters, statuses and hashes
only. Raw messages, replies, prompts, model output, tokens and responses should
not enter the runtime analytics stream.
"""
from __future__ import annotations

import hashlib
import time
from collections import Counter
from typing import Any, Callable

UNSAFE_FIELD_FRAGMENTS = {
    "message",
    "text",
    "reply",
    "prompt",
    "profile",
    "query",
    "ocr",
    "image_url",
    "url",
    "stdout",
    "stderr",
    "token",
    "cookie",
    "qr",
    "password",
    "secret",
    "authorization",
    "response",
}

SAFE_VALUE_TYPES = (str, int, float, bool, type(None))
SAFE_FIELD_NAMES = {
    "message_type",
    "reply_to_bot",
    "text_len",
    "text_len_bucket",
    "query_len",
    "query_len_bucket",
    "output_len_bucket",
    "result_len_bucket",
    "duration_bucket",
    "queue_wait_bucket",
    "e2e_bucket",
    "prompt_build_ms",
    "prompt_profile",
    "prompt_section_count",
    "prompt_truncated_count",
    "total_budget_chars",
    "total_truncated",
    "has_non_text",
    "segment_types",
    "ocr_enabled",
    "ocr_route",
    "ocr_status",
}
SAFE_LABEL_REPLACEMENTS = str.maketrans({" ": "_", "/": "_", "\\": "_", ":": "_"})


def enabled_from_env(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def safe_user_hash(user_id: Any, *, salt: str) -> str:
    raw = f"{salt}:{user_id}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def safe_hash(value: Any, *, salt: str, length: int = 16) -> str:
    raw = f"{salt}:{value}".encode("utf-8", errors="ignore")
    digest = hashlib.sha256(raw).hexdigest()
    return digest[: max(4, min(64, int(length or 16)))]


def safe_interaction_hash(parts: list[Any] | tuple[Any, ...], *, salt: str) -> str:
    raw = "\0".join(str(part) for part in parts if part not in (None, ""))
    return safe_hash(raw or "unknown", salt=salt, length=20)


def normalize_label(value: Any, *, default: str = "unknown", max_len: int = 48) -> str:
    label = str(value or default).strip().lower().translate(SAFE_LABEL_REPLACEMENTS)
    label = "".join(ch for ch in label if ch.isalnum() or ch in {"_", "-", "."})
    return (label or default)[:max(1, int(max_len or 48))]


def value_bucket(value: int | float, ranges: list[tuple[int | float, str]], *, overflow: str) -> str:
    n = max(0, float(value or 0))
    for upper, label in ranges:
        if n <= float(upper):
            return label
    return overflow


def duration_bucket(duration: int | float) -> str:
    return value_bucket(
        duration,
        [(0, "0ms"), (100, "1-100ms"), (500, "101-500ms"), (1000, "501-1000ms"), (3000, "1-3s"), (10000, "3-10s"), (30000, "10-30s")],
        overflow="30s+",
    )


def length_bucket(length: int | float) -> str:
    return value_bucket(
        length,
        [(0, "0"), (20, "1-20"), (80, "21-80"), (200, "81-200"), (500, "201-500"), (1200, "501-1200")],
        overflow="1200+",
    )


def text_len_bucket(length: int) -> str:
    return length_bucket(length)


def segment_type_counts(message: Any) -> dict[str, int]:
    if not isinstance(message, list):
        return {}
    counts: Counter[str] = Counter()
    for item in message:
        if isinstance(item, dict):
            typ = str(item.get("type") or "unknown")[:40]
        else:
            typ = "unknown"
        counts[typ] += 1
    return dict(counts)


def safe_event_record(
    event: dict[str, Any],
    *,
    message_to_text_fn: Callable[[Any], str],
    is_allowed_group_fn: Callable[[dict[str, Any]], bool],
    is_at_me_fn: Callable[[dict[str, Any]], bool],
    is_reply_to_me_fn: Callable[[dict[str, Any]], bool],
    user_hash_salt: str,
) -> dict[str, Any]:
    text = message_to_text_fn(event.get("message"))
    seg_counts = segment_type_counts(event.get("message"))
    user_id = event.get("user_id")
    return {
        "post_type": event.get("post_type"),
        "message_type": event.get("message_type"),
        "group_id": event.get("group_id"),
        "user_hash": safe_user_hash(user_id, salt=user_hash_salt) if user_id not in (None, "") else "",
        "allowed_group": bool(is_allowed_group_fn(event)),
        "has_at_bot": bool(is_at_me_fn(event)),
        "reply_to_bot": bool(is_reply_to_me_fn(event)),
        "text_len": len(text or ""),
        "text_len_bucket": text_len_bucket(len(text or "")),
        "segment_types": seg_counts,
        "has_non_text": any(k != "text" for k in seg_counts),
    }


def duration_ms(start: float, end: float | None = None) -> int:
    finish = time.monotonic() if end is None else end
    return max(0, int((finish - start) * 1000))


def _field_is_unsafe(clean_key: str) -> bool:
    lowered = clean_key.lower()
    if clean_key in SAFE_FIELD_NAMES:
        return False
    return any(fragment in lowered for fragment in UNSAFE_FIELD_FRAGMENTS)


def _sanitize_dict(value: dict[Any, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, item in value.items():
        clean_key = str(key or "")[:60]
        if _field_is_unsafe(clean_key):
            continue
        if isinstance(item, SAFE_VALUE_TYPES):
            safe[clean_key] = item
    return safe


def _safe_scalar(value: Any, *, trusted_dict_keys: bool = False) -> Any:
    if isinstance(value, SAFE_VALUE_TYPES):
        return value
    if isinstance(value, (list, tuple)):
        return [x for x in value if isinstance(x, SAFE_VALUE_TYPES)][:20]
    if isinstance(value, dict):
        if trusted_dict_keys:
            return {str(k)[:60]: v for k, v in value.items() if isinstance(v, SAFE_VALUE_TYPES)}
        return _sanitize_dict(value)
    return str(type(value).__name__)


def sanitize_stat_fields(stat: str, fields: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {"type": "runtime_stat", "stat": str(stat or "unknown")[:80]}
    for key, value in fields.items():
        clean_key = str(key or "")[:80]
        if _field_is_unsafe(clean_key):
            continue
        safe[clean_key] = _safe_scalar(value, trusted_dict_keys=clean_key in SAFE_FIELD_NAMES)
    return safe


def runtime_summary(counters: dict[str, int], *, started_at: float, now: float | None = None) -> dict[str, Any]:
    current = time.time() if now is None else now
    return {
        "uptime_s": max(0, int(current - started_at)),
        "counters": {str(k): int(v) for k, v in sorted(counters.items())},
    }
