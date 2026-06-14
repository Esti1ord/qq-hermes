"""Proactive speaking scoring/timing helpers."""
from __future__ import annotations

import re
import time
from collections import Counter, deque
from datetime import datetime
from typing import Any, Callable

from . import matching


OPEN_QUESTION_PHRASES = ["有没有人", "有人知道", "谁懂", "怎么办", "为啥", "怎么弄", "救一下"]
OPINION_PROMPT_PHRASES = [
    "你们觉得",
    "大家觉得",
    "怎么选",
    "选哪个",
    "哪个好",
    "有没有推荐",
    "到底是",
    "还是",
    "要不要",
    "该不该",
]
REACTION_PHRASES = ["笑死", "绷不住", "服了", "离谱", "麻了", "无语", "草", "寄", "太难", "累", "困", "顶不住"]
MIN_TEMPLATE_STEM_CHARS = 4


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, float(value or 0.0)))


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


def prune_recent_activity(
    activity: deque[dict[str, Any]],
    *,
    now: float,
    window_seconds: float,
) -> list[dict[str, Any]]:
    cutoff = now - window_seconds
    while activity and float(activity[0].get("ts", 0)) < cutoff:
        activity.popleft()
    return list(activity)


def add_recent_activity(
    activity: deque[dict[str, Any]],
    *,
    event: dict[str, Any],
    text: str,
    now: float,
    burst_window_seconds: float,
) -> list[dict[str, Any]]:
    activity.append({"ts": now, "user_id": event.get("user_id"), "text": text})
    return prune_recent_activity(activity, now=now, window_seconds=burst_window_seconds)


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
    if matching.contains_any_phrase(text, OPEN_QUESTION_PHRASES):
        score += score_open_question
        reasons.append("open_question")
    if matching.contains_any_phrase(text, ["[图片]", "[表情]"]):
        score += 1.0
        reasons.append("media")
    return score, reasons


def _speaker_counts(activity: list[dict[str, Any]]) -> Counter[str]:
    return Counter(str(x.get("user_id")) for x in activity if x.get("user_id") is not None)


def _max_consecutive_same_speaker(activity: list[dict[str, Any]]) -> int:
    longest = 0
    current = 0
    previous = object()
    for item in activity:
        speaker = item.get("user_id")
        if speaker is None:
            current = 0
            previous = object()
            continue
        if speaker == previous:
            current += 1
        else:
            current = 1
            previous = speaker
        longest = max(longest, current)
    return longest


def activity_window_summary(activity: list[dict[str, Any]]) -> dict[str, Any]:
    """Return content-safe aggregate stats for a recent activity window."""
    count = len(activity)
    speaker_counts = _speaker_counts(activity)
    dominant_share = max(speaker_counts.values()) / count if count and speaker_counts else 0.0
    return {
        "message_count": count,
        "speaker_count": len(speaker_counts),
        "dominant_speaker_share": round(dominant_share, 3),
        "max_consecutive_same_speaker": _max_consecutive_same_speaker(activity),
    }


def _normalized_text(text: str) -> str:
    return matching.normalize_spaces(str(text or ""))


def _template_stem(text: str) -> str:
    clean = _normalized_text(text)
    if not clean:
        return ""
    for marker in ("可以找到", "有没有", "有人知道", "你们觉得", "大家觉得", "怎么选", "选哪个", "哪个好"):
        if marker in clean:
            left, right = clean.split(marker, 1)
            if len(right.strip()) >= 2:
                return f"{marker}:{left[:2]}"
    compact = matching.compact_text_key(clean)
    compact = re.sub(r"\d+", "#", compact)
    compact = re.sub(r"[A-Za-z]+", "A", compact)
    if len(compact) < MIN_TEMPLATE_STEM_CHARS:
        return ""
    return compact[: min(8, len(compact))]


def _shared_reaction_count(activity: list[dict[str, Any]]) -> int:
    speakers: set[str] = set()
    for item in activity:
        text = str(item.get("text") or "")
        if matching.contains_any_phrase(text, REACTION_PHRASES):
            speaker = item.get("user_id")
            if speaker is not None:
                speakers.add(str(speaker))
    return len(speakers)


