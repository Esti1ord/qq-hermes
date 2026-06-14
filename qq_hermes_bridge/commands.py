"""Command reply and prompt builders for the QQ/Hermes bridge.

This module keeps command-specific text construction stateless. Runtime I/O
(subprocess, OneBot, group cache lookup) stays in bridge.py and is injected via
arguments so tests can cover formatting without booting the bridge service.
"""
from __future__ import annotations

import re
from typing import Any, Callable

from . import prompt_service


def clean_query(query: str, *, limit: int | None = None) -> str:
    clean = re.sub(r"\s+", " ", query or "").strip()
    return clean[:limit] if limit is not None else clean


def is_context_command_bot_output(item: dict[str, Any], *, reply_prefix: str = "") -> bool:
    text = str(item.get("text") or "").lstrip()
    if reply_prefix and text.startswith(reply_prefix):
        text = text[len(reply_prefix):].lstrip()
    return "机器人" in str(item.get("role") or "") and text.startswith("我现在记住的前情")


def clip_context_line(text: Any, limit: int = 80) -> str:
    clean = re.sub(r"\s+", " ", str(text or "")).strip()
    return clean[:limit] + ("…" if len(clean) > limit else "")


def append_context_line_with_budget(lines: list[str], line: str, budget: int) -> bool:
    candidate = "\n".join(lines + [line])
    if len(candidate) <= budget:
        lines.append(line)
        return True
    return False


def build_rendered_chat_prompt(
    *,
    group_id: int | None,
    date_context: str,
    context_summaries: str,
    recent_context: str,
    reply_context: str,
    reply_to_bot_note: str,
    nick: str,
    user_id: Any,
    mentioned_labels: str,
    user_text: str,
    person_profile: str,
    mentioned_profiles: str,
    related_profiles: str,
    persona: str,
    max_prompt_chars: int,
    style_hint: str,
    media_context: str = "（当前消息没有图片识别结果）",
    learning_context: str = "（暂无群内用语/风格学习提示）",
    direct_prompt_profile: str = "rich",
    total_budget_chars: int | None = None,
) -> prompt_service.RenderedPrompt:
    return prompt_service.build_rendered_chat_prompt(
        group_id=group_id,
        date_context=date_context,
        context_summaries=context_summaries,
        recent_context=recent_context,
        reply_context=reply_context,
        reply_to_bot_note=reply_to_bot_note,
        nick=nick,
        user_id=user_id,
        mentioned_labels=mentioned_labels,
        user_text=user_text,
        person_profile=person_profile,
        mentioned_profiles=mentioned_profiles,
        related_profiles=related_profiles,
        persona=persona,
        max_prompt_chars=max_prompt_chars,
        style_hint=style_hint,
        media_context=media_context,
        learning_context=learning_context,
        direct_prompt_profile=direct_prompt_profile,
        total_budget_chars=total_budget_chars,
    )


def build_chat_prompt(
    *,
    group_id: int | None,
    date_context: str,
    context_summaries: str,
    recent_context: str,
    reply_context: str,
    reply_to_bot_note: str,
    nick: str,
    user_id: Any,
    mentioned_labels: str,
    user_text: str,
    person_profile: str,
    mentioned_profiles: str,
    related_profiles: str,
    persona: str,
    max_prompt_chars: int,
    style_hint: str,
    media_context: str = "（当前消息没有图片识别结果）",
    learning_context: str = "（暂无群内用语/风格学习提示）",
    direct_prompt_profile: str = "rich",
    total_budget_chars: int | None = None,
) -> str:
    return build_rendered_chat_prompt(
        group_id=group_id,
        date_context=date_context,
        context_summaries=context_summaries,
        recent_context=recent_context,
        reply_context=reply_context,
        reply_to_bot_note=reply_to_bot_note,
        nick=nick,
        user_id=user_id,
        mentioned_labels=mentioned_labels,
        user_text=user_text,
        person_profile=person_profile,
        mentioned_profiles=mentioned_profiles,
        related_profiles=related_profiles,
        persona=persona,
        max_prompt_chars=max_prompt_chars,
        style_hint=style_hint,
        media_context=media_context,
        learning_context=learning_context,
        direct_prompt_profile=direct_prompt_profile,
        total_budget_chars=total_budget_chars,
    ).text


def build_rendered_proactive_prompt(
    *,
    group_id: int | None,
    date_context: str,
    context_summaries: str,
    recent_context: str,
    persona: str,
    reasons: list[str],
) -> prompt_service.RenderedPrompt:
    return prompt_service.build_rendered_proactive_prompt(
        group_id=group_id,
        date_context=date_context,
        context_summaries=context_summaries,
        recent_context=recent_context,
        persona=persona,
        reasons=reasons,
    )


def build_proactive_prompt(
    *,
    group_id: int | None,
    date_context: str,
    context_summaries: str,
    recent_context: str,
    persona: str,
    reasons: list[str],
) -> str:
    return build_rendered_proactive_prompt(
        group_id=group_id,
        date_context=date_context,
        context_summaries=context_summaries,
        recent_context=recent_context,
        persona=persona,
        reasons=reasons,
    ).text


def build_context_command_reply(
    *,
    summaries: list[str],
    messages: list[dict[str, Any]],
    fallback_messages: list[dict[str, Any]] | None = None,
    target_group: bool = False,
    max_reply_chars: int = 450,
    reply_prefix: str = "",
    is_context_command_fn: Callable[[str], bool] | None = None,
) -> str:
    """Build the deterministic /context reply from already-loaded context."""
    budget = min(max_reply_chars, 360)
    effective_messages = list(messages)
    if not effective_messages and target_group:
        effective_messages = list(fallback_messages or [])

    def is_context_command_text(text: str) -> bool:
        return is_context_command_fn(text) if is_context_command_fn else text.strip() == "/context"

    visible_messages = [
        m for m in effective_messages
        if not is_context_command_text(str(m.get("text") or ""))
        and not is_context_command_bot_output(m, reply_prefix=reply_prefix)
    ]
    recent = visible_messages[-3:]

    lines = ["我现在记住的前情：", "近况摘要："]
    if summaries:
        added = 0
        for summary in summaries:
            if append_context_line_with_budget(lines, f"- {clip_context_line(summary, 52)}", budget):
                added += 1
            else:
                break
        if added == 0:
            lines.append("- 有摘要 但这次太长先不展开")
    else:
        lines.append("- 暂无精炼摘要")

    if append_context_line_with_budget(lines, "最近消息：", budget):
        added_recent = 0
        for item in recent:
            name = clip_context_line(item.get("name") or item.get("user_id") or "群友", 12)
            text = clip_context_line(item.get("text") or "", 42)
            role = str(item.get("role") or "").strip()
            suffix = "（机器人）" if "机器人" in role else ""
            if append_context_line_with_budget(lines, f"- {name}{suffix}：{text}", budget):
                added_recent += 1
            else:
                break
        if not recent:
            append_context_line_with_budget(lines, "- 暂无最近上下文", budget)
        elif added_recent == 0:
            lines.pop()

    return "\n".join(lines)
