"""High-level event route helpers for the QQ/Hermes bridge."""
from __future__ import annotations

from typing import Any, Callable


CommandAction = dict[str, Any]

def event_log_record(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "event",
        "post_type": event.get("post_type"),
        "message_type": event.get("message_type"),
        "group_id": event.get("group_id"),
        "user_id": event.get("user_id"),
        "self_id": event.get("self_id"),
    }


def precheck_group_message(
    event: dict[str, Any],
    *,
    is_allowed_group_fn: Callable[[dict[str, Any]], bool],
) -> dict[str, Any] | None:
    if event.get("post_type") != "message" or event.get("message_type") != "group":
        return {"ok": True, "ignored": "not_group_message"}
    if not is_allowed_group_fn(event):
        return {"ok": True, "ignored": "other_group"}
    return None


def command_action_for_text(
    user_text: str,
    *,
    event: dict[str, Any],
    group_id: int | None,
    is_context_command_fn: Callable[[str], bool],
    is_jrrp_command_fn: Callable[[str], bool],
    sender_name_fn: Callable[[dict[str, Any]], str],
    build_context_reply_fn: Callable[[int | None], str],
    build_jrrp_reply_fn: Callable[[Any, str], tuple[str, bool]],
) -> CommandAction | None:
    if is_context_command_fn(user_text):
        return {
            "kind": "immediate",
            "reply": build_context_reply_fn(group_id),
            "trigger": "context_command",
            "log_type": "context_command",
            "remember_context": True,
            "extra": {},
        }
    if is_jrrp_command_fn(user_text):
        reply, first_draw = build_jrrp_reply_fn(event.get("user_id"), sender_name_fn(event))
        return {
            "kind": "immediate",
            "reply": reply,
            "trigger": "jrrp",
            "log_type": "jrrp",
            "remember_context": False,
            "extra": {"first_draw": first_draw},
        }
    return None


def proactive_action_for_non_direct_reply(
    event: dict[str, Any],
    *,
    proactive: dict[str, Any],
    group_id: int | None,
    enqueue_reply_intent_fn: Callable[[int, dict[str, Any]], dict[str, Any]],
    log_fn: Callable[[dict[str, Any]], None],
) -> dict[str, Any]:
    if not proactive.get("should_trigger"):
        return {
            "ok": True,
            "ignored": "not_at_me",
            "proactive_score": proactive.get("score"),
            "blocked": proactive.get("blocked"),
        }
    if group_id is None:
        return {"ok": True, "ignored": "no_group_id"}
    queued = enqueue_reply_intent_fn(group_id, {"kind": "proactive", "event": event, "proactive": proactive})
    if not queued.get("queued"):
        log_fn({
            "type": "ignored",
            "reason": queued.get("reason"),
            "group_id": group_id,
            "queue_size": queued.get("queue_size"),
            "queue_limit": queued.get("queue_limit"),
        })
        return {"ok": True, "ignored": queued.get("reason"), "score": proactive.get("score"), **queued}
    return {"kind": "process_reply_intent", "group_id": group_id, "intent": {"kind": "proactive"}}


def direct_action_for_event(
    event: dict[str, Any],
    *,
    user_text: str,
    skip_unclear_mentions: bool,
    should_skip_unclear_mention_fn: Callable[[str], bool],
    should_rate_limit_fn: Callable[[int | None, Any], tuple[bool, str]],
    group_id_fn: Callable[[dict[str, Any]], int | None],
    is_reply_to_me_fn: Callable[[dict[str, Any]], bool],
    is_at_me_fn: Callable[[dict[str, Any]], bool],
    enqueue_reply_intent_fn: Callable[[int, dict[str, Any]], dict[str, Any]],
    log_fn: Callable[[dict[str, Any]], None],
    media_context: str = "",
    is_name_mention_fn: Callable[[dict[str, Any]], bool] = lambda event: False,
) -> dict[str, Any]:
    if skip_unclear_mentions and should_skip_unclear_mention_fn(user_text):
        log_fn({"type": "ignored", "reason": "unclear_mention", "user_id": event.get("user_id")})
        return {"ok": True, "ignored": "unclear_mention"}
    group_id = group_id_fn(event)
    limited, reason = should_rate_limit_fn(group_id, event.get("user_id"))
    if limited:
        log_fn({"type": "ignored", "reason": "user_cooldown", "user_id": event.get("user_id")})
        return {"ok": True, "ignored": "user_cooldown", "message": reason}
    if group_id is None:
        return {"ok": True, "ignored": "no_group_id"}
    trigger = direct_trigger_name(is_reply_to_bot=is_reply_to_me_fn(event), is_at_bot=is_at_me_fn(event), is_name_mention=is_name_mention_fn(event))
    queued = enqueue_reply_intent_fn(group_id, {"kind": "direct", "event": event, "user_text": user_text, "trigger": trigger, "media_context": media_context})
    if not queued.get("queued"):
        log_fn({
            "type": "ignored",
            "reason": queued.get("reason"),
            "group_id": group_id,
            "user_id": event.get("user_id"),
            "queue_size": queued.get("queue_size"),
            "queue_limit": queued.get("queue_limit"),
        })
        return {"ok": True, "ignored": queued.get("reason"), **queued}
    return {"kind": "process_reply_intent", "group_id": group_id, "intent": {"kind": "direct"}}


def prepare_direct_user_text(user_text: str) -> str:
    return user_text if user_text else "（对方只 @ 了我，没有附加文本）"


def direct_trigger_name(*, is_reply_to_bot: bool, is_at_bot: bool, is_name_mention: bool = False) -> str:
    if is_reply_to_bot and not is_at_bot:
        return "reply_to_bot"
    if is_at_bot:
        return "at"
    if is_name_mention:
        return "name"
    return "at"
