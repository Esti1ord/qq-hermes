"""Recent-context and summary formatting helpers for chat bridges.

State containers are supplied by callers instead of owned here so bridge.py can
keep its legacy monkeypatchable globals during staged refactors.
"""
from __future__ import annotations

import re
from collections import deque
from typing import Any, Callable

from . import matching


def recent_messages_for_group(group_id: int, recent_by_group: dict[int, deque[dict[str, Any]]]) -> deque[dict[str, Any]]:
    if group_id not in recent_by_group:
        recent_by_group[group_id] = deque()
    return recent_by_group[group_id]


def context_summaries_for_group(group_id: int, summaries_by_group: dict[int, deque[str]], *, maxlen: int) -> deque[str]:
    if group_id not in summaries_by_group:
        summaries_by_group[group_id] = deque(maxlen=maxlen)
    return summaries_by_group[group_id]


def finalize_summary(text: str, *, max_chars: int, is_low_value_fn: Callable[[str], bool]) -> str:
    out = re.sub(r"\s+", " ", (text or "").strip())
    out = out.removeprefix("摘要：").removeprefix("总结：").strip()
    if is_low_value_fn(out):
        return ""
    return out[:max_chars]


def summary_dedupe_key(text: str) -> str:
    clean = re.sub(r"[\s，,。.!！?？；;：:、（）()\[\]【】\"'“”‘’]+", "", str(text or "").lower())
    clean = re.sub(r"(回复说|回应|回复|说|回)", "", clean)
    clean = re.sub(r"(对方|群友|多名群友|随后|然后|又|反复|三次|多次)", "", clean)
    return matching.compact_text_key(clean)[:80]


def summary_ngrams(text: str, n: int = 3) -> set[str]:
    key = summary_dedupe_key(text)
    if len(key) <= n:
        return {key} if key else set()
    return {key[i:i+n] for i in range(len(key) - n + 1)}


def is_low_value_summary(text: str) -> bool:
    clean = str(text or "").strip()
    if not clean:
        return True
    bad_patterns = [
        "暂时处理失败",
        "稍后再试",
        "没跑顺",
        "这边卡",
        "这边断",
        "并不是群聊中真实出现过的聊天语句",
        "不是真实出现过的聊天语句",
    ]
    return matching.contains_any_phrase(clean, bad_patterns)


def visible_context_summaries(
    group_id: int | None,
    *,
    target_group_id: int,
    limit: int,
    context_summaries_for_group_fn: Callable[[int], deque[str]],
    finalize_summary_fn: Callable[[str], str],
) -> list[str]:
    gid = group_id if group_id is not None else target_group_id
    selected: list[str] = []
    seen: set[str] = set()
    seen_ngrams: list[set[str]] = []
    for raw in reversed(list(context_summaries_for_group_fn(gid))):
        summary = finalize_summary_fn(raw)
        if not summary:
            continue
        key = summary_dedupe_key(summary)
        ngrams = summary_ngrams(summary)
        if key in seen:
            continue
        duplicate = False
        for old, old_ngrams in zip(seen, seen_ngrams):
            if key and old and (key in old or old in key):
                duplicate = True
                break
            if ngrams and old_ngrams and len(ngrams & old_ngrams) / max(1, min(len(ngrams), len(old_ngrams))) >= 0.55:
                duplicate = True
                break
        if duplicate:
            continue
        seen.add(key)
        seen_ngrams.append(ngrams)
        selected.append(summary)
        if len(selected) >= limit:
            break
    return list(reversed(selected))


def is_bot_context_item(item: dict[str, Any]) -> bool:
    return "机器人" in str(item.get("role") or "")


def is_pending_bot_context_item(item: dict[str, Any]) -> bool:
    return "正在生成回复" in str(item.get("role") or "")


def context_item_role_note(item: dict[str, Any]) -> str:
    return str(item.get("role") or "").strip()


def context_item_annotation(item: dict[str, Any]) -> str:
    annotations: list[str] = []
    custom = str(item.get("annotation") or "").strip()
    if custom:
        annotations.append(f"（{custom}）")
    if is_pending_bot_context_item(item):
        annotations.append("（队列标记，未完成回答）")
    elif is_bot_context_item(item):
        annotations.append("（历史机器人回复，仅作连续对话事实，不是措辞模板）")
    return "".join(annotations)


