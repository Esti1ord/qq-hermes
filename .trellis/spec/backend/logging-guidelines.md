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
  - OCR enabled/configured booleans, safe model/provider labels, and safe OCR
    status counts such as active inflight tasks, context task count, and cache
    entry count;
  - group counts, queue sizes, context message counts, summary counts, stored text
    lengths, and prompt-section metadata;
  - `prompt_composition` as the canonical prompt-composition payload, with
    `context_composition` retained only as a compatibility alias while older UI or
    tests still expect it;
  - prompt composition section keys/titles/source/priority/budgets and static
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
| Prompt composition is requested | Return concise `prompt_composition` section metadata/static summaries only; no section body text |
| Admin page shows metric trends | Compute short-lived client-side deltas from the current and previous safe `/admin/state` payload; do not persist or add server-side history unless separately specified |
| Admin page shows JSON details | Render only the content-safe `/admin/state` payload; do not fetch or inline raw runtime stores |

### 5. Good/Base/Bad Cases

- Good: `/admin/state` reports `recent_message_count`, `summary_total_chars`,
  `group_model_override_count`, and prompt section `budget_chars` without exposing
  the underlying messages, summaries, or prompts.
- Good: the admin page labels the section as "prompt composition" / `输入给机器人的提示词组成概览`, uses compact tables or chips, and keeps longer debugging detail in the already-safe JSON panel.
- Base: A local browser on `127.0.0.1` opens `/admin`, selects a group, and polls `/admin/state?group_id=<id>`.
- Bad: Publishing `/admin/state` on `0.0.0.0` without loopback/token protection.
- Bad: Showing provider base URLs, API env var names, user ids, image URLs, full
  prompt sections, or chat snippets in the admin page for debugging convenience.

### 6. Tests Required

- `tests/test_admin_routes.py` must assert:
  - `/admin` and `/admin/state` routes are registered;
  - `/admin` returns local dependency-free HTML;
  - `/admin/state` contains runtime/model/`prompt_composition` top-level shapes and
    may keep `context_composition` as a compatibility alias;
  - non-loopback requests require a valid bridge token;
  - serialized JSON excludes raw chat text, summaries, OCR text, provider URLs,
    API env names, tokens, nicknames, raw user ids, and image URLs;
  - prompt composition sections expose concise metadata only, not `body` or raw `text`;
  - the HTML contains realtime connection status, group selector, metric trend cards,
    and a read-only JSON panel backed only by `/admin/state`.
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


## Scenario: Admin memory/self-learning management contract

### 1. Scope / Trigger

- Trigger: Adding/changing admin memory curation endpoints, `admin_memory.py`,
  self-learning storage fields, or the `/admin` memory management UI.
- Why: Admin memory curation intentionally edits prompt-affecting runtime data. The
  surface must remain local/token-protected, must not leak unrelated chat or raw
  identifiers, and must not make sensitive learned content more likely to enter
  prompts.

### 2. Signatures

- FastAPI endpoints live in `qq_hermes_bridge/runtime.py` and must call
  `require_admin_access(req)` before reading or mutating storage:
  ```python
  @app.get("/admin/memory")
  async def admin_memory_list(req: Request, group_id: int | None = None) -> dict[str, Any]: ...

  class AdminMemoryAddRequest(BaseModel):
      group_id: int | None = None
      entry_type: str = "memory"
      text: str
      weight: float = 1.0

  @app.post("/admin/memory/add")
  async def admin_memory_add(req: Request, payload: AdminMemoryAddRequest) -> dict[str, Any]: ...

  class AdminMemoryDeleteRequest(BaseModel):
      group_id: int | None = None
      entry_id: str
      mode: str = "disable"

  @app.post("/admin/memory/delete")
  async def admin_memory_delete(req: Request, payload: AdminMemoryDeleteRequest) -> dict[str, Any]: ...

  class AdminMemoryStrengthenRequest(BaseModel):
      group_id: int | None = None
      entry_id: str
      amount: int = 1

  @app.post("/admin/memory/strengthen")
  async def admin_memory_strengthen(req: Request, payload: AdminMemoryStrengthenRequest) -> dict[str, Any]: ...
  ```
