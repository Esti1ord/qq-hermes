"""Stateless command parsing helpers for chat bridge text.

These helpers only parse command syntax. Command execution remains in the bridge
or command modules so parsing can be reused by other adapters without carrying
QQ/Hermes runtime state.
"""
from __future__ import annotations

import re

from . import matching


def normalized_command_text(text: str) -> str:
    return matching.normalize_spaces(text)


def has_slash_command(text: str, command: str) -> bool:
    normalized = normalized_command_text(text)
    return bool(re.search(rf"(?:^|\s)/{re.escape(command)}(?:\s|$)", normalized, flags=re.IGNORECASE))


def slash_command_query(text: str, command: str) -> str:
    normalized = normalized_command_text(text)
    normalized = re.sub(r"^@\S+\s+", "", normalized)
    match = re.search(rf"(?:^|\s)/{re.escape(command)}(?:\s|$)", normalized, flags=re.IGNORECASE)
    if not match:
        return normalized.strip()
    return normalized[match.end():].strip()


def is_context_command(text: str) -> bool:
    return has_slash_command(text, "context")
