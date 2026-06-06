"""Event deduplication helpers."""
from __future__ import annotations

import hashlib
from collections import deque
from typing import Any, Callable


def event_dedupe_key(event: dict[str, Any], *, message_to_text_fn: Callable[[Any], str]) -> str:
    mid = event.get("message_id") or event.get("message_seq") or event.get("real_id")
    if mid not in (None, ""):
        return f"{event.get('group_id')}:{mid}"
    text = message_to_text_fn(event.get("message"))
    return f"{event.get('group_id')}:{event.get('user_id')}:{event.get('time')}:{hashlib.sha1(text.encode('utf-8')).hexdigest()}"


def mark_event_seen(
    event: dict[str, Any],
    *,
    keys: deque[str],
    key_set: set[str],
    message_to_text_fn: Callable[[Any], str],
) -> bool:
    key = event_dedupe_key(event, message_to_text_fn=message_to_text_fn)
    if key in key_set:
        return False
    if len(keys) == keys.maxlen:
        old = keys.popleft()
        key_set.discard(old)
    keys.append(key)
    key_set.add(key)
    return True
