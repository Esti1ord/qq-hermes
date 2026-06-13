"""Lightweight group self-learning helpers.

This module keeps qq-hermes self-learning deliberately small and local: it
stores bounded per-group samples under the private group config directory and
formats low-weight slang/style hints for prompts. It does not depend on AstrBot,
SQLAlchemy, or any runtime hooks.
"""
from __future__ import annotations

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
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9:_-]{1,96}$")
_MAX_MANUAL_ENTRY_CHARS = 600
_MANUAL_ENTRY_TYPES = {"prompt_guidance", "memory", "self_learning"}


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


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _entry_disabled(item: dict[str, Any]) -> bool:
    status = str(item.get("status") or "").strip().lower()
    return bool(item.get("disabled") or item.get("enabled") is False or status == "disabled")


def _safe_id(value: Any) -> str:
    text = str(value or "").strip()
    if text and _SAFE_ID_RE.fullmatch(text):
        return text
    return ""


def _manual_entry_type(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"guidance", "prompt", "prompt-guidance", "prompt_guidance"}:
        return "prompt_guidance"
    if text in {"meme", "style", "selflearning", "self-learning", "self_learning"}:
        return "self_learning"
    if text in {"memory", "note", "fact"}:
        return "memory"
    if text in _MANUAL_ENTRY_TYPES:
        return text
    return "memory"


def _clamped_reinforcement(value: Any) -> int:
    return max(0, min(999, _safe_int(value, 0)))


def _clamped_weight(value: Any, default: float = 1.0) -> float:
    return round(max(0.0, min(100.0, _safe_float(value, default))), 3)


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
    empty = {"version": _VERSION, "group_id": int(group_id), "samples": [], "manual_entries": []}
    if not path.exists():
        return empty
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return empty
    if not isinstance(data, dict):
        return empty
    samples = data.get("samples")
    if not isinstance(samples, list):
        samples = []
    manual_entries = data.get("manual_entries")
    if not isinstance(manual_entries, list):
        manual_entries = []
    return {
        "version": _VERSION,
        "group_id": int(group_id),
        "samples": samples,
        "manual_entries": manual_entries,
    }


