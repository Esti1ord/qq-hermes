#!/usr/bin/env python3
"""Compatibility entry point for QQ Hermes Bridge."""
from __future__ import annotations

from pathlib import Path

_RUNTIME_PATH = Path(__file__).resolve().parent / "qq_hermes_bridge" / "runtime.py"
# Execute the runtime in this module namespace so legacy tests and deployment
# can continue importing bridge:app and mutating bridge globals directly.
exec(compile(_RUNTIME_PATH.read_text(encoding="utf-8"), str(_RUNTIME_PATH), "exec"), globals())
