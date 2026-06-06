"""User-facing control helpers: cooldowns, unclear mentions, style selection."""
from __future__ import annotations

import hashlib
import re
import time
from typing import Any, Callable


def cooldown_key(group_id: Any, user_id: Any) -> str:
    return f"{group_id}:{user_id}"


def should_rate_limit(
    group_id: Any,
    user_id: Any,
    *,
    replied_at: dict[str, float],
    cooldown_seconds: float,
    now: float | None = None,
) -> tuple[bool, str]:
    now = time.time() if now is None else now
    key = cooldown_key(group_id, user_id)
    last = replied_at.get(key, 0.0)
    remain = cooldown_seconds - (now - last)
    if remain > 0:
        return True, f"你刚才问得太频繁啦，慢点，约 {int(remain)} 秒后再叫我。"
    return False, ""


def mark_user_replied(
    group_id: Any,
    user_id: Any,
    *,
    replied_at: dict[str, float],
    now: float | None = None,
) -> None:
    replied_at[cooldown_key(group_id, user_id)] = time.time() if now is None else now


def should_skip_unclear_mention(user_text: str) -> bool:
    text = re.sub(r"@\S+", "", user_text).strip()
    text = re.sub(r"[\s?？!！。.,，~～…]+", "", text)
    return not text


def style_hint_for(
    event: dict[str, Any],
    *,
    style_hints: list[str],
    message_to_text_fn: Callable[[Any], str],
) -> str:
    seed = f"{event.get('user_id')}|{message_to_text_fn(event.get('message'))}"
    idx = int(hashlib.sha1(seed.encode("utf-8")).hexdigest(), 16) % len(style_hints)
    return style_hints[idx]
