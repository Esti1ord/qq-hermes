"""Logging and deterministic template selection helpers."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Callable


def pick_template(
    name: str,
    key: str = "",
    *,
    templates: dict[str, list[str]],
    minute_bucket: int | None = None,
) -> str:
    choices = templates.get(name) or [""]
    bucket = int(time.time() // 60) if minute_bucket is None else minute_bucket
    seed = f"{name}|{key}|{bucket}"
    idx = int(hashlib.sha1(seed.encode("utf-8")).hexdigest(), 16) % len(choices)
    return choices[idx]


def json_log_line(obj: Any, *, now_fn: Callable[[str], str] = time.strftime) -> str:
    return json.dumps({"ts": now_fn("%Y-%m-%d %H:%M:%S"), "event": obj}, ensure_ascii=False)


def log(obj: Any, *, log_file: Path, print_fn: Callable[..., None] = print) -> None:
    line = json_log_line(obj)
    print_fn(line, flush=True)
    with log_file.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
