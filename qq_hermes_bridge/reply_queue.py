"""Per-group reply queue helpers."""
from __future__ import annotations

import re
import time
from collections import deque
from typing import Any


QueueKey = tuple[int, str]
NO_MEDIA_CONTEXT = "（当前消息没有图片识别结果）"
_COALESCED_ITEMS_KEY = "_coalesced_items"
_SAFE_DIRECT_TRIGGERS = {"at", "name"}
_COMMAND_TEXTS = {"jrrp", "/jrrp", "今日人品"}


def _kind_for_intent(intent: dict[str, Any] | None) -> str:
    kind = str((intent or {}).get("kind") or "direct")
    return "proactive" if kind == "proactive" else "direct"


def _queue_key(group_id: int, kind: str) -> QueueKey:
    return (group_id, "proactive" if kind == "proactive" else "direct")


def _intent_event(intent: dict[str, Any] | None) -> dict[str, Any]:
    event = (intent or {}).get("event")
    return event if isinstance(event, dict) else {}


def _intent_sender_id(intent: dict[str, Any] | None) -> str:
    sender = _intent_event(intent).get("user_id")
    return "" if sender in (None, "") else str(sender)


def _intent_group_id(intent: dict[str, Any] | None, default: int | None = None) -> int | None:
    raw = _intent_event(intent).get("group_id", default)
    if raw in (None, ""):
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _direct_route_for_intent(intent: dict[str, Any] | None) -> str:
    return str((intent or {}).get("trigger") or "direct").strip().lower() or "direct"


def _media_context_is_empty(intent: dict[str, Any]) -> bool:
    media_context = str(intent.get("media_context") or "").strip()
    return media_context in {"", NO_MEDIA_CONTEXT}


def _text_looks_command_like(text: str) -> bool:
    clean = str(text or "").strip()
    lowered = clean.lower()
    return clean.startswith("/") or lowered in _COMMAND_TEXTS


def _message_is_ordinary_text(message: Any) -> bool:
    """Return True only for direct text/at messages with no reply/media segments."""
    if message in (None, ""):
        return True
    if isinstance(message, str):
        for cq_type in re.findall(r"\[CQ:([^,\]]+)", message, flags=re.IGNORECASE):
            if cq_type.strip().lower() != "at":
                return False
        return True
    if not isinstance(message, list):
        return False
    for segment in message:
        if not isinstance(segment, dict):
            return False
        segment_type = str(segment.get("type") or "").strip().lower()
        if segment_type == "text":
            continue
        if segment_type == "at":
            data = segment.get("data") if isinstance(segment.get("data"), dict) else {}
            if str(data.get("qq") or "").strip().lower() == "all":
                return False
            continue
        return False
    return True


def is_safe_direct_coalesce_intent(intent: dict[str, Any] | None) -> bool:
    """Whether an intent is an ordinary pending direct text reply safe to merge."""
    if not isinstance(intent, dict):
        return False
    if _kind_for_intent(intent) != "direct":
        return False
    if intent.get("_reply_started") or intent.get("_direct_reply_started"):
        return False
    if intent.get("command") or intent.get("is_command") or intent.get("command_action"):
        return False
    route = _direct_route_for_intent(intent)
    if route not in _SAFE_DIRECT_TRIGGERS:
        return False
    user_text = str(intent.get("user_text") or "").strip()
    if not user_text or _text_looks_command_like(user_text):
        return False
    lowered_text = user_text.lower()
    if any(marker in lowered_text for marker in ("[cq:image", "[cq:reply", "[图片]", "[回复]")):
        return False
    if not _media_context_is_empty(intent):
        return False
    if intent.get("ocr_task") is not None:
        return False
    return _message_is_ordinary_text(_intent_event(intent).get("message"))


def _coalesced_items_for_intent(intent: dict[str, Any]) -> list[dict[str, str]]:
    items = intent.get(_COALESCED_ITEMS_KEY)
    if isinstance(items, list) and items:
        normalized = [item for item in items if isinstance(item, dict)]
        if normalized:
            intent[_COALESCED_ITEMS_KEY] = normalized
            return normalized
    first_text = str(intent.get("user_text") or "")
    normalized = [{"user_text": first_text}]
    intent[_COALESCED_ITEMS_KEY] = normalized
    return normalized


def coalesced_count(intent: dict[str, Any] | None) -> int:
    if not isinstance(intent, dict):
        return 0
    try:
        stored = int(intent.get("_coalesced_count") or 0)
    except (TypeError, ValueError):
        stored = 0
    items = intent.get(_COALESCED_ITEMS_KEY)
    item_count = len(items) if isinstance(items, list) else 0
    return max(1, stored, item_count)


