"""Deterministic JRRP (今日人品) command helpers.

File paths and logging callbacks are provided by callers so this module can be
reused by other chat bridges without depending on QQ/Hermes bridge globals.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from . import matching

DEFAULT_LEVEL = {"name": "平", "faces": ["(￣ω￣)"], "comments": ["风平浪静，正常发挥即可。"]}


def is_jrrp_command(text: str) -> bool:
    """Trigger only when the whole normalized message equals jrrp."""
    return matching.exact_normalized_match(text, "jrrp")


def load_json_dict(path: Path, *, on_error: Callable[[Exception], None] | None = None) -> dict[str, Any]:
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception as exc:
        if on_error is not None:
            on_error(exc)
    return {}


def save_json_dict(path: Path, state: dict[str, Any], *, on_error: Callable[[Exception], None] | None = None) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        if on_error is not None:
            on_error(exc)


def pick_option(options: Any, seed: str, salt: str) -> str:
    if not isinstance(options, list) or not options:
        return ""
    idx = int(hashlib.sha256(f"{seed}:{salt}".encode("utf-8")).hexdigest()[:8], 16) % len(options)
    return str(options[idx])


def level_for_score(results: dict[str, Any], score: int) -> dict[str, Any]:
    levels = results.get("levels") if isinstance(results, dict) else None
    if isinstance(levels, list):
        for level in levels:
            try:
                lo = int(level.get("min", 0))
                hi = int(level.get("max", 100))
            except Exception:
                continue
            if lo <= score <= hi:
                return level
    return DEFAULT_LEVEL


def build_jrrp_reply(
    user_id: Any,
    nickname: str = "",
    now: datetime | None = None,
    *,
    load_state_fn: Callable[[], dict[str, Any]],
    save_state_fn: Callable[[dict[str, Any]], None],
    load_results_fn: Callable[[], dict[str, Any]],
) -> tuple[str, bool]:
    now = now or datetime.now()
    qq = str(user_id or "0")
    day = now.strftime("%Y%m%d")
    state_key = f"{day}:{qq}"
    state = load_state_fn()
    if state_key in state:
        return "你今日已经抽过了", False
    seed = now.strftime("%Y%m%d%H%M%S") + qq
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    score = int(digest[:8], 16) % 101
    results = load_results_fn()
    level = level_for_score(results, score)
    level_name = str(level.get("name") or "平")
    face = pick_option(level.get("faces"), seed, "face")
    comment = pick_option(level.get("comments"), seed, "comment")
    mention = f"@{nickname} " if nickname else ""
    line2 = f"判定：{level_name}{(' ' + face) if face else ''}"
    lines = [f"{mention}今日人品：{score}/100", line2]
    if comment:
        lines.append(comment)
    reply = "\n".join(lines)
    state[state_key] = {"seed": seed, "score": score, "level": level_name, "ts": now.isoformat()}
    save_state_fn(state)
    return reply, True
