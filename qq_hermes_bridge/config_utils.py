"""Configuration parsing helpers for the QQ/Hermes bridge."""
from __future__ import annotations

import os
import re
from pathlib import Path

DEFAULT_PRIMARY_CHAT_MODEL = "deepseekv4flash"
DEFAULT_PRIMARY_CHAT_PROVIDER = "custom"
DEFAULT_FALLBACK_CHAT_MODEL = "deepseekv4flash"
DEFAULT_FALLBACK_CHAT_PROVIDER = "deepseek"
DEFAULT_PRIMARY_OCR_PROVIDER = "custom"
DEFAULT_PRIMARY_OCR_MODEL = "mimo"
DEFAULT_FALLBACK_OCR_PROVIDER = "custom"
DEFAULT_FALLBACK_OCR_MODEL = "gpt-5.4"

PRIMARY_CHAT_PROVIDER_URL_ENV_NAMES = (
    "PRIMARY_CHAT_MODEL_URL",
    "PRIMARY_CHAT_MODEL_BASE_URL",
    "CUSTOM_CHAT_MODEL_URL",
    "CUSTOM_CHAT_MODEL_BASE_URL",
    "CUSTOM_PROVIDER_URL",
    "CUSTOM_PROVIDER_BASE_URL",
    "HERMES_PROVIDER_BASE_URL",
)

PRIMARY_CHAT_API_KEY_ENV_GROUPS = (
    (
        ("PRIMARY_CHAT_MODEL_API_KEY_ENV",),
        ("PRIMARY_CHAT_MODEL_API_KEY", "PRIMARY_CHAT_MODEL_API"),
    ),
    (
        ("CUSTOM_CHAT_MODEL_API_KEY_ENV", "CUSTOM_PROVIDER_API_KEY_ENV", "CUSTOM_API_KEY_ENV"),
        (
            "CUSTOM_CHAT_MODEL_API_KEY",
            "CUSTOM_CHAT_MODEL_API",
            "CUSTOM_PROVIDER_API_KEY",
            "CUSTOM_PROVIDER_API",
            "CUSTOM_API_KEY",
            "CUSTOM_API",
        ),
    ),
    (
        ("HERMES_API_KEY_ENV",),
        ("HERMES_API_KEY",),
    ),
)

FALLBACK_CHAT_PROVIDER_URL_ENV_NAMES = (
    "VICE_CHAT_MODEL_URL",
    "VICE_CHAT_MODEL_BASE_URL",
    "HERMES_FALLBACK_PROVIDER_BASE_URL",
)

FALLBACK_CHAT_API_KEY_ENV_GROUPS = (
    (
        ("VICE_CHAT_MODEL_API_KEY_ENV",),
        ("VICE_CHAT_MODEL_API_KEY", "VICE_CHAT_MODEL_API"),
    ),
    (
        ("HERMES_FALLBACK_API_KEY_ENV",),
        ("HERMES_FALLBACK_API_KEY",),
    ),
)


def parse_bool(value: str, *, true_values: set[str] | None = None) -> bool:
    values = true_values or {"1", "true", "yes"}
    return str(value or "").lower() in values


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        os.environ.setdefault(k, v)


def env_first(*names: str, default: str = "") -> str:
    for name in names:
        if not name:
            continue
        value = os.getenv(name)
        if value is None:
            continue
        clean = str(value).strip()
        if clean:
            return clean
    return str(default or "").strip()


def env_name_if_set(*names: str) -> str:
    for name in names:
        if not name:
            continue
        value = os.getenv(name)
        if value is None:
            continue
        if str(value).strip():
            return name
    return ""


def api_key_env_name_from_groups(groups: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...]) -> str:
    """Resolve API-key env names by alias family without exposing secret values."""
    for explicit_names, raw_names in groups:
        raw_name = env_name_if_set(*raw_names)
        if raw_name:
            return raw_name
        explicit_name = env_first(*explicit_names)
        if explicit_name:
            return explicit_name
    return ""


def env_list(name: str, default: str) -> list[str]:
    raw = os.getenv(name, default)
    return [x.strip() for x in re.split(r"[,，]", raw) if x.strip()]


def parse_group_float_map(raw: str) -> dict[int, float]:
    mapping: dict[int, float] = {}
    for item in re.split(r"[,，]", raw or ""):
        item = item.strip()
        if not item:
            continue
        if "=" in item:
            left, right = item.split("=", 1)
        elif ":" in item:
            left, right = item.split(":", 1)
        else:
            continue
        try:
            mapping[int(left.strip())] = float(right.strip())
        except (TypeError, ValueError):
            continue
    return mapping


def parse_group_str_map(raw: str) -> dict[int, str]:
    mapping: dict[int, str] = {}
    for item in re.split(r"[,，]", raw or ""):
        item = item.strip()
        if not item:
            continue
        if "=" in item:
            left, right = item.split("=", 1)
        elif ":" in item:
            left, right = item.split(":", 1)
        else:
            continue
        value = right.strip()
        if not value:
            continue
        try:
            mapping[int(left.strip())] = value
        except (TypeError, ValueError):
            continue
    return mapping