- Admin helper API lives in `qq_hermes_bridge/admin_memory.py`:
  ```python
  def list_memory_entries(group_id: int, *, group_config_dir: Path, config: self_learning.SelfLearningConfig) -> dict[str, Any]: ...
  def add_manual_entry(group_id: int, *, entry_type: str, text: str, weight: float, group_config_dir: Path, config: self_learning.SelfLearningConfig, now: float | None = None) -> dict[str, Any]: ...
  def delete_or_disable_entry(group_id: int, *, entry_id: str, mode: str, group_config_dir: Path, config: self_learning.SelfLearningConfig) -> dict[str, Any]: ...
  def strengthen_entry(group_id: int, *, entry_id: str, amount: int, group_config_dir: Path, config: self_learning.SelfLearningConfig) -> dict[str, Any]: ...
  ```
- Self-learning storage helpers in `qq_hermes_bridge/self_learning.py` expose the
  existing per-group JSON store to admin code:
  ```python
  def load_learning_data_for_group(group_id: int, *, group_config_dir: Path, config: SelfLearningConfig) -> dict[str, Any]: ...
  def save_learning_data_for_group(group_id: int, data: dict[str, Any], *, group_config_dir: Path, config: SelfLearningConfig, now: float | None = None) -> None: ...
  ```

### 3. Contracts

Admin access and UI contracts:

- `/admin/memory*` endpoints use the same loopback-or-valid-`BRIDGE_INBOUND_TOKEN`
  access contract as `/admin` and `/admin/state`.
- `/admin` may include a dependency-free memory management panel that fetches
  `/admin/memory?group_id=<id>` and posts JSON to the mutation endpoints.
- `/admin/state` may include only a `memory_management` summary such as total,
  active, disabled, manual, self-learning, and strengthened counts. It must not
  include memory previews or raw stored text.

Storage contract:

- The per-group `self_learning.json` shape remains backward-compatible:
  ```json
  {
    "version": 1,
    "group_id": 975805598,
    "samples": [{"ts": 1.0, "text": "auto learned text", "source": "auto"}],
    "manual_entries": [{"id": "manual:...", "ts": 1.0, "text": "curated hint", "entry_type": "memory", "source": "admin", "enabled": true, "weight": 1.0, "reinforcement": 0}]
  }
  ```
- `samples` are auto-collected self-learning entries; `manual_entries` are
  operator-curated entries. Missing `manual_entries` must load as `[]`.
- Soft-disabled entries carry `enabled: false`, `disabled: true`, or
  `status: "disabled"`; prompt injection and recollection of the exact disabled
  sample text must skip them.
- Strengthened auto samples carry `admin_strengthened: true`, `reinforcement`, and
  `weight`; they may be injected as bounded admin-curated hints only when not
  disabled.
- Legacy entries without stored IDs may receive their generated admin ID before a
  mutation so lookup remains stable after normalization.

Response contract:

- `GET /admin/memory` returns `ok`, `group_id`, `entries`, `summary`, `limits`, and
  `safety`.
- Each entry includes only safe metadata: generated/stored `id`, `group_id`,
  `type`, `source`, `storage`, `status`, short `preview`, char counts, timestamp,
  numeric `weight`/`reinforcement`, and supported `operations`.
- Previews are short and sanitized; URL/CQ-code content is stripped or redacted,
  raw numeric identifiers are redacted/rejected, and unrelated runtime chat buffers
  are never read for this endpoint.
- Mutation success returns `ok: true`, `action`, the affected serialized `entry`,
  and updated `summary`.

### 4. Validation & Error Matrix

| Condition | Expected behavior |
|---|---|
| Non-loopback request to any `/admin/memory*` endpoint without valid token | HTTP 403 |
| `group_id` missing | Use `TARGET_GROUP_ID` |
| `group_id` is non-integer or `<= 0` | HTTP 400 `invalid group_id` |
| `entry_type` outside `prompt_guidance`, `memory`, `self_learning` and aliases | HTTP 400 `invalid entry_type` |
| Manual text shorter than 2 chars or longer than 600 chars | HTTP 400 |
| Manual text contains CQ code, URL, raw numeric identifier, token/API-key/password/cookie marker, or redaction-shaped secret/path/host | HTTP 400 |
| `weight` is non-numeric, NaN/Infinity, `< 0.1`, or `> 20` | HTTP 400 `invalid weight` |
| `mode` is not `disable` or `delete` | HTTP 400 `invalid mode` |
| `entry_id` is malformed | HTTP 400 `invalid entry_id` |
| `entry_id` is valid-shaped but not found | HTTP 404 `entry not found` |
| Strengthen `amount` is not an integer from 1 to 20 | HTTP 400 `invalid amount` |
| Strengthening a disabled entry | HTTP 400 `entry disabled` |
| Strengthening an entry whose preview is redacted/sensitive | HTTP 400; do not increase prompt weight |
| Delete mode `disable` | Soft-disable and keep the entry in storage/list with `status: disabled` |
| Delete mode `delete` | Remove only the selected entry from its collection |
| Disabled sample text appears again in collection path | Return `False`; do not create a new active duplicate |

