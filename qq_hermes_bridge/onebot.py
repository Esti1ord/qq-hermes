"""OneBot v11 event/message parsing helpers.

This module is intentionally stateless. Bridge-specific configuration such as
allowed group IDs, target fallback group, bot QQ, and display-name resolution is
passed in by callers so these helpers can be reused by other OneBot adapters.
"""
from __future__ import annotations

import re
from typing import Any, Callable


def message_to_text(
    message: Any,
    include_at: bool = True,
    *,
    display_name_by_qq_fn: Callable[[str], str] | None = None,
) -> str:
    """Convert OneBot string or message segment array to readable plain text."""
    display_name_by_qq_fn = display_name_by_qq_fn or (lambda qq: qq)
    if isinstance(message, str):
        def repl_at(match: re.Match[str]) -> str:
            if not include_at:
                return ""
            qq = match.group(1)
            return f"@{display_name_by_qq_fn(qq)}"
        return re.sub(r"\[CQ:at,qq=(\d+)\]", repl_at, message).strip()
    if isinstance(message, list):
        parts: list[str] = []
        for seg in message:
            if not isinstance(seg, dict):
                continue
            typ = seg.get("type")
            data = seg.get("data") or {}
            if typ == "text":
                parts.append(str(data.get("text", "")))
            elif typ == "at":
                if not include_at:
                    continue
                qq = str(data.get("qq") or "")
                if qq == "all":
                    parts.append("@全体成员")
                elif qq:
                    name = str(data.get("name") or data.get("card") or data.get("nickname") or display_name_by_qq_fn(qq))
                    parts.append(f"@{name}")
            elif typ == "image":
                parts.append("[图片]")
            elif typ == "face":
                parts.append("[表情]")
            elif typ == "reply":
                parts.append("[回复]")
            else:
                parts.append(f"[{typ}]")
        return "".join(parts).strip()
    return str(message or "").strip()


def sender_name(event: dict[str, Any]) -> str:
    sender = event.get("sender") or {}
    return str(sender.get("card") or sender.get("nickname") or event.get("user_id") or "群成员")


def group_id_from_event(event: dict[str, Any], default: int | None) -> int | None:
    raw = event.get("group_id")
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def is_allowed_group(event: dict[str, Any], *, allowed_group_ids: set[int]) -> bool:
    group_id = group_id_from_event(event, default=None)
    return group_id is not None and group_id in allowed_group_ids


def reply_segments(event: dict[str, Any]) -> list[dict[str, Any]]:
    message = event.get("message")
    if not isinstance(message, list):
        return []
    return [seg for seg in message if isinstance(seg, dict) and seg.get("type") == "reply"]


def reply_segment_sender_qq(data: dict[str, Any]) -> str:
    for key in ("qq", "sender_id", "user_id", "sender", "from_uin"):
        val = data.get(key)
        if isinstance(val, dict):
            val = val.get("user_id") or val.get("qq") or val.get("uin")
        if val not in (None, ""):
            return str(val)
    return ""


def reply_segment_message_id(data: dict[str, Any]) -> str:
    for key in ("message_id", "id", "msg_id", "seq", "message_seq", "real_id"):
        val = data.get(key)
        if val not in (None, ""):
            return str(val)
    return ""


def is_at_me(event: dict[str, Any], *, bot_qq: str = "") -> bool:
    message = event.get("message")
    self_id = str(event.get("self_id") or bot_qq or "")
    if isinstance(message, list):
        for seg in message:
            if not isinstance(seg, dict):
                continue
            if seg.get("type") == "at":
                qq = str((seg.get("data") or {}).get("qq") or "")
                if qq == "all":
                    return False
                if self_id and qq == self_id:
                    return True
        return False
    if isinstance(message, str):
        if self_id and re.search(rf"\[CQ:at,qq={re.escape(self_id)}\]", message):
            return True
    return False


def is_reply_to_me(event: dict[str, Any], *, bot_qq: str = "") -> bool:
    self_id = str(event.get("self_id") or bot_qq or "")
    if not self_id:
        return False
    for seg in reply_segments(event):
        qq = reply_segment_sender_qq(seg.get("data") or {})
        if qq == self_id:
            return True
    return False
