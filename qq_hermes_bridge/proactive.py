"""Proactive speaking scoring/timing helpers."""
from __future__ import annotations

import time
from collections import deque
from datetime import datetime
from typing import Any, Callable

from . import matching


def parse_hhmm(value: str) -> tuple[int, int]:
    try:
        h, m = value.split(":", 1)
        return int(h), int(m)
    except Exception:
        return 0, 0


def is_night_time(
    now: float | None = None,
    *,
    night_start: str,
    night_end: str,
    fromtimestamp: Callable[[float], datetime] = datetime.fromtimestamp,
) -> bool:
    dt = fromtimestamp(time.time() if now is None else now)
    cur = dt.hour * 60 + dt.minute
    sh, sm = parse_hhmm(night_start)
    eh, em = parse_hhmm(night_end)
    start = sh * 60 + sm
    end = eh * 60 + em
    if start <= end:
        return start <= cur < end
    return cur >= start or cur < end


def decay_score(state: dict[str, Any], *, now: float, decay_per_minute: float) -> None:
    last = float(state.get("last_decay_at") or now)
    elapsed_minutes = max(0.0, (now - last) / 60.0)
    if elapsed_minutes:
        state["score"] = max(0.0, float(state.get("score", 0.0)) - elapsed_minutes * decay_per_minute)
    state["last_decay_at"] = now


def add_recent_activity(
    activity: deque[dict[str, Any]],
    *,
    event: dict[str, Any],
    text: str,
    now: float,
    burst_window_seconds: float,
) -> list[dict[str, Any]]:
    activity.append({"ts": now, "user_id": event.get("user_id"), "text": text})
    cutoff = now - burst_window_seconds
    while activity and float(activity[0].get("ts", 0)) < cutoff:
        activity.popleft()
    return list(activity)


def message_score(
    text: str,
    *,
    name_triggers: list[str],
    topic_keywords: list[str],
    light_keywords: list[str],
    score_name_trigger: float,
    score_topic_keyword: float,
    score_light_keyword: float,
    score_question: float,
    score_open_question: float,
) -> tuple[float, list[str]]:
    score = 1.0
    reasons = ["message"]
    name = matching.first_phrase_match(text, name_triggers, case_sensitive=False)
    if name:
        score += score_name_trigger
        reasons.append(f"name:{name}")
    topic = matching.first_phrase_match(text, topic_keywords)
    if topic:
        score += score_topic_keyword
        reasons.append(f"topic:{topic}")
    light = matching.first_phrase_match(text, light_keywords)
    if light:
        score += score_light_keyword
        reasons.append(f"light:{light}")
    if matching.contains_any_phrase(text, ["?", "？", "吗", "么"]):
        score += score_question
        reasons.append("question")
    if matching.contains_any_phrase(text, ["有没有人", "有人知道", "谁懂", "怎么办", "为啥", "怎么弄", "救一下"]):
        score += score_open_question
        reasons.append("open_question")
    if matching.contains_any_phrase(text, ["[图片]", "[表情]"]):
        score += 1.0
        reasons.append("media")
    return score, reasons


def update_score_core(
    state: dict[str, Any],
    *,
    activity: list[dict[str, Any]],
    base_add: float,
    reasons: list[str],
    now: float,
    blocked: str,
    burst_message_threshold: int,
    burst_user_threshold: int,
    score_burst: float,
    score_multi_user: float,
    night_score_multiplier: float,
    is_night: bool,
    threshold: float,
) -> dict[str, Any]:
    add = base_add
    out_reasons = list(reasons)
    if len(activity) >= burst_message_threshold:
        add += score_burst
        out_reasons.append("burst")
    speakers = {str(x.get("user_id")) for x in activity if x.get("user_id") is not None}
    if len(speakers) >= burst_user_threshold:
        add += score_multi_user
        out_reasons.append("multi_user")
    if is_night:
        add *= night_score_multiplier
        out_reasons.append("night_scaled")

    state["score"] = float(state.get("score", 0.0)) + add
    direct_name_trigger = any(str(r).startswith("name:") for r in out_reasons)
    should = not blocked and state["score"] >= threshold
    return {
        "score": state["score"],
        "should_trigger": should,
        "reasons": out_reasons,
        "blocked": blocked,
        "direct_name_trigger": direct_name_trigger,
        "threshold": threshold,
    }


def can_send_now(times: deque[float], *, now: float, window_seconds: float, max_replies: int) -> str:
    cutoff = now - window_seconds
    while times and times[0] <= cutoff:
        times.popleft()
    if len(times) >= max_replies:
        return "rate_limit"
    return ""


def block_reason(
    state: dict[str, Any],
    *,
    now: float,
    rate_block: str = "",
    group_cooldown_seconds: float,
    daily_limit: int = 0,
) -> str:
    if rate_block:
        return rate_block
    if daily_limit > 0 and int(state.get("daily_count") or 0) >= daily_limit:
        return "daily_limit"
    if now < float(state.get("sensitive_until") or 0.0):
        return "sensitive_cooldown"
    if now - float(state.get("last_proactive_at") or 0.0) < group_cooldown_seconds:
        return "group_cooldown"
    return ""


def mark_replied(state: dict[str, Any], times: deque[float], *, now: float) -> None:
    state["score"] = 0.0
    state["last_proactive_at"] = now
    state["daily_count"] = int(state.get("daily_count") or 0) + 1
    times.append(now)


def mark_skipped(state: dict[str, Any]) -> None:
    state["score"] = float(state.get("score", 0.0)) * 0.4
