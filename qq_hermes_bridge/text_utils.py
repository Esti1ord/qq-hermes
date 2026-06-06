"""Reusable text-cleanup helpers for QQ/Hermes bridge replies.

The helpers in this module are intentionally stateless: callers pass runtime
configuration such as length limits and punctuation-style flags explicitly. This
keeps them reusable across command handlers, tests, and future bridge adapters.
"""
from __future__ import annotations

import re

AI_PHRASES = [
    "作为一个AI，",
    "作为一个 AI，",
    "作为AI，",
    "作为 AI，",
    "我无法真正体验。",
    "我无法真正体验",
    "希望这能帮到你。",
    "希望这能帮到你",
]


def apply_punctuation_style(text: str, enabled: bool = True) -> str:
    if not enabled:
        return text
    out = (text or "").strip()
    if not out:
        return out
    # 群聊短回复尽量像手打：去句号/引号，短句用空格替代逗号顿号。
    replacements = {
        "。": "",
        ".": "",
        "“": "",
        "”": "",
        '"': "",
        "‘": "",
        "’": "",
        "'": "",
        "、": " ",
    }
    for old, new in replacements.items():
        out = out.replace(old, new)
    if len(out) <= 80:
        out = out.replace("，", " ").replace(",", " ")
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r" *\n *", "\n", out)
    return out.strip()


def normalize_reply_linebreaks(text: str) -> str:
    """Flatten casual replies while preserving structured code/list formatting."""
    out = (text or "").strip()
    if not out:
        return out
    has_structured_format = "```" in out or re.search(r"(?m)^\s*(?:[-*+]\s+|\d+[.)、]\s+)", out)
    if has_structured_format:
        out = re.sub(r"[ \t]*\n[ \t]*", "\n", out)
        return re.sub(r"\n{3,}", "\n\n", out).strip()
    return re.sub(r"\s*\n+\s*", " ", out).strip()


def prepare_reply_text(text: str, punctuation_style_enabled: bool = True) -> str:
    """Clean reply text without truncating it."""
    out = (text or "").strip()
    for phrase in AI_PHRASES:
        out = out.replace(phrase, "")
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    if "⏱" in out or "Timeout" in out or "denying command" in out:
        out = re.sub(r"⏱\s*Timeout\s*[—-]\s*denying command", "", out, flags=re.I).strip()
        out = re.sub(r"Timeout\s*[—-]\s*denying command", "", out, flags=re.I).strip()
    out = normalize_reply_linebreaks(out)
    out = apply_punctuation_style(out, enabled=punctuation_style_enabled)
    return out


def finalize_reply(
    text: str,
    *,
    max_chars: int,
    empty_reply: str,
    punctuation_style_enabled: bool = True,
) -> str:
    """Clean a normal reply and enforce the caller's hard character budget."""
    out = prepare_reply_text(text, punctuation_style_enabled=punctuation_style_enabled)
    if not out:
        out = empty_reply
    return out[:max_chars]


def whole_clause_fit(
    text: str,
    limit: int,
    *,
    punctuation_style_enabled: bool = True,
    fallback: str = "这题信息量比较大，建议拆成一个更具体的问题，我再给完整路线。",
) -> str:
    """Fit text to a limit by keeping complete clauses instead of hard cutting."""
    raw = (text or "").strip()
    clean = prepare_reply_text(raw, punctuation_style_enabled=punctuation_style_enabled)
    if len(clean) <= limit:
        return clean
    # 先按原始标点切分，再套 QQ 标点风格；否则 prepare_reply_text 会移除句号导致无法判断句界。
    parts = [p for p in re.split(r"(?<=[。！？!?；;])|(?<=，)|(?<=,)|\s+(?=\d+[）).、])", raw) if p.strip()]
    out = ""
    for part in parts:
        prepared_part = prepare_reply_text(part, punctuation_style_enabled=punctuation_style_enabled)
        candidate = (out + prepared_part).strip()
        if len(candidate) <= limit:
            out = candidate
        elif out:
            break
    return out or fallback
