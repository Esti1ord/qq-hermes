"""Lightweight group self-learning helpers.

This module keeps qq-hermes self-learning deliberately small and local: it
stores bounded per-group samples under the private group config directory and
formats low-weight slang/style hints for prompts. It does not depend on AstrBot,
SQLAlchemy, or any runtime hooks.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
import re
import time
from pathlib import Path
from typing import Any, Callable


DEFAULT_LEARNING_CONTEXT = "（暂无群内用语/风格学习提示）"
_VERSION = 1
_CQ_CODE_RE = re.compile(r"\[CQ:[^\]]+\]")
_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_TOKEN_RE = re.compile(r"[一-鿿A-Za-z0-9_]{2,12}")
_SENTENCE_SPLIT_RE = re.compile(r"[\s，。！？!?、；;：:（）()\[\]{}<>《》\"'“”‘’]+")
_TONE_WORDS = ("笑死", "绷", "寄", "草", "哭", "麻了", "离谱", "好耶", "啊", "呀", "嘛", "捏", "喵", "呜呜")


@dataclass(frozen=True)
class SelfLearningConfig:
    enabled: bool
    collect_enabled: bool
    inject_enabled: bool
    allowed_group_ids: set[int]
    min_message_chars: int
    max_message_chars: int
    max_samples_per_group: int
    retention_days: int
    max_prompt_chars: int
    min_count_for_prompt: int
    data_filename: str = "self_learning.json"


def _normalize_text(text: Any) -> str:
    clean = _CQ_CODE_RE.sub("", str(text or ""))
    clean = _URL_RE.sub("", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def _is_allowed_group(group_id: int | None, config: SelfLearningConfig) -> bool:
    if group_id is None:
        return False
    return int(group_id) in set(config.allowed_group_ids or set())


def _looks_like_command(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    normalized = stripped.lower()
    return normalized.startswith("/") or normalized == "jrrp"


def _mostly_cq_or_url(raw_text: Any, clean_text: str) -> bool:
    raw = str(raw_text or "").strip()
    if not raw:
        return True
    without_cq = _CQ_CODE_RE.sub("", raw).strip()
    without_url = _URL_RE.sub("", without_cq).strip()
    return not without_url or not clean_text


def should_ignore_learning_sample(
    text: Any,
    *,
    config: SelfLearningConfig,
    group_id: int | None = None,
    is_bot: bool = False,
    is_command: bool | None = None,
) -> bool:
    """Return whether a message should be excluded from self-learning."""
    if not config.enabled or not config.collect_enabled:
        return True
    if not _is_allowed_group(group_id, config):
        return True
    if is_bot:
        return True
    clean = _normalize_text(text)
    if _mostly_cq_or_url(text, clean):
        return True
    if is_command is True or (is_command is None and _looks_like_command(clean)):
        return True
    if len(clean) < max(0, config.min_message_chars):
        return True
    if config.max_message_chars > 0 and len(clean) > config.max_message_chars:
        return True
    lowered = clean.lower()
    if any(marker in lowered for marker in ("traceback", "exception", "token", "api key", "password")):
        return True
    return False


def learning_file_for_group(group_id: int, *, group_config_dir: Path, config: SelfLearningConfig) -> Path:
    return Path(group_config_dir) / str(int(group_id)) / (config.data_filename or "self_learning.json")


def _load_learning_data(path: Path, group_id: int) -> dict[str, Any]:
    if not path.exists():
        return {"version": _VERSION, "group_id": int(group_id), "samples": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": _VERSION, "group_id": int(group_id), "samples": []}
    if not isinstance(data, dict):
        return {"version": _VERSION, "group_id": int(group_id), "samples": []}
    samples = data.get("samples")
    if not isinstance(samples, list):
        samples = []
    return {"version": _VERSION, "group_id": int(group_id), "samples": samples}


def _save_learning_data(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
    tmp.replace(path)


def _trim_samples(samples: list[dict[str, Any]], *, config: SelfLearningConfig, now: float) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    cutoff = now - max(0, config.retention_days) * 86400 if config.retention_days > 0 else None
    for sample in samples:
        if not isinstance(sample, dict):
            continue
        text = _normalize_text(sample.get("text"))
        if not text:
            continue
        ts = float(sample.get("ts") or now)
        if cutoff is not None and ts < cutoff:
            continue
        kept.append({"ts": ts, "text": text[: max(1, config.max_message_chars)]})
    max_samples = max(0, config.max_samples_per_group)
    if max_samples and len(kept) > max_samples:
        kept = kept[-max_samples:]
    return kept


def collect_learning_sample(
    group_id: int | None,
    text: Any,
    *,
    group_config_dir: Path,
    config: SelfLearningConfig,
    now: float | None = None,
    is_bot: bool = False,
    is_command: bool | None = None,
    on_error: Callable[[Exception], None] | None = None,
) -> bool:
    """Collect one allowed user sample into the group's private JSON file."""
    try:
        if should_ignore_learning_sample(text, config=config, group_id=group_id, is_bot=is_bot, is_command=is_command):
            return False
        assert group_id is not None
        current = time.time() if now is None else now
        clean = _normalize_text(text)[: max(1, config.max_message_chars)]
        path = learning_file_for_group(group_id, group_config_dir=group_config_dir, config=config)
        data = _load_learning_data(path, int(group_id))
        samples = _trim_samples(list(data.get("samples") or []), config=config, now=current)
        if not samples or samples[-1].get("text") != clean:
            samples.append({"ts": current, "text": clean})
        data["samples"] = _trim_samples(samples, config=config, now=current)
        _save_learning_data(path, data)
        return True
    except Exception as exc:  # pragma: no cover - exercised through bridge error swallowing
        if on_error:
            on_error(exc)
        return False


