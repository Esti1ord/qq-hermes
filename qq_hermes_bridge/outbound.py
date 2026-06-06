"""Outbound message helpers for QQ/Hermes bridge."""
from __future__ import annotations

import hashlib
import re
import time
from collections import deque
from typing import Any

import httpx


def cq_escape_param(value: Any) -> str:
    """Escape a value for use inside a OneBot CQ-code parameter."""
    text = str(value or "")
    return text.replace("&", "&amp;").replace("[", "&#91;").replace("]", "&#93;").replace(",", "&#44;")


def cq_reply_segment(message_id: Any) -> str:
    if message_id in (None, ""):
        return ""
    return f"[CQ:reply,id={cq_escape_param(message_id)}]"


def reply_to_message(message: str, message_id: Any) -> str:
    prefix = cq_reply_segment(message_id)
    if not prefix:
        return message
    return f"{prefix}{message or ''}"


async def send_group_msg(
    group_id: int,
    message: str,
    *,
    onebot_http_url: str,
    access_token: str = "",
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    headers = {}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    payload = {"group_id": group_id, "message": message}
    async with httpx.AsyncClient(timeout=30, trust_env=False, transport=transport) as client:
        r = await client.post(f"{onebot_http_url}/send_group_msg", json=payload, headers=headers)
        text = r.text
        try:
            return r.json()
        except Exception:
            return {"status_code": r.status_code, "text": text}


def send_group_msg_succeeded(data: dict[str, Any]) -> bool:
    if not isinstance(data, dict):
        return False
    if data.get("error"):
        return False
    status = str(data.get("status") or "").lower()
    if status and status != "ok":
        return False
    retcode = data.get("retcode")
    if retcode not in (None, 0, "0"):
        return False
    return True


def outbound_key(message: str) -> str:
    clean = re.sub(r"\s+", "", message or "")
    return hashlib.sha1(clean.encode("utf-8")).hexdigest()


def prune_recent_outbound(bucket: deque[dict[str, Any]], *, now: float, window: float) -> None:
    cutoff = now - window
    while bucket and float(bucket[0].get("ts") or 0.0) < cutoff:
        bucket.popleft()


def is_recent_duplicate_outbound(
    group_id: int,
    message: str,
    *,
    recent_by_group: dict[int, deque[dict[str, Any]]],
    now: float | None = None,
    window: float = 30.0,
    maxlen: int = 20,
) -> bool:
    now = time.time() if now is None else now
    bucket = recent_by_group.setdefault(group_id, deque(maxlen=maxlen))
    prune_recent_outbound(bucket, now=now, window=window)
    key = outbound_key(message)
    return any(item.get("key") == key for item in bucket)


def remember_successful_outbound(
    group_id: int,
    message: str,
    *,
    recent_by_group: dict[int, deque[dict[str, Any]]],
    now: float | None = None,
    window: float = 30.0,
    maxlen: int = 20,
) -> None:
    now = time.time() if now is None else now
    bucket = recent_by_group.setdefault(group_id, deque(maxlen=maxlen))
    prune_recent_outbound(bucket, now=now, window=window)
    bucket.append({"key": outbound_key(message), "ts": now})


def should_suppress_duplicate_outbound(
    group_id: int,
    message: str,
    *,
    recent_by_group: dict[int, deque[dict[str, Any]]],
    now: float | None = None,
    window: float = 30.0,
    maxlen: int = 20,
) -> bool:
    return is_recent_duplicate_outbound(
        group_id,
        message,
        recent_by_group=recent_by_group,
        now=now,
        window=window,
        maxlen=maxlen,
    )