def _meme_chain_score(activity: list[dict[str, Any]]) -> tuple[float, list[str]]:
    stems: dict[str, set[str]] = {}
    for item in activity:
        stem = _template_stem(str(item.get("text") or ""))
        speaker = item.get("user_id")
        if stem and speaker is not None:
            stems.setdefault(stem, set()).add(str(speaker))
    if not stems:
        return 0.0, []
    participants = max(len(speakers) for speakers in stems.values())
    if participants >= 3:
        return 30.0, ["opening:meme_chain"]
    if participants >= 2:
        return 18.0, ["opening:meme_chain"]
    return 0.0, []


def activity_heat_score(activity: list[dict[str, Any]]) -> tuple[float, list[str]]:
    count = len(activity)
    if count <= 0:
        return 0.0, []
    speaker_counts = _speaker_counts(activity)
    speakers = len(speaker_counts)
    dominant_share = max(speaker_counts.values()) / count if speaker_counts else 1.0
    consecutive = _max_consecutive_same_speaker(activity)

    message_score_part = min(30.0, count * 5.0)
    speaker_score_part = min(20.0, speakers * 7.0)
    balance_score_part = max(0.0, (1.0 - dominant_share) * 20.0)
    heat = message_score_part + speaker_score_part + balance_score_part
    reasons = ["heat:activity"]

    if count >= 5 and speakers >= 3 and dominant_share <= 0.67:
        heat += 8.0
        reasons.append("heat:hot_chat")
    elif count >= 3 and speakers >= 2:
        heat += 4.0
        reasons.append("heat:back_and_forth")

    if speakers <= 1 and count >= 3:
        heat -= min(25.0, count * 5.0)
        reasons.append("penalty:single_speaker")
    elif dominant_share > 0.75 and count >= 4:
        heat -= 12.0
        reasons.append("penalty:dominant_speaker")
    if consecutive >= 4:
        heat -= min(20.0, (consecutive - 3) * 5.0)
        reasons.append("penalty:consecutive_speaker")

    return _clamp(heat, 0.0, 60.0), reasons


def natural_opening_score(
    text: str,
    activity: list[dict[str, Any]],
    *,
    topic_keywords: list[str],
    light_keywords: list[str],
) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    recent_text = "\n".join(str(item.get("text") or "") for item in activity)
    signal_text = recent_text or text
    chain_score, chain_reasons = _meme_chain_score(activity)
    if chain_score:
        score += chain_score
        reasons.extend(chain_reasons)
    if matching.contains_any_phrase(signal_text, OPEN_QUESTION_PHRASES):
        score += 28.0
        reasons.append("opening:open_question")
    if matching.contains_any_phrase(signal_text, OPINION_PROMPT_PHRASES):
        score += 20.0
        reasons.append("opening:opinion_prompt")
    shared_reactions = _shared_reaction_count(activity)
    if shared_reactions >= 3:
        score += 16.0
        reasons.append("opening:shared_reaction")
    elif shared_reactions >= 2:
        score += 10.0
        reasons.append("opening:shared_reaction")
    if matching.first_phrase_match(signal_text, topic_keywords):
        score += 8.0
        reasons.append("signal:topic")
    if matching.first_phrase_match(signal_text, light_keywords):
        score += 5.0
        reasons.append("signal:light")
    if matching.contains_any_phrase(signal_text, ["?", "？", "吗", "么"]):
        score += 6.0
        reasons.append("signal:question")
    return min(40.0, score), reasons


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
    topic_keywords: list[str] | None = None,
    light_keywords: list[str] | None = None,
) -> dict[str, Any]:
    del base_add, burst_message_threshold, burst_user_threshold, score_burst, score_multi_user
    out_reasons = list(reasons)
    heat, heat_reasons = activity_heat_score(activity)
    out_reasons.extend(heat_reasons)
    current_text = str(activity[-1].get("text") or "") if activity else ""
    opening, opening_reasons = natural_opening_score(
        current_text,
        activity,
        topic_keywords=topic_keywords or [],
        light_keywords=light_keywords or [],
    )
    out_reasons.extend(opening_reasons)
    direct_name_trigger = any(str(r).startswith("name:") for r in out_reasons)

    score = _clamp(heat + opening)
    if is_night:
        score *= night_score_multiplier
        out_reasons.append("night_scaled")
    score = _clamp(score)
    state["score"] = score
    state["last_decay_at"] = now
    should = not blocked and score >= threshold
    return {
        "score": score,
        "heat": heat,
        "opening_score": opening,
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
