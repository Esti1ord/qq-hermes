"""Admin-only memory/self-learning management helpers.

The helpers in this module adapt the existing per-group self_learning JSON store
for manual curation. They validate mutation inputs, keep serialized admin data
short and content-safe, and avoid exposing unrelated runtime chat state.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import math
import re
import time
from pathlib import Path
from typing import Any

from . import admin_view, self_learning

ENTRY_TYPES = {"prompt_guidance", "memory", "self_learning"}
ENTRY_TYPE_ALIASES = {
    "guidance": "prompt_guidance",
    "prompt": "prompt_guidance",
    "prompt-guidance": "prompt_guidance",
    "prompt_guidance": "prompt_guidance",
    "memory": "memory",
    "note": "memory",
    "fact": "memory",
    "meme": "self_learning",
    "style": "self_learning",
    "self-learning": "self_learning",
    "selflearning": "self_learning",
    "self_learning": "self_learning",
}
DEFAULT_TEXT_MAX_CHARS = 600
PREVIEW_MAX_CHARS = 90
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9:_-]{1,96}$")
_CQ_CODE_RE = re.compile(r"\[CQ:[^\]]+\]", re.IGNORECASE)
_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_RAW_IDENTIFIER_RE = re.compile(r"\b\d{6,}\b")
_SENSITIVE_TEXT_MARKERS = (
    "authorization",
    "bearer ",
    "cookie",
    "token",
    "secret",
    "passwd",
    "password",
    "api key",
    "api_key",
    "apikey",
    "密钥",
    "令牌",
    "密码",
    "cookie",
)


class AdminMemoryError(ValueError):
    """Input or storage error safe to show as a short admin API detail."""


class AdminMemoryNotFound(KeyError):
    """Raised when a selected memory entry no longer exists."""


def group_id_or_default(group_id: Any, *, target_group_id: int) -> int:
    value = target_group_id if group_id in (None, "") else group_id
    try:
        gid = int(value)
    except (TypeError, ValueError) as exc:
        raise AdminMemoryError("invalid group_id") from exc
    if gid <= 0:
        raise AdminMemoryError("invalid group_id")
    return gid


def normalize_entry_type(value: Any) -> str:
    text = str(value or "").strip().lower()
    entry_type = ENTRY_TYPE_ALIASES.get(text, text)
    if entry_type not in ENTRY_TYPES:
        raise AdminMemoryError("invalid entry_type")
    return entry_type


def normalize_mode(value: Any) -> str:
    mode = str(value or "disable").strip().lower()
    if mode not in {"disable", "delete"}:
        raise AdminMemoryError("invalid mode")
    return mode


def normalize_strength_amount(value: Any) -> int:
    try:
        amount = int(value if value not in (None, "") else 1)
    except (TypeError, ValueError) as exc:
        raise AdminMemoryError("invalid amount") from exc
    if amount < 1 or amount > 20:
        raise AdminMemoryError("invalid amount")
    return amount


def normalize_weight(value: Any) -> float:
    try:
        weight = float(value if value not in (None, "") else 1.0)
    except (TypeError, ValueError) as exc:
        raise AdminMemoryError("invalid weight") from exc
    if not math.isfinite(weight) or weight < 0.1 or weight > 20.0:
        raise AdminMemoryError("invalid weight")
    return round(weight, 3)


def _compact_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def validate_manual_text(value: Any, *, max_chars: int = DEFAULT_TEXT_MAX_CHARS) -> str:
    text = _compact_text(value)
    if len(text) < 2:
        raise AdminMemoryError("text too short")
    if len(text) > max_chars:
        raise AdminMemoryError("text too long")
    lowered = text.lower()
    if _CQ_CODE_RE.search(text):
        raise AdminMemoryError("text contains CQ code")
    if _URL_RE.search(text):
        raise AdminMemoryError("text contains URL")
    if _RAW_IDENTIFIER_RE.search(text):
        raise AdminMemoryError("text contains raw identifier")
    if any(marker in lowered for marker in _SENSITIVE_TEXT_MARKERS):
        raise AdminMemoryError("text contains sensitive marker")
    if admin_view.safe_display_value(text, max_chars=max_chars + 1) == admin_view.REDACTED:
        raise AdminMemoryError("text contains sensitive value")
    return text


def _safe_id(value: Any) -> str:
    text = str(value or "").strip()
    if _SAFE_ID_RE.fullmatch(text):
        return text
    return ""


def _entry_id(prefix: str, index: int, item: dict[str, Any]) -> str:
    stored = _safe_id(item.get("id"))
    if stored and stored.startswith(f"{prefix}:"):
        return stored
    raw = "\0".join([
        prefix,
        str(index),
        str(item.get("ts") or ""),
        str(item.get("text") or ""),
    ])
    digest = hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()[:16]
    return f"{prefix}:{digest}"


def _new_manual_id(group_id: int, text: str, now: float) -> str:
    raw = f"manual\0{group_id}\0{now:.6f}\0{text}"
    digest = hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()[:18]
    return f"manual:{digest}"


def _is_disabled(item: dict[str, Any]) -> bool:
    status = str(item.get("status") or "").strip().lower()
    return bool(item.get("disabled") or item.get("enabled") is False or status == "disabled")


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


def _iso_timestamp(value: Any) -> str:
    try:
        ts = float(value)
    except (TypeError, ValueError):
        return ""
    if ts <= 0:
        return ""
    try:
        return datetime.fromtimestamp(ts).isoformat(timespec="seconds")
    except (OverflowError, OSError, ValueError):
        return ""


def safe_entry_preview(value: Any, *, max_chars: int = PREVIEW_MAX_CHARS) -> dict[str, Any]:
    text = _compact_text(_URL_RE.sub("", _CQ_CODE_RE.sub("", str(value or ""))))
    safe = admin_view.safe_display_value(text, max_chars=max_chars)
    if text and _RAW_IDENTIFIER_RE.search(text):
        safe = admin_view.REDACTED
    redacted = bool(text and safe == admin_view.REDACTED)
    return {
        "preview": safe if safe else "（空）",
        "preview_chars": len(safe or ""),
        "raw_char_count": len(str(value or "")),
        "redacted": redacted,
    }


def _serialize_entry(*, group_id: int, collection: str, index: int, item: dict[str, Any]) -> dict[str, Any]:
    prefix = "manual" if collection == "manual_entries" else "sample"
    entry_id = _entry_id(prefix, index, item)
    source = "manual" if collection == "manual_entries" else "self_learning"
    if collection == "manual_entries":
        entry_type = normalize_entry_type(item.get("entry_type") or item.get("type") or "memory")
    else:
        entry_type = "self_learning"
    status = "disabled" if _is_disabled(item) else "active"
    reinforcement = max(0, _safe_int(item.get("reinforcement"), 0))
    weight = max(0.0, _safe_float(item.get("weight"), 1.0 if collection == "manual_entries" else 0.0))
    preview = safe_entry_preview(item.get("text"))
    return {
        "id": entry_id,
        "group_id": group_id,
        "type": entry_type,
        "source": source,
        "storage": collection,
        "status": status,
        "preview": preview["preview"],
        "preview_chars": preview["preview_chars"],
        "char_count": preview["raw_char_count"],
        "redacted": preview["redacted"],
        "created_at": _iso_timestamp(item.get("ts")),
        "weight": round(weight, 3),
        "reinforcement": reinforcement,
        "counters": {
            "weight": round(weight, 3),
            "reinforcement": reinforcement,
        },
        "operations": {
            "disable": status != "disabled",
            "delete": True,
            "strengthen": status != "disabled",
        },
    }


def _load(group_id: int, *, group_config_dir: Path, config: self_learning.SelfLearningConfig) -> dict[str, Any]:
    return self_learning.load_learning_data_for_group(group_id, group_config_dir=group_config_dir, config=config)


def _save(group_id: int, data: dict[str, Any], *, group_config_dir: Path, config: self_learning.SelfLearningConfig, now: float | None = None) -> None:
    self_learning.save_learning_data_for_group(group_id, data, group_config_dir=group_config_dir, config=config, now=now)


def _all_entries(group_id: int, data: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for collection in ("manual_entries", "samples"):
        items = data.get(collection) or []
        if not isinstance(items, list):
            continue
        for index, item in enumerate(items):
            if isinstance(item, dict):
                rows.append(_serialize_entry(group_id=group_id, collection=collection, index=index, item=item))
    rows.sort(key=lambda item: (item.get("status") != "active", item.get("source") != "manual", item.get("created_at") or ""))
    return rows


def summarize_entries(entries: list[dict[str, Any]]) -> dict[str, int]:
    active = sum(1 for item in entries if item.get("status") == "active")
    disabled = sum(1 for item in entries if item.get("status") == "disabled")
    manual = sum(1 for item in entries if item.get("source") == "manual")
    learned = sum(1 for item in entries if item.get("source") == "self_learning")
    strengthened = sum(1 for item in entries if _safe_int(item.get("reinforcement"), 0) > 0)
    return {
        "total": len(entries),
        "active": active,
        "disabled": disabled,
        "manual": manual,
        "self_learning": learned,
        "strengthened": strengthened,
    }


def list_memory_entries(group_id: int, *, group_config_dir: Path, config: self_learning.SelfLearningConfig) -> dict[str, Any]:
    data = _load(group_id, group_config_dir=group_config_dir, config=config)
    entries = _all_entries(group_id, data)
    return {
        "ok": True,
        "group_id": group_id,
        "entries": entries,
        "summary": summarize_entries(entries),
        "limits": {
            "max_text_chars": DEFAULT_TEXT_MAX_CHARS,
            "preview_max_chars": PREVIEW_MAX_CHARS,
            "supported_entry_types": sorted(ENTRY_TYPES),
            "supported_delete_modes": ["disable", "delete"],
        },
        "safety": {
            "previews_are_short": True,
            "raw_user_ids_hidden": True,
            "provider_urls_hidden": True,
            "tokens_hidden": True,
            "unrelated_chat_hidden": True,
        },
    }


def memory_summary(group_id: int, *, group_config_dir: Path, config: self_learning.SelfLearningConfig) -> dict[str, Any]:
    state = list_memory_entries(group_id, group_config_dir=group_config_dir, config=config)
    return {
        "group_id": group_id,
        **state["summary"],
        "content_hidden": True,
        "previews_hidden_in_state": True,
    }


def _find_entry(data: dict[str, Any], entry_id: str) -> tuple[str, int, dict[str, Any]]:
    wanted = _safe_id(entry_id)
    if not wanted:
        raise AdminMemoryError("invalid entry_id")
    for collection in ("manual_entries", "samples"):
        items = data.get(collection) or []
        if not isinstance(items, list):
            continue
        prefix = "manual" if collection == "manual_entries" else "sample"
        for index, item in enumerate(items):
            if isinstance(item, dict) and _entry_id(prefix, index, item) == wanted:
                return collection, index, item
    raise AdminMemoryNotFound("entry not found")


def add_manual_entry(
    group_id: int,
    *,
    entry_type: str,
    text: str,
    weight: float,
    group_config_dir: Path,
    config: self_learning.SelfLearningConfig,
    now: float | None = None,
) -> dict[str, Any]:
    clean_text = validate_manual_text(text)
    normalized_type = normalize_entry_type(entry_type)
    current = time.time() if now is None else now
    data = _load(group_id, group_config_dir=group_config_dir, config=config)
    entries = data.get("manual_entries")
    if not isinstance(entries, list):
        entries = []
    entry = {
        "id": _new_manual_id(group_id, clean_text, current),
        "ts": current,
        "text": clean_text,
        "entry_type": normalized_type,
        "source": "admin",
        "enabled": True,
        "weight": normalize_weight(weight),
        "reinforcement": 0,
    }
    entries.append(entry)
    data["manual_entries"] = entries
    _save(group_id, data, group_config_dir=group_config_dir, config=config, now=current)
    saved = _load(group_id, group_config_dir=group_config_dir, config=config)
    collection, index, item = _find_entry(saved, entry["id"])
    serialized = _serialize_entry(group_id=group_id, collection=collection, index=index, item=item)
    return {"ok": True, "action": "added", "entry": serialized, "summary": summarize_entries(_all_entries(group_id, saved))}


def delete_or_disable_entry(
    group_id: int,
    *,
    entry_id: str,
    mode: str,
    group_config_dir: Path,
    config: self_learning.SelfLearningConfig,
) -> dict[str, Any]:
    normalized_mode = normalize_mode(mode)
    data = _load(group_id, group_config_dir=group_config_dir, config=config)
    collection, index, item = _find_entry(data, entry_id)
    before = _serialize_entry(group_id=group_id, collection=collection, index=index, item=item)
    items = data.get(collection)
    if not isinstance(items, list):
        raise AdminMemoryNotFound("entry not found")
    if normalized_mode == "delete":
        items.pop(index)
        data[collection] = items
        _save(group_id, data, group_config_dir=group_config_dir, config=config)
        saved = _load(group_id, group_config_dir=group_config_dir, config=config)
        return {"ok": True, "action": "deleted", "entry": before, "summary": summarize_entries(_all_entries(group_id, saved))}
    if not _safe_id(item.get("id")):
        item["id"] = before["id"]
    item["enabled"] = False
    item["disabled"] = True
    item["status"] = "disabled"
    items[index] = item
    data[collection] = items
    _save(group_id, data, group_config_dir=group_config_dir, config=config)
    saved = _load(group_id, group_config_dir=group_config_dir, config=config)
    collection2, index2, item2 = _find_entry(saved, entry_id)
    return {
        "ok": True,
        "action": "disabled",
        "entry": _serialize_entry(group_id=group_id, collection=collection2, index=index2, item=item2),
        "summary": summarize_entries(_all_entries(group_id, saved)),
    }


def strengthen_entry(
    group_id: int,
    *,
    entry_id: str,
    amount: int,
    group_config_dir: Path,
    config: self_learning.SelfLearningConfig,
) -> dict[str, Any]:
    normalized_amount = normalize_strength_amount(amount)
    data = _load(group_id, group_config_dir=group_config_dir, config=config)
    collection, index, item = _find_entry(data, entry_id)
    if _is_disabled(item):
        raise AdminMemoryError("entry disabled")
    before = _serialize_entry(group_id=group_id, collection=collection, index=index, item=item)
    if not _safe_id(item.get("id")):
        item["id"] = before["id"]
    preview = safe_entry_preview(item.get("text"))
    if preview.get("redacted"):
        raise AdminMemoryError("entry contains sensitive value")
    current_reinforcement = max(0, _safe_int(item.get("reinforcement"), 0))
    current_weight = max(0.0, _safe_float(item.get("weight"), 1.0 if collection == "manual_entries" else 0.0))
    item["reinforcement"] = min(999, current_reinforcement + normalized_amount)
    item["weight"] = round(min(100.0, max(1.0, current_weight) + normalized_amount), 3)
    if collection == "samples":
        item["admin_strengthened"] = True
    items = data.get(collection)
    if not isinstance(items, list):
        raise AdminMemoryNotFound("entry not found")
    items[index] = item
    data[collection] = items
    _save(group_id, data, group_config_dir=group_config_dir, config=config)
    saved = _load(group_id, group_config_dir=group_config_dir, config=config)
    collection2, index2, item2 = _find_entry(saved, entry_id)
    return {
        "ok": True,
        "action": "strengthened",
        "entry": _serialize_entry(group_id=group_id, collection=collection2, index=index2, item=item2),
        "summary": summarize_entries(_all_entries(group_id, saved)),
    }
