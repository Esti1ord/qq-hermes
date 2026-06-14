"""Deterministic JRRP (今日人品) command helpers.

File paths and logging callbacks are provided by callers so this module can be
reused by other chat bridges without depending on QQ/Hermes bridge globals.
"""
from __future__ import annotations

import hashlib
import json
import random
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from . import matching

DEFAULT_RESULTS: dict[str, Any] = {
    "levels": [
        {
            "name": "天选之人",
            "min": 100,
            "max": 100,
            "faces": ["✧*｡٩(ˊᗜˋ*)و✧*｡", "ヾ(≧▽≦*)o", "ᕕ( ᐛ )ᕗ"],
            "comments": [
                "今日运势突破上限，随机数都在偏爱你。",
                "人品值直接拉满，建议截图留念。",
                "天选之人已上线，普通好运已经配不上你了。",
            ],
        },
        {
            "name": "大吉",
            "min": 90,
            "max": 99,
            "faces": ["٩(ˊᗜˋ*)و", "ヽ(✿ﾟ▽ﾟ)ノ", "╰(*°▽°*)╯"],
            "comments": [
                "好运在线，建议大胆出击。",
                "今天状态很好，适合推进重要事项。",
                "今日人品优秀，群友看了都要沾一沾。",
            ],
        },
        {
            "name": "中吉",
            "min": 75,
            "max": 89,
            "faces": ["(｡･ω･｡)ﾉ", "(￣▽￣)~*", "(｡•̀ᴗ-)✧"],
            "comments": [
                "状态不错，稳中有喜。",
                "整体运势偏上，适合正常发挥。",
                "好运不算夸张，但足够支撑你赢一小局。",
            ],
        },
        {
            "name": "小吉",
            "min": 60,
            "max": 74,
            "faces": ["(・ω・)ノ", "(๑´ㅂ`๑)", "(ง ˘ω˘ )ว"],
            "comments": [
                "小有好运，适合做点轻松的事。",
                "运势温和上扬，适合慢慢来。",
                "小吉护体，问题不大。",
            ],
        },
        {
            "name": "平",
            "min": 40,
            "max": 59,
            "faces": ["(￣ω￣)", "(・_・)", "(。・・)ノ"],
            "comments": [
                "风平浪静，正常发挥即可。",
                "今日运势平稳，没有明显增益或减益。",
                "平平淡淡才是真，稳住就行。",
            ],
        },
        {
            "name": "小凶",
            "min": 20,
            "max": 39,
            "faces": ["_(:з」∠)_", "(；′⌒`)", "(つ﹏⊂)"],
            "comments": [
                "略有波折，谨慎一点问题不大。",
                "今天可能有点卡手，建议别硬冲。",
                "今天建议稳一点，别和概率较劲。",
            ],
        },
        {
            "name": "凶",
            "min": 5,
            "max": 19,
            "faces": ["(╯°□°）╯︵ ┻━┻", "(；д；)", "_(:3」∠)_"],
            "comments": [
                "今日运势偏低，建议先别上头。",
                "今天适合保守行事，能不赌就不赌。",
                "建议低调一点，等明天再战。",
            ],
        },
        {
            "name": "大凶",
            "min": 0,
            "max": 4,
            "faces": ["Σ(っ °Д °;)っ", "(╥﹏╥)", "_(:з」∠)_"],
            "comments": [
                "今日运势触底，建议立刻进入防御姿态。",
                "随机数下手有点重，今天先苟住。",
                "今日适合低调潜行，别和概率硬碰硬。",
            ],
        },
    ]
}
JRRP_SCORE_COMPONENTS: tuple[tuple[float, float, float], ...] = (
    (0.70, 75.0, 8.0),
    (0.20, 65.0, 18.0),
    (0.10, 45.0, 22.0),
)
JRRP_SCORE_TOTAL_WEIGHT = sum(weight for weight, _, _ in JRRP_SCORE_COMPONENTS)
JRRP_SCORE_RETRY_LIMIT = 64
DEFAULT_LEVEL = DEFAULT_RESULTS["levels"][4]


def is_jrrp_command(text: str) -> bool:
    """Trigger only when the whole normalized message equals jrrp."""
    return matching.exact_normalized_match(text, "jrrp") | matching.exact_normalized_match(text, "jrro")


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


def _score_component(rng: random.Random) -> tuple[float, float]:
    marker = rng.random() * JRRP_SCORE_TOTAL_WEIGHT
    cumulative = 0.0
    for weight, mean, stdev in JRRP_SCORE_COMPONENTS:
        cumulative += weight
        if marker <= cumulative:
            return mean, stdev
    _, mean, stdev = JRRP_SCORE_COMPONENTS[-1]
    return mean, stdev


def score_for_seed(seed: str) -> int:
    rng = random.Random(f"{seed}:score")
    for _ in range(JRRP_SCORE_RETRY_LIMIT):
        mean, stdev = _score_component(rng)
        sample = rng.gauss(mean, stdev)
        if 0 <= sample <= 100:
            return round(sample)
    return round(JRRP_SCORE_COMPONENTS[0][1])


def _matching_level(levels: Any, score: int) -> dict[str, Any] | None:
    if not isinstance(levels, list):
        return None
    for level in levels:
        if not isinstance(level, dict) or "min" not in level or "max" not in level or not level.get("name"):
            continue
        try:
            lo = int(level["min"])
            hi = int(level["max"])
        except Exception:
            continue
        if lo <= hi and lo <= score <= hi:
            return level
    return None


def level_for_score(results: dict[str, Any], score: int) -> dict[str, Any]:
    levels = results.get("levels") if isinstance(results, dict) else None
    return _matching_level(levels, score) or _matching_level(DEFAULT_RESULTS["levels"], score) or DEFAULT_LEVEL


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
    score = score_for_seed(seed)
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