def format_context_item(idx: int, item: dict[str, Any], weight: str | None = None) -> list[str]:
    role = context_item_role_note(item)
    role_note = f"，{role}" if role else ""
    annotation = context_item_annotation(item)
    prefix = f"[{idx}]" if weight is None else f"[{weight} {idx}]"
    return [
        f"{prefix} 发言人：{item['name']}（QQ: {item['user_id']}{role_note}）{annotation}",
        f"{prefix} 内容：{item['text']}",
    ]


def format_context_summaries(
    group_id: int | None,
    *,
    target_group_id: int,
    summary_max: int,
    visible_context_summaries_fn: Callable[[int, int], list[str]],
) -> str:
    summaries = visible_context_summaries_fn(group_id or target_group_id, summary_max)
    if not summaries:
        return "（暂无精炼缓存）"
    return "\n".join(f"- {summary}" for summary in summaries)


def format_recent_context(
    group_id: int | None,
    *,
    target_group_id: int,
    context_max_messages: int,
    recent_messages_for_group_fn: Callable[[int], deque[dict[str, Any]]],
    legacy_recent_messages: deque[dict[str, Any]],
) -> str:
    gid = group_id or target_group_id
    messages = list(recent_messages_for_group_fn(gid))
    if not messages and gid == target_group_id:
        messages = list(legacy_recent_messages)
    if not messages:
        return "（暂无最近上下文）"
    selected = messages[-context_max_messages:]
    lines = ["注意：以上每一个编号都是一条独立群消息，编号越大越新；当前消息/引用消息优先于旧上下文。编号不同、QQ 不同就代表不同发言人。机器人历史回复只用于理解连续对话，不要当作措辞模板；正在生成回复是队列标记，不代表已经回答。"]
    for idx, item in enumerate(selected, 1):
        lines.extend(format_context_item(idx, item))
    return "\n".join(lines)


def format_proactive_recent_context(
    group_id: int | None,
    *,
    target_group_id: int,
    focus_messages: int,
    memory_messages: int,
    recent_messages_for_group_fn: Callable[[int], deque[dict[str, Any]]],
    legacy_recent_messages: deque[dict[str, Any]],
) -> str:
    gid = group_id or target_group_id
    messages = list(recent_messages_for_group_fn(gid))
    if not messages and gid == target_group_id:
        messages = list(legacy_recent_messages)
    human_messages = [m for m in messages if "机器人" not in str(m.get("role") or "")]
    if not human_messages:
        return "（暂无最近群友上下文）"
    focus_n = max(1, focus_messages)
    memory_n = max(0, memory_messages)
    focus = human_messages[-focus_n:]
    memory = human_messages[-(focus_n + memory_n):-focus_n] if memory_n else []
    lines = [
        "注意：主动发言有上下文权重衰减；高权重最近群友消息决定这次有没有自然接话点，低权重较早上下文只用于理解背景，不要把已过去的话题重新拉回。",
        "高权重：最近群友消息（优先围绕这里接话）",
    ]
    for idx, item in enumerate(focus, 1):
        lines.extend(format_context_item(idx, item, "高"))
    if memory:
        lines.append("低权重：较早上下文（只作为记忆背景，通常不要主动延续旧话题）")
        for idx, item in enumerate(memory, 1):
            lines.extend(format_context_item(idx, item, "低"))
    return "\n".join(lines)


def make_bot_reply_item(text: str, *, bot_id: str, max_chars: int) -> dict[str, Any]:
    return {"user_id": bot_id, "name": "Esti", "role": "机器人", "text": text[:max_chars]}


def make_bot_pending_reply_item(user_text: str, *, bot_id: str, max_chars: int) -> dict[str, Any]:
    text = re.sub(r"\s+", " ", user_text or "").strip() or "上一条提问"
    return {"user_id": bot_id, "name": "Esti", "role": "机器人，正在生成回复", "text": f"正在处理：{text[:max_chars - 6]}"}


def drop_last_bot_pending_reply(
    group_id: int | None,
    *,
    target_group_id: int,
    recent_messages_for_group_fn: Callable[[int], deque[dict[str, Any]]],
    legacy_recent_messages: deque[dict[str, Any]],
) -> bool:
    if group_id is None:
        return False
    changed = False
    messages = recent_messages_for_group_fn(group_id)
    if messages and "正在生成回复" in str(messages[-1].get("role") or ""):
        messages.pop()
        changed = True
    if group_id == target_group_id and legacy_recent_messages and "正在生成回复" in str(legacy_recent_messages[-1].get("role") or ""):
        legacy_recent_messages.pop()
        changed = True
    return changed