def coalesced_user_text_for_prompt(intent: dict[str, Any] | None, *, default: str = "") -> str:
    """Build the merged user text for the prompt path only."""
    if not isinstance(intent, dict):
        return default
    items = intent.get(_COALESCED_ITEMS_KEY)
    if not isinstance(items, list) or len(items) <= 1:
        return str(default if default not in (None, "") else intent.get("user_text") or "")
    lines: list[str] = []
    for index, item in enumerate(items, 1):
        if not isinstance(item, dict):
            continue
        text = str(item.get("user_text") or "").strip()
        if text:
            lines.append(f"{index}. {text}")
    if len(lines) <= 1:
        return str(default if default not in (None, "") else intent.get("user_text") or "")
    return "同一位群友在短时间内连续发了几条消息。请按顺序一起理解，主要回复最后一条：\n" + "\n".join(lines)


def _intent_timestamp(intent: dict[str, Any], now: float) -> float:
    for key in ("_coalesced_last_at", "_perf_enqueued_at"):
        try:
            value = float(intent.get(key))
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return now


def _within_coalesce_window(existing: dict[str, Any], incoming: dict[str, Any], *, window_ms: int | float, now: float) -> bool:
    try:
        window = max(0.0, float(window_ms or 0))
    except (TypeError, ValueError):
        return False
    if window <= 0:
        return False
    last_at = _intent_timestamp(existing, now)
    incoming_at = _intent_timestamp(incoming, now)
    elapsed_ms = max(0.0, (incoming_at - last_at) * 1000.0)
    return elapsed_ms <= window


def _same_direct_coalesce_bucket(group_id: int, existing: dict[str, Any], incoming: dict[str, Any]) -> bool:
    existing_group_id = _intent_group_id(existing)
    incoming_group_id = _intent_group_id(incoming)
    if existing_group_id != group_id or incoming_group_id != group_id:
        return False
    sender_id = _intent_sender_id(existing)
    if not sender_id or sender_id != _intent_sender_id(incoming):
        return False
    return _direct_route_for_intent(existing) == _direct_route_for_intent(incoming)


def _coalesce_into(existing: dict[str, Any], incoming: dict[str, Any], *, window_ms: int | float, now: float) -> None:
    items = _coalesced_items_for_intent(existing)
    items.append({"user_text": str(incoming.get("user_text") or "")})

    # Reply to the most recent QQ message while preserving all text for the prompt.
    if isinstance(incoming.get("event"), dict):
        existing["event"] = incoming["event"]
    existing["user_text"] = str(incoming.get("user_text") or existing.get("user_text") or "")
    existing["trigger"] = incoming.get("trigger", existing.get("trigger"))
    if "media_context" in incoming:
        existing["media_context"] = incoming.get("media_context")
    for key in ("_perf_interaction_id", "_perf_event_received_at", "_perf_kind"):
        if incoming.get(key) not in (None, ""):
            existing[key] = incoming[key]
    try:
        window = int(float(window_ms or 0))
    except (TypeError, ValueError):
        window = 0
    existing["_coalesced_count"] = len(items)
    existing["_coalesced_window_ms"] = max(0, window)
    existing["_coalesced_last_at"] = _intent_timestamp(incoming, now)


def try_coalesce_last_direct(
    group_id: int,
    intent: dict[str, Any],
    *,
    queue: deque[dict[str, Any]],
    direct_coalesce_window_ms: int | float = 0,
    now: float | None = None,
) -> dict[str, Any] | None:
    """Merge ``intent`` into the last pending direct intent when conservatively safe."""
    current = time.monotonic() if now is None else float(now)
    if not queue or _kind_for_intent(intent) != "direct":
        return None
    existing = queue[-1]
    if not is_safe_direct_coalesce_intent(existing) or not is_safe_direct_coalesce_intent(intent):
        return None
    if not _same_direct_coalesce_bucket(group_id, existing, intent):
        return None
    if not _within_coalesce_window(existing, intent, window_ms=direct_coalesce_window_ms, now=current):
        return None
    _coalesce_into(existing, intent, window_ms=direct_coalesce_window_ms, now=current)
    try:
        window_value = int(max(0, float(direct_coalesce_window_ms or 0)))
    except (TypeError, ValueError):
        window_value = 0
    return {
        "queued": True,
        "coalesced": True,
        "reason": "direct_coalesced",
        "kind": "direct",
        "queue_size": len(queue),
        "queue_limit": queue.maxlen,
        "merged_count": 1,
        "coalesced_count": coalesced_count(existing),
        "coalesce_window_ms": window_value,
        "status": "coalesced",
    }


