# Directory Structure

> How backend code is organized in this project.

---

## Overview

This repository is a single Python/FastAPI service for the QQ Hermes bridge. The
root `bridge.py` is intentionally a compatibility entry point; runtime behavior
belongs in `qq_hermes_bridge/` modules.

---

## Directory Layout

```text
qq-hermes/
├── bridge.py                 # thin compatibility shim; keeps bridge:app imports working
├── qq_hermes_bridge/
│   ├── runtime.py            # FastAPI app, routes, queue workers, runtime globals
│   ├── config.py             # typed flat Config loader scaffold
│   ├── metrics.py            # dependency-free Prometheus text exporter
│   ├── app_helpers.py        # request auth and health response helpers
│   ├── handlers.py           # routing decisions
│   ├── commands.py           # /context, jrrp command helpers
│   ├── runtime_stats.py      # content-safe JSONL stat sanitization helpers
│   └── ...                   # focused business modules
├── tests/                    # pytest tests, many import bridge.py directly by path
└── scripts/                  # operational scripts
```

---

## Module Organization

- Put new reusable business logic in focused `qq_hermes_bridge/*.py` modules.
- Keep root `bridge.py` thin. Do not add runtime logic there.
- Keep FastAPI routes and global runtime state in `qq_hermes_bridge/runtime.py`
  until an app-context refactor replaces the current globals.
- Preserve `bridge:app` as the deployment import target used by `start-bridge.sh`.
- Preserve legacy tests that mutate `bridge` module globals directly.

---

## Scenario: Runtime Split Compatibility Contract

### 1. Scope / Trigger

- Trigger: Any change to root `bridge.py`, `qq_hermes_bridge/runtime.py`, app
  startup, route registration, or global runtime state.
- Why: Tests and deployment import `bridge.py` directly and monkeypatch globals.
  Moving runtime code without preserving that namespace breaks behavior.

### 2. Signatures

- Deployment import target: `bridge:app`
- Compatibility shim signature:
  ```python
  _RUNTIME_PATH = Path(__file__).resolve().parent / "qq_hermes_bridge" / "runtime.py"
  exec(compile(_RUNTIME_PATH.read_text(encoding="utf-8"), str(_RUNTIME_PATH), "exec"), globals())
  ```
- Runtime source path handling:
  ```python
  _RUNTIME_SOURCE_PATH = globals().get("_RUNTIME_PATH")
  BASE_DIR = (
      Path(_RUNTIME_SOURCE_PATH).resolve().parent.parent
      if _RUNTIME_SOURCE_PATH is not None
      else Path(__file__).resolve().parent.parent
  )
  ```

### 3. Contracts

- `bridge.py` must expose the same globals/functions/classes as `runtime.py`
  after import.
- Tests must be able to do `bridge.BRIDGE_INBOUND_TOKEN = "secret"` and have
  route functions see that value.
- `BASE_DIR` must resolve to the repository root both when:
  - importing `bridge.py` via `bridge:app`; and
  - importing `qq_hermes_bridge.runtime` directly.
- Runtime paths derived from `BASE_DIR` (`logs/`, `.env`, `groups/`) must not
  point to the parent directory.

### 4. Validation & Error Matrix

| Condition | Expected behavior |
|---|---|
| Import `bridge:app` via uvicorn/importer | `app` is a FastAPI app from runtime |
| Test mutates `bridge.MAX_REPLY_CHARS` | Runtime functions read the mutated value |
| Shim executes `runtime.py` | `BASE_DIR` remains repository root |
| Direct import of `qq_hermes_bridge.runtime` | `BASE_DIR` remains repository root |
| Runtime file missing | Import fails loudly; do not silently create a dummy app |

### 5. Good/Base/Bad Cases

- Good: add route logic in `runtime.py`; root `bridge.py` stays unchanged.
- Base: add a helper in `qq_hermes_bridge/<topic>.py` and call it from
  `runtime.py`.
- Bad: add business logic to root `bridge.py` or replace `exec(..., globals())`
  with a normal import that breaks monkeypatchable globals.

### 6. Tests Required

- `./venv/bin/python -m py_compile bridge.py qq_hermes_bridge/*.py`
- A bridge import/route test such as `tests/test_inbound_auth.py` must pass.
- Any change to `BASE_DIR` logic must assert paths remain under the repo root.
- Full regression for runtime refactors:
  ```bash
  GROUP_IDS=975805598,781423661 ./venv/bin/python -m pytest tests -q
  ```

### 7. Wrong vs Correct

#### Wrong

```python
# bridge.py
from qq_hermes_bridge.runtime import app
```

This exposes `app`, but functions imported from `runtime.py` still use the
`runtime.py` module globals. Tests that mutate `bridge.BRIDGE_INBOUND_TOKEN` no
longer affect `onebot_event()`.

#### Correct

```python
_RUNTIME_PATH = Path(__file__).resolve().parent / "qq_hermes_bridge" / "runtime.py"
exec(compile(_RUNTIME_PATH.read_text(encoding="utf-8"), str(_RUNTIME_PATH), "exec"), globals())
```

This keeps the historical `bridge` module namespace contract intact while the
source file lives under `qq_hermes_bridge/runtime.py`.

---

## Naming Conventions

- Module files use lowercase snake_case.
- Runtime env globals in `runtime.py` remain uppercase for compatibility.
- `Config` dataclass fields in `config.py` use lowercase snake_case matching the
  old uppercase names one-to-one.

---

## Examples

- `qq_hermes_bridge/runtime.py` - runtime orchestration and FastAPI routes.
- `qq_hermes_bridge/metrics.py` - standalone helper module with no external
  dependency.
- `qq_hermes_bridge/runtime_stats.py` - content-safe stat sanitization helpers.
