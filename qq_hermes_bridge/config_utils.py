"""Configuration parsing helpers for the QQ/Hermes bridge."""
from __future__ import annotations

import os
import re
from pathlib import Path


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
