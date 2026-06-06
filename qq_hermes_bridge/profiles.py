"""People/profile parsing helpers for group-scoped QQ bridge prompts.

This module is stateless and file-agnostic: callers provide loaded sections or a
loader callback. It can be reused by other chat adapters that keep people.md-like
Markdown profiles.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

from . import matching

NO_PERSON_PROFILE = "（没有该群友的资料）"
NO_TARGET_PROFILE = "（没有匹配到被询问对象的资料）"
NO_RELATED_PROFILE = "（没有按关键词匹配到相关群友资料）"


def field_values_from_section(section: str, field: str) -> list[str]:
    prefix_cn = f"- {field}："
    prefix_en = f"- {field}:"
    values: list[str] = []
    for line in section.splitlines():
        stripped = line.strip()
        if stripped.startswith(prefix_cn):
            raw = stripped.split("：", 1)[1]
        elif stripped.startswith(prefix_en):
            raw = stripped.split(":", 1)[1]
        else:
            continue
        values.extend([v.strip() for v in re.split(r"[、,，/\s]+", raw) if v.strip()])
    return values


def people_sections_from_text(text: str) -> list[str]:
    if not text:
        return []
    return [section.strip() for section in re.split(r"(?m)^##\s+", text)[1:] if section.strip()]


def people_sections(path: Path | None, *, default_path: Path, load_text_file_fn: Callable[[Path, str], str]) -> list[str]:
    profile_path = path if path is not None else default_path
    return people_sections_from_text(load_text_file_fn(profile_path, ""))


def primary_alias_from_section(section: str) -> str:
    nick_line = next((line for line in section.splitlines() if line.strip().startswith("- 昵称")), "")
    if not nick_line:
        return ""
    nick_part = nick_line.split("：", 1)[-1] if "：" in nick_line else nick_line.split(":", 1)[-1]
    aliases = [a.strip() for a in re.split(r"[、,，/\s]+", nick_part) if a.strip()]
    return aliases[0] if aliases else ""


def profile_display_name_by_qq(qq: str, sections: list[str]) -> str:
    for section in sections:
        header = section.splitlines()[0].strip()
        body = "## " + section
        if qq and (qq in header or qq in body):
            return primary_alias_from_section(section) or qq
    return qq


def extract_person_profile(user_id: Any, nickname: str, *, people_text: str, max_chars: int = 1500) -> str:
    if not people_text:
        return NO_PERSON_PROFILE
    candidates: list[str] = []
    uid = str(user_id or "")
    nick = str(nickname or "")
    for section in people_sections_from_text(people_text):
        body = section.strip()
        if not body:
            continue
        header = body.splitlines()[0].strip()
        if uid and uid in header:
            candidates.append("## " + body)
            continue
        if nick and nick in body:
            candidates.append("## " + body)
    if not candidates:
        return NO_PERSON_PROFILE
    return "\n\n".join(candidates)[:max_chars]


def mentioned_people_labels(
    event: dict[str, Any],
    *,
    self_id: str,
    display_name_by_qq_fn: Callable[[str], str],
) -> list[str]:
    labels: list[str] = []
    message = event.get("message")
    if isinstance(message, list):
        for seg in message:
            if not isinstance(seg, dict) or seg.get("type") != "at":
                continue
            data = seg.get("data") or {}
            qq = str(data.get("qq") or "")
            if not qq or qq == "all" or qq == self_id:
                continue
            name = str(data.get("name") or data.get("card") or data.get("nickname") or display_name_by_qq_fn(qq))
            labels.append(f"@{name}（QQ: {qq}）")
    elif isinstance(message, str):
        for qq in re.findall(r"\[CQ:at,qq=(\d+)\]", message):
            if qq != self_id:
                labels.append(f"@{display_name_by_qq_fn(qq)}（QQ: {qq}）")
    return list(dict.fromkeys(labels))


def extract_profiles_for_query(
    event: dict[str, Any],
    user_text: str,
    *,
    sections: list[str],
    self_id: str,
    max_chars: int = 2500,
) -> str:
    if not sections:
        return NO_TARGET_PROFILE

    mentioned_qqs: set[str] = set()
    message = event.get("message")
    if isinstance(message, list):
        for seg in message:
            if not isinstance(seg, dict) or seg.get("type") != "at":
                continue
            qq = str((seg.get("data") or {}).get("qq") or "")
            if qq and qq != "all" and qq != self_id:
                mentioned_qqs.add(qq)
    elif isinstance(message, str):
        for qq in re.findall(r"\[CQ:at,qq=(\d+)\]", message):
            if qq != self_id:
                mentioned_qqs.add(qq)

    matches: list[str] = []
    for section in sections:
        header = section.splitlines()[0].strip()
        body = "## " + section
        if any(qq in header or qq in body for qq in mentioned_qqs):
            matches.append(body)
            continue
        aliases = field_values_from_section(section, "昵称")
        if any(alias and alias in user_text for alias in aliases):
            matches.append(body)

    if not matches:
        return NO_TARGET_PROFILE
    return "\n\n".join(list(dict.fromkeys(matches)))[:max_chars]


def keyword_related_profiles(
    user_text: str,
    *,
    sections: list[str],
    min_keyword_len: int,
    max_matches: int,
    max_chars: int = 2500,
) -> str:
    if not sections:
        return NO_RELATED_PROFILE
    normalized_query = matching.strip_text_mentions(user_text)
    keywords = matching.extract_keyword_candidates(normalized_query, min_len=min_keyword_len)
    if not keywords:
        return NO_RELATED_PROFILE

    matches: list[tuple[int, str]] = []
    for section in sections:
        score = 0
        tags = field_values_from_section(section, "标签")
        for kw in keywords:
            if any(kw in tag or tag in kw for tag in tags):
                score += len(kw) * 10
            elif kw in section:
                score += len(kw)
        if score:
            matches.append((score, "## " + section))
    if not matches:
        return NO_RELATED_PROFILE
    matches.sort(key=lambda x: x[0], reverse=True)
    selected = [body for _, body in matches[:max_matches]]
    return "\n\n".join(selected)[:max_chars]
