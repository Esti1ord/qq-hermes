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

---

## What to Log

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
