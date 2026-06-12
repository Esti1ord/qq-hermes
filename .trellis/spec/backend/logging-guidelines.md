# Logging Guidelines

> How logging and operational metrics are done in this project.

---

## Overview

Runtime observability has two content-safe outputs:

1. JSONL runtime stats in `logs/runtime_stats.jsonl` via
   `qq_hermes_bridge/runtime_stats.py` sanitization helpers.
2. Prometheus-compatible text from `qq_hermes_bridge/metrics.py` exposed at
   `GET /metrics`.

Both outputs must avoid raw chat content, prompts, model outputs, OCR text,
URLs, tokens, cookies, user identifiers, and full provider responses.

---

## Structured Logging

- Use `logging_utils.log()` for JSONL records.
- Route runtime stats through `runtime_stat()` / `emit_perf_stat()` in
  `qq_hermes_bridge/runtime.py` so `runtime_stats.sanitize_stat_fields()` can
  filter unsafe fields.
- Content analysis logs are separate and sensitive; do not mix them with runtime
  stats or Prometheus metrics.

---

## Scenario: Prometheus `/metrics` Contract

### 1. Scope / Trigger

- Trigger: Adding/changing `/metrics`, `qq_hermes_bridge/metrics.py`, runtime
  stat names, queue/context gauges, or observability env vars.
- Why: Metrics are scraped by operations tools and must remain content-safe and
  low-cardinality.

### 2. Signatures

- FastAPI endpoint:
  ```python
  @app.get("/metrics", response_class=PlainTextResponse)
  async def prometheus_metrics() -> PlainTextResponse: ...
  ```
- Exporter module API:
  ```python
  metrics.configure(enabled: bool, include_group_id_label: bool) -> None
  metrics.generate_latest() -> str
  metrics.observe_runtime_stat(stat: str, fields: dict[str, Any]) -> None
  metrics.observe_runtime_counter(name: str, amount: int = 1) -> None
  metrics.record_queue_size(group_id: Any, kind: str, size: int | float) -> None
  metrics.set_context_messages(group_id: Any, count: int | float) -> None
  ```
- Content type:
  ```text
  text/plain; version=0.0.4; charset=utf-8
  ```

### 3. Contracts

Environment keys:

| Key | Default | Contract |
|---|---:|---|
| `PROMETHEUS_ENABLED` | `true` | Enables `GET /metrics`; disabled endpoint returns HTTP 404 |
| `PROMETHEUS_INCLUDE_GROUP_ID_LABEL` | `false` | When false, omit `group_id` labels from all metrics |

Metric contracts:

- Metric names are prefixed with `qq_hermes_`.
- Labels are allowlisted and low-cardinality only:
  `route`, `result`, `type`, `status`, `component`, `error_type`, optionally
  `group_id`.
- Unsafe label names/values are dropped or normalized to `unknown`.
- Metrics observation must be additive to JSONL stats; a metrics bug must not
  prevent JSONL logging or message processing.
- Do not add `prometheus-client` unless deployment docs and dependency handling
  are updated; the current exporter is dependency-free by design.

### 4. Validation & Error Matrix

| Condition | Expected behavior |
|---|---|
| `PROMETHEUS_ENABLED=false` | `/metrics` raises HTTP 404 |
| `PROMETHEUS_INCLUDE_GROUP_ID_LABEL=false` | Output contains no `group_id` label |
| `PROMETHEUS_INCLUDE_GROUP_ID_LABEL=true` | Safe numeric group IDs may appear as labels |
| Unsafe label field like `token` or `url` | Field is not exported |
| Unsafe label value like URL/token text | Value becomes `unknown` or is omitted |
| Metrics observation raises internally | Runtime logs a safe `metrics_*_error`; main path continues |

### 5. Good/Base/Bad Cases

- Good: map existing `runtime_stat("route_decision", ...)` to
  `qq_hermes_messages_total{route,result}`.
- Base: add a new low-cardinality `status` label for a new component.
- Bad: export message text, prompt text, query strings, user hashes, raw errors,
  image URLs, or unbounded IDs as labels.

### 6. Tests Required

- `tests/test_metrics_module.py` must assert:
  - Prometheus text includes expected metric names and types.
  - `group_id` is omitted by default.
  - `group_id` appears only when explicitly enabled.
  - unsafe labels/values are not emitted.
  - `/metrics` returns plaintext when enabled and 404 when disabled.
- Runtime validation:
  ```bash
  ./venv/bin/python -m py_compile bridge.py qq_hermes_bridge/*.py scripts/sync_people_from_qqdocs.py
  GROUP_IDS=975805598,781423661 ./venv/bin/python -m pytest tests -q
  ```

### 7. Wrong vs Correct

#### Wrong

```python
# Do not export high-cardinality or sensitive labels.
metrics.counter("messages_total", "...", user_hash=user_hash, query=user_query)
```

#### Correct

```python
# Export only route/status style labels; omit group_id unless explicitly enabled.
metrics.observe_runtime_stat("route_decision", {"route": "direct", "queued": True})
```


## Scenario: Local admin `/admin` contract

### 1. Scope / Trigger

- Trigger: Adding/changing local admin pages, runtime-state endpoints, model-routing
  dashboards, queue/context inspectors, or prompt/context composition views.
- Why: The bridge may bind `0.0.0.0`; admin data is operationally useful but can
  reveal sensitive chat, provider, or prompt information if exposed raw.

### 2. Signatures

- FastAPI endpoints live in `qq_hermes_bridge/runtime.py`:
  ```python
  @app.get("/admin", response_class=HTMLResponse)
  async def admin_page(req: Request) -> HTMLResponse: ...

  @app.get("/admin/state")
  async def admin_state(req: Request, group_id: int | None = None) -> dict[str, Any]: ...
  ```