### 5. Good/Base/Bad Cases

- Good: A local admin adds `entry_type="prompt_guidance"`, text `遇到求助先给结论`,
  and weight `2`; `/admin/memory` returns a `manual:` entry with a short preview,
  and prompt injection may include it as an `人工提示` line within
  `SELF_LEARNING_MAX_PROMPT_CHARS`.
- Good: A learned sample containing an inappropriate meme is disabled; the list
  still shows it as disabled for audit, prompt injection skips it, and collecting
  the same exact text later does not reactivate it.
- Good: A legacy learned sample without an `id` can be strengthened or disabled
  because the admin helper preserves the generated `sample:<hash>` ID before save.
- Base: `GET /admin/memory?group_id=975805598` returns counts and previews for only
  that group's `self_learning.json` file.
- Bad: Exposing full chat buffers, QQ user IDs, nicknames, provider URLs, API env
  names, tokens, or prompt bodies through `/admin/state`, `/admin/memory`, or the
  admin HTML.
- Bad: Strengthening redacted/sensitive content such as a token-shaped sample,
  because that can promote leaked secrets into future prompts.
- Bad: Treating `delete` as a broad cleanup command; it must affect only the
  selected `entry_id` and collection.

### 6. Tests Required

- `tests/test_admin_routes.py` must assert:
  - `/admin/memory`, `/admin/memory/add`, `/admin/memory/delete`, and
    `/admin/memory/strengthen` routes are registered;
  - non-loopback requests require a valid bridge token for list and all mutations;
  - `/admin` contains the dependency-free memory management panel and fetch/post
    paths, with no external script/link dependency;
  - `GET /admin/memory` serializes learned samples as short safe previews and does
    not emit URLs, raw user identifiers, API env names, tokens, or unrelated chat;
  - add, strengthen, soft-disable, and hard-delete return expected actions,
    counters, status, and weight/reinforcement changes;
  - sensitive manual input, non-finite weights, sensitive strengthen targets, and
    invalid IDs/modes/amounts fail safely;
  - legacy generated IDs stay usable after mutation/save normalization.
- `tests/test_self_learning.py` must assert:
  - disabled samples are skipped by prompt context;
  - exact disabled text is not recollected as a new active sample;
  - unrelated new samples still collect after a disabled sample exists.
- Runtime validation:
  ```bash
  ./venv/bin/python -m py_compile bridge.py qq_hermes_bridge/*.py
  ./venv/bin/python -m pytest tests/test_admin_routes.py tests/test_self_learning.py tests/test_bridge_self_learning.py -q
  ./venv/bin/python -m pytest tests/test_inbound_auth.py tests/test_metrics_module.py -q
  ```

### 7. Wrong vs Correct

#### Wrong

```python
@app.post("/admin/memory/strengthen")
async def admin_memory_strengthen(payload: dict[str, Any]) -> dict[str, Any]:
    # No admin guard, no ID validation, and may promote leaked tokens into prompts.
    item = find_by_text(payload["text"])
    item["weight"] = 999
    return {"ok": True, "item": item}  # leaks raw text and storage shape
```

#### Correct

```python
@app.post("/admin/memory/strengthen")
async def admin_memory_strengthen(req: Request, payload: AdminMemoryStrengthenRequest) -> dict[str, Any]:
    require_admin_access(req)
    try:
        return admin_memory.strengthen_entry(
            admin_memory.group_id_or_default(payload.group_id, target_group_id=TARGET_GROUP_ID),
            entry_id=payload.entry_id,
            amount=payload.amount,
            group_config_dir=GROUP_CONFIG_DIR,
            config=SELF_LEARNING_CONFIG,
        )
    except admin_memory.AdminMemoryNotFound as exc:
        raise HTTPException(status_code=404, detail="entry not found") from exc
    except admin_memory.AdminMemoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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