def _save_learning_data(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
    tmp.replace(path)


def _trim_samples(samples: list[dict[str, Any]], *, config: SelfLearningConfig, now: float, enforce_retention: bool = True) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    cutoff = now - max(0, config.retention_days) * 86400 if enforce_retention and config.retention_days > 0 else None
    max_chars = max(1, config.max_message_chars)
    for sample in samples:
        if not isinstance(sample, dict):
            continue
        text = _normalize_text(sample.get("text"))
        if not text:
            continue
        ts = float(sample.get("ts") or now)
        if cutoff is not None and ts < cutoff:
            continue
        row: dict[str, Any] = {"ts": ts, "text": text[:max_chars]}
        sample_id = _safe_id(sample.get("id"))
        if sample_id:
            row["id"] = sample_id
        if _entry_disabled(sample):
            row["disabled"] = True
        reinforcement = _clamped_reinforcement(sample.get("reinforcement"))
        if reinforcement:
            row["reinforcement"] = reinforcement
        if sample.get("admin_strengthened"):
            row["admin_strengthened"] = True
        weight = _clamped_weight(sample.get("weight"), 0.0)
        if weight > 0:
            row["weight"] = weight
        source = str(sample.get("source") or "").strip().lower()
        if source in {"auto", "self_learning", "admin"}:
            row["source"] = source
        kept.append(row)
    max_samples = max(0, config.max_samples_per_group)
    if max_samples and len(kept) > max_samples:
        kept = kept[-max_samples:]
    return kept


def _trim_manual_entries(entries: list[dict[str, Any]], *, config: SelfLearningConfig) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        text = _normalize_text(entry.get("text"))[:_MAX_MANUAL_ENTRY_CHARS]
        if not text:
            continue
        row: dict[str, Any] = {
            "text": text,
            "entry_type": _manual_entry_type(entry.get("entry_type") or entry.get("type")),
            "source": "admin",
            "ts": _safe_float(entry.get("ts"), time.time()),
            "weight": _clamped_weight(entry.get("weight"), 1.0),
            "reinforcement": _clamped_reinforcement(entry.get("reinforcement")),
        }
        entry_id = _safe_id(entry.get("id"))
        if entry_id:
            row["id"] = entry_id
        if _entry_disabled(entry):
            row["enabled"] = False
            row["disabled"] = True
        else:
            row["enabled"] = True
        kept.append(row)
    return kept


def load_learning_data_for_group(group_id: int, *, group_config_dir: Path, config: SelfLearningConfig) -> dict[str, Any]:
    """Load raw group learning data for admin/storage helpers."""
    path = learning_file_for_group(group_id, group_config_dir=group_config_dir, config=config)
    return _load_learning_data(path, int(group_id))


def save_learning_data_for_group(group_id: int, data: dict[str, Any], *, group_config_dir: Path, config: SelfLearningConfig, now: float | None = None) -> None:
    """Save group learning data after normalizing known storage fields."""
    current = time.time() if now is None else now
    path = learning_file_for_group(group_id, group_config_dir=group_config_dir, config=config)
    normalized = {
        "version": _VERSION,
        "group_id": int(group_id),
        "samples": _trim_samples(list(data.get("samples") or []), config=config, now=current, enforce_retention=False),
        "manual_entries": _trim_manual_entries(list(data.get("manual_entries") or []), config=config),
    }
    _save_learning_data(path, normalized)


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
        if any(sample.get("text") == clean and _entry_disabled(sample) for sample in samples):
            return False
        if not samples or samples[-1].get("text") != clean:
            samples.append({"ts": current, "text": clean, "source": "auto"})
        data["samples"] = _trim_samples(samples, config=config, now=current)
        data["manual_entries"] = _trim_manual_entries(list(data.get("manual_entries") or []), config=config)
        _save_learning_data(path, data)
        return True
    except Exception as exc:  # pragma: no cover - exercised through bridge error swallowing
        if on_error:
            on_error(exc)
        return False


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


def _entry_type_label(entry_type: str) -> str:
    if entry_type == "prompt_guidance":
        return "提示"
    if entry_type == "self_learning":
        return "用语/梗"
    return "记忆"


def _manual_entry_lines(manual_entries: list[dict[str, Any]]) -> list[str]:
    usable: list[tuple[float, int, float, str]] = []
    for entry in manual_entries:
        if not isinstance(entry, dict) or _entry_disabled(entry):
            continue
        text = _normalize_text(entry.get("text"))[:_MAX_MANUAL_ENTRY_CHARS]
        if not text:
            continue
        entry_type = _manual_entry_type(entry.get("entry_type") or entry.get("type"))
        reinforcement = _clamped_reinforcement(entry.get("reinforcement"))
        weight = _clamped_weight(entry.get("weight"), 1.0)
        label = _entry_type_label(entry_type)
        strength_note = f"，强化 {reinforcement}" if reinforcement else ""
        line = f"人工{label}（权重 {weight:g}{strength_note}）：{text}"
        usable.append((weight, reinforcement, _safe_float(entry.get("ts"), 0.0), line))
    usable.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    return [item[3] for item in usable[:8]]


def _strengthened_sample_lines(samples: list[dict[str, Any]]) -> list[str]:
    usable: list[tuple[int, float, str]] = []
    for sample in samples:
        if not isinstance(sample, dict) or _entry_disabled(sample):
            continue
        reinforcement = _clamped_reinforcement(sample.get("reinforcement"))
        if not reinforcement and not sample.get("admin_strengthened"):
            continue
        text = _normalize_text(sample.get("text"))
        if not text:
            continue
        weight = _clamped_weight(sample.get("weight"), 1.0)
        usable.append((reinforcement or 1, _safe_float(sample.get("ts"), 0.0), f"管理员强化样例（强化 {reinforcement or 1}，权重 {weight:g}）：{text}"))
    usable.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [item[2] for item in usable[:5]]


def _format_learning_context(samples: list[dict[str, Any]], *, config: SelfLearningConfig, manual_entries: list[dict[str, Any]] | None = None) -> str:
    enabled_samples = [sample for sample in samples if isinstance(sample, dict) and not _entry_disabled(sample)]
    texts = [_normalize_text(sample.get("text")) for sample in enabled_samples]
    texts = [text for text in texts if text]
    style = _style_summary(texts)
    manual_lines = _manual_entry_lines(manual_entries or [])
    strengthened_lines = _strengthened_sample_lines(enabled_samples)
    if not style and not manual_lines and not strengthened_lines:
        return DEFAULT_LEARNING_CONTEXT

    lines: list[str] = []
    if style:
        lines.extend([
            "低权重理解线索：只用于判断本群消息的大致节奏和互动方式，不是事实来源，也不是必须提到的话题",
            "使用边界：不得覆盖 Esti 的基础人设和原始语气；不得主动模仿、复读或强化群友口癖/梗/高频表达",
            "风格信号：" + "；".join(style),
        ])
    if manual_lines or strengthened_lines:
        lines.append("人工维护记忆：管理员确认的提示或强化样例，可作为比自动学习更高权重的群内低/中权重线索；不得向群友暴露管理来源")
        lines.extend(manual_lines)
        lines.extend(strengthened_lines)

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
        manual_entries = _trim_manual_entries(list(data.get("manual_entries") or []), config=config)
        return _format_learning_context(samples, config=config, manual_entries=manual_entries)
    except Exception as exc:  # pragma: no cover - bridge verifies error swallowing
        if on_error:
            on_error(exc)
        return DEFAULT_LEARNING_CONTEXT