- Reusable HTML/sanitization helpers live in a focused module such as
  `qq_hermes_bridge/admin_view.py`:
  ```python
  def safe_model_provider_details(model: Any, provider: Any) -> dict[str, Any]: ...
  def summarize_context(messages: Iterable[Mapping[str, Any]], summaries: Iterable[Any]) -> dict[str, Any]: ...
  def build_context_composition_overview(...) -> dict[str, Any]: ...
  def build_admin_html() -> str: ...
  ```
- Access guard:
  ```python
  def require_admin_access(req: Request) -> None: ...
  ```

### 3. Contracts

Admin access contract:

| Request source | Expected behavior |
|---|---|
| Loopback client (`127.0.0.0/8`, `::1`, `localhost`) | Allow without token |
| Non-loopback client with valid `BRIDGE_INBOUND_TOKEN` via `Authorization: Bearer ...` or `X-Bridge-Token` | Allow |
| Non-loopback client without valid token | HTTP 403 |

`GET /admin` contract:

- Returns dependency-free HTML/CSS/JS unless a frontend stack is intentionally
  introduced and documented.
- Fetches JSON from `/admin/state`; it must not inline runtime secrets or raw
  prompt/context content.

`GET /admin/state` contract:

- May include content-safe fields such as:
  - runtime status, PID, start time, uptime, enabled flags, queue counts, worker
    counts, inflight counts, and integer counters;
  - primary/selected/fallback model/provider display labels after redaction;
  - OCR enabled/configured booleans and safe model/provider labels;
  - group counts, queue sizes, context message counts, summary counts, stored text
    lengths, and prompt-section metadata;
  - context composition section keys/titles/source/priority/budgets and static
    summaries.
- Must not include raw chat text, prompt bodies, model outputs, OCR text, provider
  URLs, API key env names/values, tokens/cookies, image URLs, full provider
  responses, local secret config paths, raw user identifiers, or nicknames.

### 4. Validation & Error Matrix

| Condition | Expected behavior |
|---|---|
| `/admin` requested from loopback | HTML response |
| `/admin/state` requested from loopback | JSON response with `ok: true` |
| `/admin/state` requested remotely without token | HTTP 403 |
| `/admin/state` requested remotely with valid bridge token | JSON response with `ok: true` |
| Model/provider label looks like URL, token, API key, or local path | Return `[redacted]` and redaction flag |
| Recent context contains chat text, user ids, nicknames, image URLs, or OCR text | Return counts/lengths only; raw values absent from serialized JSON |
| Prompt composition is requested | Return section metadata/static summaries only; no section body text |

### 5. Good/Base/Bad Cases

- Good: `/admin/state` reports `recent_message_count`, `summary_total_chars`,
  `group_model_override_count`, and section `budget_chars` without exposing the
  underlying messages, summaries, or prompts.
- Base: A local browser on `127.0.0.1` opens `/admin` and polls `/admin/state`.
- Bad: Publishing `/admin/state` on `0.0.0.0` without loopback/token protection.
- Bad: Showing provider base URLs, API env var names, user ids, image URLs, full
  prompt sections, or chat snippets in the admin page for debugging convenience.

### 6. Tests Required

- `tests/test_admin_routes.py` must assert:
  - `/admin` and `/admin/state` routes are registered;
  - `/admin` returns local dependency-free HTML;
  - `/admin/state` contains runtime/model/context-composition top-level shapes;
  - non-loopback requests require a valid bridge token;
  - serialized JSON excludes raw chat text, summaries, OCR text, provider URLs,
    API env names, tokens, nicknames, raw user ids, and image URLs;
  - prompt composition sections expose metadata only, not `body` or raw `text`.
- Runtime validation:
  ```bash
  ./venv/bin/python -m py_compile bridge.py qq_hermes_bridge/*.py
  ./venv/bin/python -m pytest tests/test_admin_routes.py tests/test_inbound_auth.py tests/test_metrics_module.py -q
  ```

### 7. Wrong vs Correct

#### Wrong

```python
@app.get("/admin/state")
async def admin_state() -> dict[str, Any]:
    return {
        "provider_url": HERMES_PROVIDER_BASE_URL,
        "api_key_env": HERMES_API_KEY_ENV,
        "recent_messages": list(_recent_messages_by_group[TARGET_GROUP_ID]),
        "prompt": build_prompt(...),
    }
```

#### Correct

```python
@app.get("/admin/state")
async def admin_state(req: Request, group_id: int | None = None) -> dict[str, Any]:
    require_admin_access(req)
    return {
        "runtime": {"status": "running", "uptime_seconds": uptime_seconds},
        "model_routing": {"primary": admin_view.safe_model_provider_details(HERMES_MODEL, HERMES_PROVIDER)},
        "context_composition": admin_view.build_context_composition_overview(...),
        "safety": {"prompt_text_hidden": True, "provider_urls_hidden": True},
    }
```

---

- Counts, durations, statuses, route decisions, queue sizes, and component names.
- Hashes only where explicitly designed for JSONL runtime stats; never expose
  hashes through Prometheus labels.
- Safe exception type names, not raw exception messages when they may contain
  provider responses or URLs.

---

## What NOT to Log

Never log or export:

- Chat message text, prompts, model replies, search queries, OCR text.
- QQ passwords, QR codes, cookies, tokens, API keys, provider base URLs.
- Image URLs, full HTTP responses, stdout/stderr dumps in metrics.
- Unbounded IDs as Prometheus labels.
