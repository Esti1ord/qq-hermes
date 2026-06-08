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


def build_search_command_prompt(query: str, *, date_context: str, knowledge: str) -> str:
    clean = clean_query(query, limit=300)
    return f"""联网搜索命令 /search 的内部查询任务。只服务本次显式搜索，不写入普通聊天模型 session。
{date_context}

本群知识库（仅作为搜索源和查证方向，不是最终事实；不要在回复中暴露你在读知识库）：
{knowledge}

搜索问题：{clean}
规则：优先使用知识库给出的来源和官方/主流来源；区分实时事实、传闻和不确定信息；没查到可靠结果就直说没查准，不要编。"""


def build_deepseek_command_prompt(
    query: str,
    search_result: str,
    *,
    date_context: str,
    knowledge: str,
    max_reply_chars: int,
) -> str:
    clean = clean_query(query, limit=500)
    return f"""你正在处理 QQ 群里的 /deepseek 深度思考命令。注意：命令名与 DeepSeek 模型无关；你必须作为一个全新的独立对话回答，不继承任何群聊上下文、缓存摘要、历史 persona 或普通聊天 session。
{date_context}

用户问题：{clean}

联网搜索/查证结果（仅作为证据，不足时要说明不确定）：
{(search_result or '（没有拿到可靠搜索结果）')[:2500]}

本群搜索专用知识库（只作来源提示，不要暴露你在读知识库）：
{knowledge[:1200]}

回答要求：
- 进入深度思考模式：先综合证据和常识，给出清晰结论，再补关键理由/步骤/风险点。
- 可以比普通群聊更详细，但必须适合 QQ 单条消息，整体必须自然写完，不要超过 {max_reply_chars} 字；不要靠截断变短。
- 不要说“根据之前聊天/上下文”；本命令不使用之前上下文。
- 不要编造搜索结果；证据不足就明确说不确定。
- 输出中文，一段为主，必要时可用短列表。"""


def build_compress_deepseek_prompt(
    *,
    query: str,
    draft: str,
    search_result: str,
    budget: int,
) -> str:
    return f"""把下面 /deepseek 深度回答重写成适合 QQ 单条发送的完整短答。不是截取，不要留下半句话；必须保留结论、关键路线/理由、风险提醒；总字数严格小于 {budget} 字。

用户问题：{query[:300]}
搜索要点：{(search_result or '')[:800]}
原回答：{draft[:2000]}

只输出改写后的中文答案。"""


def finalize_deepseek_command_reply(
    raw: str,
    *,
    query: str,
    search_result: str,
    max_reply_chars: int,
    strip_session_footer_fn: Callable[[str], str],
    prepare_reply_text_fn: Callable[[str], str],
    empty_reply_fn: Callable[[str, str], str],
    compress_fn: Callable[..., str],
    whole_clause_fit_fn: Callable[[str, int], str],
    group_id: int | None = None,
) -> str:
    raw_clean = strip_session_footer_fn(raw or "")
    prepared = prepare_reply_text_fn(raw_clean)
    if not prepared:
        return empty_reply_fn(raw or "", query)
    if len(prepared) <= max_reply_chars:
        return prepared
    compressed = compress_fn(query, prepared, search_result, group_id=group_id)
    if compressed and len(compressed) <= max_reply_chars:
        return compressed
    if compressed:
        second = compress_fn(query, compressed, search_result, group_id=group_id)
        if second and len(second) <= max_reply_chars:
            return second
        return whole_clause_fit_fn(second or compressed, max_reply_chars)
    return whole_clause_fit_fn(raw_clean, max_reply_chars)
