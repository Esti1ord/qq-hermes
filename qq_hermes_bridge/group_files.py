"""Group-scoped file helpers for QQ/Hermes bridge prompts.

The functions are parameterized instead of reading bridge globals directly. This
makes them reusable for other adapters and keeps bridge.py free to preserve its
legacy monkeypatchable globals during staged refactors.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from . import matching

DEFAULT_KNOWLEDGE_FALLBACK = "（本群没有配置知识库；涉及事实请优先依靠联网搜索和明确来源，不要编造。）"
DEFAULT_GROUP_PROMPT_FALLBACK = "（本群没有额外群聊提示词）"
DEFAULT_BASE_PERSONA_FALLBACK = "你是 QQ 群里的机器人伙伴 Esti，像熟人群友一样自然、简短、有边界地聊天。"
NORMAL_CHAT_KNOWLEDGE_NOTICE = "（普通聊天不读取知识库；需要查证请使用 /search 命令。）"

SEARCH_GUIDANCE_MARKERS = [
    "联网搜索",
    "联网核对",
    "实时信息",
    "实时内容",
    "实时事实",
    "实时新闻",
    "先查实时",
    "查实时",
    "仍要联网",
]


def load_text_file(path: Path, fallback: str, *, on_error: Callable[[Exception, Path], None] | None = None) -> str:
    try:
        text = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return fallback
    except Exception as exc:
        if on_error is not None:
            on_error(exc, path)
        return fallback
    return text or fallback


def persona_file_for_group(
    group_id: int,
    *,
    group_config_dir: Path,
    target_group_id: int,
    persona_file: Path,
    default_persona_file: Path,
    default_group_config_dir: Path,
) -> Path:
    candidate = group_config_dir / str(group_id) / "persona.md"
    if candidate.exists():
        return candidate
    if group_id == target_group_id and (persona_file != default_persona_file or group_config_dir == default_group_config_dir):
        return persona_file
    return candidate


def knowledge_file_for_group(group_id: int, *, group_config_dir: Path) -> Path:
    return group_config_dir / str(group_id) / "knowledge.md"


def group_people_file_for_group(
    group_id: int,
    *,
    group_config_dir: Path,
    target_group_id: int,
    people_file: Path,
    default_people_file: Path,
    default_group_config_dir: Path,
) -> Path | None:
    candidate = group_config_dir / str(group_id) / "people.md"
    if candidate.exists():
        return candidate
    if group_id == target_group_id and (people_file != default_people_file or group_config_dir == default_group_config_dir):
        return people_file
    return None


def group_people_file_for_prompt(
    group_id: int,
    *,
    target_group_id: int,
    people_file: Path,
    persona_file: Path,
    default_people_file: Path,
    default_persona_file: Path,
    group_people_file_for_group_fn: Callable[[int], Path | None],
) -> Path | None:
    if group_id == target_group_id and (people_file != default_people_file or persona_file != default_persona_file):
        return people_file
    return group_people_file_for_group_fn(group_id)


def persona_file_for_prompt(
    group_id: int,
    *,
    target_group_id: int,
    people_file: Path,
    persona_file: Path,
    default_people_file: Path,
    default_persona_file: Path,
    persona_file_for_group_fn: Callable[[int], Path],
) -> Path:
    if group_id == target_group_id and (people_file != default_people_file or persona_file != default_persona_file):
        return persona_file
    return persona_file_for_group_fn(group_id)


def knowledge_for_prompt(
    group_id: int | None,
    *,
    target_group_id: int,
    knowledge_max_chars: int,
    knowledge_file_for_group_fn: Callable[[int], Path],
    load_text_file_fn: Callable[[Path, str], str],
    fallback: str = DEFAULT_KNOWLEDGE_FALLBACK,
) -> str:
    gid = group_id if group_id is not None else target_group_id
    return load_text_file_fn(knowledge_file_for_group_fn(gid), fallback)[:knowledge_max_chars]


def group_prompt_for_prompt(
    group_id: int,
    *,
    persona_file_for_prompt_fn: Callable[[int], Path],
    load_text_file_fn: Callable[[Path, str], str],
    fallback: str = DEFAULT_GROUP_PROMPT_FALLBACK,
) -> str:
    return load_text_file_fn(persona_file_for_prompt_fn(group_id), fallback)


def base_persona_for_prompt(
    *,
    base_persona_file: Path,
    load_text_file_fn: Callable[[Path, str], str],
    fallback: str = DEFAULT_BASE_PERSONA_FALLBACK,
) -> str:
    return load_text_file_fn(base_persona_file, fallback)


def persona_bundle_for_prompt(
    group_id: int | None,
    *,
    base_persona_for_prompt_fn: Callable[[], str],
    group_prompt_for_prompt_fn: Callable[[int], str],
) -> str:
    return f"""基础人设：
{base_persona_for_prompt_fn()}

群聊提示词：
{group_prompt_for_prompt_fn(group_id)}"""


def strip_normal_chat_search_guidance(text: str, markers: list[str] | None = None) -> str:
    """Remove stale live-search instructions from normal chat persona/knowledge."""
    markers = markers or SEARCH_GUIDANCE_MARKERS
    lines = []
    for line in (text or "").splitlines():
        if matching.contains_any_phrase(line, markers):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def normal_chat_persona_bundle_for_prompt(
    group_id: int | None,
    *,
    persona_bundle_for_prompt_fn: Callable[[int | None], str],
) -> str:
    return strip_normal_chat_search_guidance(persona_bundle_for_prompt_fn(group_id))


def normal_chat_knowledge_for_prompt() -> str:
    return NORMAL_CHAT_KNOWLEDGE_NOTICE