def queue_for_group(
    group_id: int,
    *,
    queues: dict[Any, deque[dict[str, Any]]],
    max_pending_replies: int,
    proactive_rate_limit_max_replies: int,
    kind: str = "direct",
    max_pending_direct_replies: int | None = None,
) -> deque[dict[str, Any]]:
    queue_kind = "proactive" if kind == "proactive" else "direct"
    key = _queue_key(group_id, queue_kind)
    if key not in queues:
        if queue_kind == "proactive":
            maxlen = max(1, proactive_rate_limit_max_replies)
        else:
            maxlen = max(1, max_pending_direct_replies if max_pending_direct_replies is not None else max_pending_replies)
        queues[key] = deque(maxlen=maxlen)
    return queues[key]


def enqueue(
    group_id: int,
    intent: dict[str, Any],
    *,
    queues: dict[Any, deque[dict[str, Any]]],
    max_pending_replies: int,
    proactive_rate_limit_max_replies: int,
    max_pending_direct_replies: int | None = None,
    direct_coalesce_window_ms: int | float = 0,
    now: float | None = None,
) -> dict[str, Any]:
    kind = _kind_for_intent(intent)
    queue = queue_for_group(
        group_id,
        queues=queues,
        max_pending_replies=max_pending_replies,
        proactive_rate_limit_max_replies=proactive_rate_limit_max_replies,
        kind=kind,
        max_pending_direct_replies=max_pending_direct_replies,
    )
    coalesced = try_coalesce_last_direct(
        group_id,
        intent,
        queue=queue,
        direct_coalesce_window_ms=direct_coalesce_window_ms,
        now=now,
    )
    if coalesced is not None:
        return coalesced
    if len(queue) >= queue.maxlen:
        if kind == "proactive" and queue.maxlen:
            queue.popleft()
            queue.append(intent)
            return {
                "queued": True,
                "reason": "proactive_replaced_oldest",
                "kind": kind,
                "queue_size": len(queue),
                "queue_limit": queue.maxlen,
                "dropped_oldest": True,
            }
        return {
            "queued": False,
            "reason": "reply_queue_full",
            "kind": kind,
            "queue_size": len(queue),
            "queue_limit": queue.maxlen,
        }
    queue.append(intent)
    return {"queued": True, "kind": kind, "queue_size": len(queue), "queue_limit": queue.maxlen}


def dequeue(
    group_id: int,
    *,
    queues: dict[Any, deque[dict[str, Any]]],
    max_pending_replies: int,
    proactive_rate_limit_max_replies: int,
    max_pending_direct_replies: int | None = None,
) -> dict[str, Any] | None:
    direct_queue = queue_for_group(
        group_id,
        queues=queues,
        max_pending_replies=max_pending_replies,
        proactive_rate_limit_max_replies=proactive_rate_limit_max_replies,
        kind="direct",
        max_pending_direct_replies=max_pending_direct_replies,
    )
    if direct_queue:
        return direct_queue.popleft()
    proactive_queue = queue_for_group(
        group_id,
        queues=queues,
        max_pending_replies=max_pending_replies,
        proactive_rate_limit_max_replies=proactive_rate_limit_max_replies,
        kind="proactive",
        max_pending_direct_replies=max_pending_direct_replies,
    )
    if proactive_queue:
        return proactive_queue.popleft()
    return None


def size_by_kind(
    group_id: int,
    kind: str,
    *,
    queues: dict[Any, deque[dict[str, Any]]],
    max_pending_replies: int,
    proactive_rate_limit_max_replies: int,
    max_pending_direct_replies: int | None = None,
) -> int:
    return len(queue_for_group(
        group_id,
        queues=queues,
        max_pending_replies=max_pending_replies,
        proactive_rate_limit_max_replies=proactive_rate_limit_max_replies,
        kind=kind,
        max_pending_direct_replies=max_pending_direct_replies,
    ))


def size(
    group_id: int,
    *,
    queues: dict[Any, deque[dict[str, Any]]],
    max_pending_replies: int,
    proactive_rate_limit_max_replies: int,
    max_pending_direct_replies: int | None = None,
) -> int:
    return size_by_kind(
        group_id,
        "direct",
        queues=queues,
        max_pending_replies=max_pending_replies,
        proactive_rate_limit_max_replies=proactive_rate_limit_max_replies,
        max_pending_direct_replies=max_pending_direct_replies,
    ) + size_by_kind(
        group_id,
        "proactive",
        queues=queues,
        max_pending_replies=max_pending_replies,
        proactive_rate_limit_max_replies=proactive_rate_limit_max_replies,
        max_pending_direct_replies=max_pending_direct_replies,
    )
