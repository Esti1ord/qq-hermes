"""Structured prompt builders for direct and proactive QQ/Hermes replies.

The service keeps prompt construction pure: callers collect runtime context,
profiles, OCR text, and persona data, then pass those strings here. Hermes still
receives a normal string, but the prompt is assembled from explicit sections so
source and priority stay testable.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PromptKind = Literal["direct", "proactive"]
PromptSource = Literal[
    "runtime_policy",
    "current_message",
    "recent_context",
    "quoted_context",
    "generated_summary",
    "media_recognition",
    "group_profile",
    "self_learning",
    "persona",
    "internal_diagnostic",
]
PromptPriority = Literal["critical", "high", "medium", "low"]


@dataclass(frozen=True)
class PromptSection:
    key: str
    title: str
    body: str
    source: PromptSource
    priority: PromptPriority
    instruction: str = ""


@dataclass(frozen=True)
class PromptRequest:
    kind: PromptKind
    group_id: int | None
    date_context: str
    sections: list[PromptSection]
    rules: list[str]
    output_contract: str
    max_prompt_chars: int | None = None


@dataclass(frozen=True)
class RenderedPrompt:
    text: str
    section_keys: tuple[str, ...]
    char_count: int


def _clean_body(body: object) -> str:
    text = str(body or "").strip()
    return text or "（无）"


def render_prompt(request: PromptRequest) -> RenderedPrompt:
    """Render a PromptRequest into a Hermes-compatible prompt string."""
    lines: list[str] = [
        "你正在为 QQ 群聊生成回复。请按各 section 的来源、优先级和使用说明判断权重。",
        f"类型：{request.kind}",
        f"群号：{request.group_id}",
        f"当前日期：{request.date_context}",
    ]

    for section in request.sections:
        lines.extend([
            "",
            f"## {section.title}",
            f"来源：{section.source}",
            f"优先级：{section.priority}",
        ])
        if section.instruction:
            lines.append(f"使用说明：{section.instruction}")
        lines.append(_clean_body(section.body))

    if request.rules:
        lines.extend(["", "## 规则"])
        lines.extend(f"- {rule}" for rule in request.rules if str(rule or "").strip())

    lines.extend(["", "## 输出要求", _clean_body(request.output_contract)])
    text = "\n".join(lines)
    return RenderedPrompt(
        text=text,
        section_keys=tuple(section.key for section in request.sections),
        char_count=len(text),
    )