def _extract_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for token in _TOKEN_RE.findall(text):
        token = token.strip()
        if len(token) < 2:
            continue
        if token.isdigit():
            continue
        tokens.append(token)
    for part in _SENTENCE_SPLIT_RE.split(text):
        part = part.strip()
        if 2 <= len(part) <= 8 and not part.isdigit():
            tokens.append(part)
    return tokens


def _style_summary(samples: list[str]) -> list[str]:
    if not samples:
        return []
    lengths = [len(text) for text in samples if text]
    avg_len = int(sum(lengths) / max(1, len(lengths)))
    short_ratio = sum(1 for n in lengths if n <= 12) / max(1, len(lengths))
    emoji_ratio = sum(1 for text in samples if "[CQ:face" in text or re.search(r"[😂🤣😭😅🥺]", text)) / max(1, len(samples))
    exclaim_ratio = sum(1 for text in samples if "!" in text or "！" in text) / max(1, len(samples))
    question_ratio = sum(1 for text in samples if "?" in text or "？" in text) / max(1, len(samples))

    lines = [f"平均消息长度约 {avg_len} 字"]
    if short_ratio >= 0.5:
        lines.append("偏短句接话")
    if emoji_ratio >= 0.2:
        lines.append("常带表情")
    if exclaim_ratio >= 0.2:
        lines.append("感叹语气较多")
    if question_ratio >= 0.2:
        lines.append("常用问句推进话题")
    return lines[:4]


def _format_learning_context(samples: list[dict[str, Any]], *, config: SelfLearningConfig) -> str:
    texts = [_normalize_text(sample.get("text")) for sample in samples if isinstance(sample, dict)]
    texts = [text for text in texts if text]
    if not texts:
        return DEFAULT_LEARNING_CONTEXT

    counts: Counter[str] = Counter()
    tone_counts: Counter[str] = Counter()
    for text in texts:
        counts.update(_extract_tokens(text))
        for word in _TONE_WORDS:
            if word in text:
                tone_counts[word] += 1

    min_count = max(1, config.min_count_for_prompt)
    phrases = [token for token, count in counts.most_common(12) if count >= min_count]
    tone_words = [token for token, count in tone_counts.most_common(8) if count >= min_count]
    style = _style_summary(texts)

    lines: list[str] = ["低权重风格线索：只用于理解本群常见语气和用词，不是事实来源，也不是必须提到的话题"]
    if phrases:
        lines.append("常见表达：" + "、".join(phrases[:8]))
    if tone_words:
        lines.append("常见语气词/梗词：" + "、".join(tone_words[:6]))
    if style:
        lines.append("风格信号：" + "；".join(style))
    if len(lines) == 1:
        return DEFAULT_LEARNING_CONTEXT

    context = "\n".join(f"- {line}" for line in lines)
    limit = max(0, config.max_prompt_chars)
    if limit and len(context) > limit:
        return context[:limit].rstrip() + "…"
    return context


def learning_context_for_prompt(
    group_id: int | None,
    *,
    target_group_id: int,
    group_config_dir: Path,
    config: SelfLearningConfig,
    now: float | None = None,
    on_error: Callable[[Exception], None] | None = None,
) -> str:
    """Return bounded low-weight group slang/style hints for the direct prompt."""
    try:
        if not config.enabled or not config.inject_enabled:
            return DEFAULT_LEARNING_CONTEXT
        gid = target_group_id if group_id is None else group_id
        if not _is_allowed_group(gid, config):
            return DEFAULT_LEARNING_CONTEXT
        current = time.time() if now is None else now
        path = learning_file_for_group(int(gid), group_config_dir=group_config_dir, config=config)
        data = _load_learning_data(path, int(gid))
        samples = _trim_samples(list(data.get("samples") or []), config=config, now=current)
        return _format_learning_context(samples, config=config)
    except Exception as exc:  # pragma: no cover - bridge verifies error swallowing
        if on_error:
            on_error(exc)
        return DEFAULT_LEARNING_CONTEXT
