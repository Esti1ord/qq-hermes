"""Per-group reply queue helpers."""
from __future__ import annotations

from collections import deque
from typing import Any


QueueKey = tuple[int, str]


def _kind_for_intent(intent: dict[str, Any] | None) -> str:
    kind = str((intent or {}).get("kind") or "direct")
    return "proactive" if kind == "proactive" else "direct"


def _queue_key(group_id: int, kind: str) -> QueueKey:
    return (group_id, "proactive" if kind == "proactive" else "direct")


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
