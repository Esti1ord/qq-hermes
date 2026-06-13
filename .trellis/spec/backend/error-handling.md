# Error Handling

> How errors are handled in this project.

---

## Overview

Backend error handling should keep QQ-facing output short and safe while preserving
low-cardinality runtime metadata for diagnosis. Provider/env alias resolution is
part of that contract: the bridge must resolve model/provider env aliases
predictably, fall back safely, and never log prompts, raw model output, OCR text,
provider base URLs, API key env names/values, image URLs, or full provider
responses.

---

## Error Types

- **Hermes text generation failure**: subprocess launch failure, timeout, nonzero
  exit, unknown/invalid provider identifier, missing/invalid group session, or
  empty model output.
- **OCR provider failure**: image fetch failure, external provider error, skipped
  provider, malformed provider response, missing model/base URL/API-key env name,
  or missing API key value.
- **Configuration precedence failure**: wrong alias wins, vice/fallback config is
  accidentally treated as the default primary path, or a raw API key value is
  copied instead of passing its env var name through the runtime.
- **OneBot send failure**: failed outbound HTTP response or exception while
  sending the final QQ message.

---

## Error Handling Patterns

### Scenario: Provider/env alias precedence and fallback for text and OCR

#### 1. Scope / Trigger

- Trigger: changing text/OCR env resolution, per-group text routing, Hermes CLI
  `--provider` values, OCR provider wiring, provider fallback behavior, direct
  generation failure notices, or related logging/runtime stats.
- Why: alias precedence now decides which provider/model actually runs. Wrong
  precedence silently routes traffic to the wrong provider, suppresses fallback,
  or leaks secrets during outage debugging.

#### 2. Signatures

Runtime globals in `qq_hermes_bridge/runtime.py`:

```python
HERMES_MODEL: str
HERMES_PROVIDER: str
HERMES_PROVIDER_BASE_URL: str
HERMES_API_KEY_ENV: str
HERMES_FALLBACK_ENABLED: bool
HERMES_FALLBACK_MODEL: str
HERMES_FALLBACK_PROVIDER: str
HERMES_FALLBACK_PROVIDER_BASE_URL: str
HERMES_FALLBACK_API_KEY_ENV: str
HERMES_MODEL_BY_GROUP: dict[int, str]
HERMES_PROVIDER_BY_GROUP: dict[int, str]
OCR_PROVIDER: str
OCR_MODEL: str
OCR_PROVIDER_BASE_URL: str
OCR_API_KEY_ENV: str
OCR_FALLBACK_ENABLED: bool
OCR_FALLBACK_PROVIDER: str
OCR_FALLBACK_MODEL: str
OCR_FALLBACK_PROVIDER_BASE_URL: str
OCR_FALLBACK_API_KEY_ENV: str
OCR_EXTERNAL_PROVIDER_ALLOWED: bool
DIRECT_GENERATION_FAILURE_NOTICE: str
```

Runtime/config helper signatures:

```python
def env_first(*names: str, default: str = "") -> str: ...
def env_name_if_set(*names: str) -> str: ...
def hermes_model_for_group(group_id: int | None) -> str: ...
def hermes_provider_for_group(group_id: int | None) -> str: ...
def text_model_http_config(
    *,
    provider: str,
    model: str,
    base_url: str,
    api_key_env: str,
) -> dict[str, str] | None: ...
def primary_text_http_config_for_group(group_id: int | None = None) -> dict[str, str] | None: ...
def fallback_text_http_config() -> dict[str, str] | None: ...
def run_text_http_result(
    prompt: str,
    *,
    config: dict[str, str],
    group_id: int | None = None,
    purpose: str = "unknown",
    phase: str = "primary",
) -> dict[str, Any]: ...
def hermes_fallback_available(group_id: int | None = None) -> bool: ...
def run_hermes_fallback_result(
    prompt: str,
    group_id: int | None = None,
    *,
    purpose: str = "unknown",
    primary_reason: str = "",
) -> dict[str, Any] | None: ...
def run_hermes_raw_result(
    prompt: str,
    group_id: int | None = None,
    use_group_session: bool = True,
    purpose: str = "unknown",
) -> dict[str, Any]: ...
def build_ocr_provider() -> vision.VisionProvider: ...
def build_ocr_fallback_provider() -> vision.VisionProvider: ...
async def recognize_image_with_fallback(
    fetched: media_fetch.MediaFetchResult,
    primary_provider: vision.VisionProvider,
) -> media.MediaRecognition: ...
def direct_failure_notice_for_event(event: dict[str, Any]) -> str: ...
```

Typed config fields in `qq_hermes_bridge/config.py` mirror these env-backed
runtime fields one-to-one using lowercase names, for example `hermes_model`,
`hermes_provider_base_url`, `hermes_api_key_env`,
`hermes_fallback_provider_base_url`, `hermes_fallback_api_key_env`,
`ocr_api_key_env`, and `ocr_fallback_api_key_env`.

#### 3. Contracts

Text generation env precedence:

| Setting | Resolution order | Contract |
|---|---|---|
| Primary text model | `PRIMARY_CHAT_MODEL` → `HERMES_MODEL` → `deepseekv4flash` | Default groups use this resolved value unless `HERMES_MODEL_BY_GROUP[group_id]` overrides it |
| Primary text provider | `PRIMARY_CHAT_MODEL_PROVIDER` → `HERMES_PROVIDER` → `custom` | OpenAI-compatible direct HTTP is allowed for supported aliases when URL/API env are configured; otherwise this is passed to Hermes CLI after safe alias normalization |
| Primary text URL | `PRIMARY_CHAT_MODEL_URL` → `PRIMARY_CHAT_MODEL_BASE_URL` → `CUSTOM_CHAT_MODEL_URL` → `CUSTOM_CHAT_MODEL_BASE_URL` → `CUSTOM_PROVIDER_URL` → `CUSTOM_PROVIDER_BASE_URL` → `HERMES_PROVIDER_BASE_URL` | Enables OpenAI-compatible direct HTTP for supported providers; custom-channel aliases are compatibility fallback only after canonical `PRIMARY_CHAT_*`; never log it |
| Primary text API key env name | explicit/raw primary group first (`PRIMARY_CHAT_MODEL_API_KEY_ENV`, then raw-name detection on `PRIMARY_CHAT_MODEL_API_KEY` / `PRIMARY_CHAT_MODEL_API`) → explicit/raw custom-channel group (`CUSTOM_CHAT_MODEL_API_KEY_ENV` / `CUSTOM_PROVIDER_API_KEY_ENV` / `CUSTOM_API_KEY_ENV`, then raw-name detection on `CUSTOM_CHAT_MODEL_API_KEY` / `CUSTOM_CHAT_MODEL_API` / `CUSTOM_PROVIDER_API_KEY` / `CUSTOM_PROVIDER_API` / `CUSTOM_API_KEY` / `CUSTOM_API`) → explicit/raw legacy group (`HERMES_API_KEY_ENV`, then `HERMES_API_KEY`) | Pass the env var name into the HTTP helper; do not copy or log the secret value |
| Fallback text model | `VICE_CHAT_MODEL` → `HERMES_FALLBACK_MODEL` → `deepseekv4flash` | Used only for retry after primary failure/empty output |
| Fallback text provider | `VICE_CHAT_MODEL_PROVIDER` → `HERMES_FALLBACK_PROVIDER` → `deepseek` | Default fallback is official DeepSeek; legacy display label `官方` is normalized to Hermes provider `deepseek` |
| Fallback text URL | `VICE_CHAT_MODEL_URL` → `VICE_CHAT_MODEL_BASE_URL` → `HERMES_FALLBACK_PROVIDER_BASE_URL` | Enables OpenAI-compatible fallback HTTP for supported providers; never log it |
| Fallback text API key env name | explicit `VICE_CHAT_MODEL_API_KEY_ENV` → `HERMES_FALLBACK_API_KEY_ENV`, else raw-name detection on `VICE_CHAT_MODEL_API_KEY` / `VICE_CHAT_MODEL_API` / `HERMES_FALLBACK_API_KEY` | Pass the env var name into the HTTP helper; do not copy or log the secret value |
| Per-group model override | `HERMES_MODEL_BY_GROUP[group_id]` | Overrides the primary text model for that group only |
| Per-group provider override | `HERMES_PROVIDER_BY_GROUP[group_id]` | Overrides the primary text provider for that group only |

OCR env precedence:

| Setting | Resolution order | Contract |
|---|---|---|
| Primary OCR provider | `PRIMARY_OCR_MODEL_PROVIDER` → `IMAGE_MODEL_PROVIDER` → `OCR_PROVIDER` → `custom` | Legacy `OCR_*` names remain compatible as the fallback chain |
| Primary OCR model | `PRIMARY_OCR_MODEL` → `IMAGE_MODEL` → `OCR_MODEL` → `mimo` | Used for model-backed OCR providers; builders may fall back to `HERMES_MODEL` when required |
| Primary OCR URL | `PRIMARY_OCR_MODEL_URL` → `PRIMARY_OCR_MODEL_BASE_URL` → `IMAGE_MODEL_URL` → `IMAGE_MODEL_BASE_URL` → `OCR_PROVIDER_BASE_URL` | Provider root or `/chat/completions` endpoint; never log it |
| Primary OCR API key env name | explicit `PRIMARY_OCR_MODEL_API_KEY_ENV` → `IMAGE_MODEL_API_KEY_ENV` → `OCR_API_KEY_ENV`, else raw-name detection on `PRIMARY_OCR_MODEL_API_KEY` / `PRIMARY_OCR_MODEL_API` / `IMAGE_MODEL_API_KEY` / `IMAGE_MODEL_API` / `OCR_API_KEY` | Pass the env var name into the provider; do not copy or log the secret value |
| Fallback OCR provider | `VICE_OCR_MODEL_PROVIDER` → `OCR_FALLBACK_PROVIDER` → `custom` | Used only after non-`ok` primary OCR result and only when external providers are allowed |
| Fallback OCR model | `VICE_OCR_MODEL` → `OCR_FALLBACK_MODEL` → `gpt-5.4` | Used only for OCR fallback |
| Fallback OCR URL | `VICE_OCR_MODEL_URL` → `VICE_OCR_MODEL_BASE_URL` → `OCR_FALLBACK_PROVIDER_BASE_URL` | Provider root or `/chat/completions` endpoint; never log it |
| Fallback OCR API key env name | explicit `VICE_OCR_MODEL_API_KEY_ENV` → `OCR_FALLBACK_API_KEY_ENV`, else raw-name detection on `VICE_OCR_MODEL_API_KEY` / `VICE_OCR_MODEL_API` / `OCR_FALLBACK_API_KEY` | Pass the env var name into the provider; do not copy or log the secret value |

Behavior contracts:

- Groups not listed in `HERMES_MODEL_BY_GROUP` / `HERMES_PROVIDER_BY_GROUP`
  use the resolved primary text block. They do not inherit the vice/fallback
  block for normal traffic.
- If only one per-group text override exists, override only that field and keep
  the other field from the resolved primary text block.
- Hermes CLI provider names must be Hermes-known identifiers after safe alias
  normalization. Legacy display label `官方` maps to `deepseek`; other unknown
  labels cause a nonzero Hermes run, may trigger fallback, and must not be
  documented as valid active `*_PROVIDER` values unless Hermes is configured to
  recognize them.
- OpenAI-compatible text providers use direct HTTP only when provider is a
  supported direct alias and both provider URL and API-key env name are present.
  Missing URL/model/API config must return safe low-cardinality reasons without
  leaking prompt, URL, API env name/value, response body, or model output.
- Direct HTTP URL normalization may append `/chat/completions`; the raw provider
  base URL must never appear in logs, runtime stats, metrics, or QQ-visible
  messages.
- Direct HTTP request payloads may include the prompt and image/OCR content only
  in the outbound provider request. Logs/stats/results must contain booleans,
  lengths, status/reason, purpose/phase, and durations only.
- `run_hermes_raw_result()` attempts the active primary path first: direct HTTP
  when fully configured, otherwise Hermes CLI/session. Fallback is attempted when
  the primary path fails, times out, returns nonzero/HTTP error, has malformed
  response, or returns empty output.
- Text fallback must run with `use_group_session=False`; do not continue or
  mutate the primary group session during outage recovery.
- Text fallback is skipped when the fallback `(model, normalized provider,
  base_url, api_key_env)` matches the active primary identity after per-group
  overrides and provider normalization.
- `build_ocr_provider()` / `build_ocr_fallback_provider()` must pass API key env
  names into runtime vision providers. The bridge must not rewrite/copy secret
  values into new env vars, config fields, logs, or metrics.
- Primary/fallback OCR provider construction must still obey
  `OCR_EXTERNAL_PROVIDER_ALLOWED`. If the gate is off, external provider builds
  return `NoopVisionProvider`.
- `recognize_image_with_fallback()` runs fallback when primary recognition
  returns any non-`ok` status, including `error` and `skipped`. If fallback also
  fails, downstream OCR context degrades to placeholders rather than fabricating
  text.
- Provider failure logs/runtime stats may include purpose, phase, group id,
  booleans, return code, configured/not-configured flags, safe status/reason,
  output/result lengths, and durations. They must not include prompt text, raw
  stdout/stderr, OCR text, provider base URLs, API key env names/values, image
  URLs, or full provider responses.

Direct visible failure contract:

```python
DIRECT_GENERATION_FAILURE_NOTICE == "没有油烧了谁给我加加油"
```

When direct generation still fails after primary + fallback + empty-output retry,
`process_direct_reply_intent()` sends `direct_failure_notice_for_event(event)`
instead of exposing provider details or rotating raw provider errors.

#### 4. Validation & Error Matrix

| Condition | Expected behavior |
|---|---|
| `PRIMARY_CHAT_MODEL` and `HERMES_MODEL` are both set | Use `PRIMARY_CHAT_MODEL` |
| `PRIMARY_CHAT_MODEL_PROVIDER` and `HERMES_PROVIDER` are both set | Use `PRIMARY_CHAT_MODEL_PROVIDER` |
| `CUSTOM_CHAT_MODEL_*` / `CUSTOM_PROVIDER_*` and `HERMES_*` text URL/API aliases are both set | Use the custom-channel aliases for primary direct HTTP config, because they are more specific than legacy Hermes aliases |
| `PRIMARY_CHAT_MODEL_*` and custom-channel text URL/API aliases are both set | Use the canonical `PRIMARY_CHAT_MODEL_*` aliases |
| `VICE_CHAT_MODEL` and `HERMES_FALLBACK_MODEL` are both set | Use `VICE_CHAT_MODEL` |
| Neither vice alias nor legacy text fallback is set | Use hard-coded text fallback defaults `deepseekv4flash` / `deepseek` |
| Primary text provider is direct-compatible but URL or API env is missing | Use Hermes CLI path rather than direct HTTP |
| Primary direct HTTP helper returns HTTP status / invalid JSON / malformed response / empty text | Return a safe reason, omit prompt/URL/API env/response body/output, then try fallback when enabled |
| `官方` is configured as fallback text provider | Normalize to Hermes provider `deepseek` before CLI invocation and fallback identity comparison |
| Group id is absent from both text override maps | Use the resolved primary text block |
| Group id is present only in `HERMES_MODEL_BY_GROUP` | Override model only; keep provider from the resolved primary block |
| Active text provider label is unknown to Hermes CLI | Hermes run returns nonzero; safe logs/stats only; normal fallback/visible-failure rules continue |
| Primary Hermes subprocess returns nonzero / launch error / timeout / empty output | Try fallback no-session command when available |
| Fallback text identity equals active per-group primary identity after provider/base-url/API-env normalization | Skip fallback to avoid retrying the same outage |
| Raw OCR key env like `PRIMARY_OCR_MODEL_API` is set | Store/pass the env var name `PRIMARY_OCR_MODEL_API`, not the secret value |
| `PRIMARY_OCR_MODEL_*` and legacy `OCR_*` values are both set | Use the primary OCR alias chain |
| `VICE_OCR_MODEL_*` and legacy `OCR_FALLBACK_*` values are both set | Use the vice OCR alias chain |
| `OCR_EXTERNAL_PROVIDER_ALLOWED=false` | Build no external primary/fallback OCR provider |
| Primary OCR provider returns `ok` | Do not run OCR fallback |
| Primary OCR provider returns `error` or `skipped` | Try OCR fallback if available |
| OCR provider/fallback fails | Logs/stats omit OCR text, provider URL, API key env names/values, and raw provider payloads |

#### 5. Good/Base/Bad Cases

- Good: `PRIMARY_CHAT_MODEL` / `PRIMARY_CHAT_MODEL_PROVIDER` and legacy
  `HERMES_*` are both present; runtime uses the primary aliases, while
  `HERMES_MODEL_BY_GROUP` changes only the targeted group.
- Good: primary text provider is `custom`, URL/API env are configured, and the
  runtime uses direct HTTP with logs containing only status/reason, booleans,
  lengths, purpose/phase, and duration.
- Good: fallback text provider is legacy label `官方`; runtime sends Hermes CLI
  `--provider deepseek` and compares fallback identity using `deepseek`.
- Good: `PRIMARY_OCR_MODEL_API` exists in the environment; runtime passes the env
  name `PRIMARY_OCR_MODEL_API` into the vision provider and does not copy the
  secret value into config/log output.
- Good: `IMAGE_MODEL` / `IMAGE_MODEL_BASE_URL` / `IMAGE_MODEL_API` are present;
  runtime treats them as primary OCR aliases when canonical `PRIMARY_OCR_MODEL_*`
  values are unset.
- Base: only legacy `HERMES_*`, `OCR_*`, and `OCR_FALLBACK_*` names are set;
  runtime stays compatible and fallback still works.
- Bad: setting `VICE_CHAT_MODEL` / `VICE_CHAT_MODEL_PROVIDER` and expecting all
  normal traffic to use them. The vice block is fallback-only.
- Bad: using a display/vendor label other than the supported `官方` alias as
  `PRIMARY_CHAT_MODEL_PROVIDER` or `VICE_CHAT_MODEL_PROVIDER` when Hermes CLI
  does not know that identifier.
- Bad: writing the actual secret into `OCR_API_KEY_ENV` or
  `OCR_FALLBACK_API_KEY_ENV`; those fields carry env var names only.
- Bad: logging prompts, OCR text, provider base URLs, API key env names/values,
  or raw provider payloads while debugging precedence or fallback failures.

#### 6. Tests Required

- `tests/test_config_utils_module.py` must assert:
  - primary/vice text aliases win over legacy `HERMES_*` names;
  - primary/vice text URL and API env aliases resolve to direct HTTP config fields;
  - custom-channel text URL/API aliases resolve only after canonical `PRIMARY_CHAT_*` and before legacy `HERMES_*` aliases;
  - primary/vice OCR aliases win over legacy `OCR_*` / `OCR_FALLBACK_*` names;
  - `IMAGE_MODEL_*` aliases feed the primary OCR block when canonical OCR aliases are unset;
  - raw text/OCR key envs resolve to env var names such as `PRIMARY_CHAT_MODEL_API`,
    `VICE_CHAT_MODEL_API`, `PRIMARY_OCR_MODEL_API`, and `VICE_OCR_MODEL_API`, not secret values;
  - hard-coded text/OCR fallback defaults apply only when alias and legacy keys
    are both unset.
- `tests/test_hermes_group_sessions.py` must assert:
  - bridge import prefers primary/vice chat aliases;
  - default groups use the primary text block and `HERMES_*_BY_GROUP` only
    overrides targeted groups;
  - primary nonzero/empty output triggers a second command without `--continue`;
  - direct HTTP primary/fallback routing is used when URL/API env are configured;
  - direct HTTP fallback does not use group sessions;
  - `官方` is normalized to `deepseek` for Hermes CLI and fallback identity comparison;
  - matching primary/fallback model-provider/base-url/API-env skips fallback;
  - Hermes/HTTP start/error logs do not include prompt/model/provider URL/API env details.
- `tests/test_bridge_ocr.py` must assert:
  - primary OCR aliases win over legacy `OCR_*` settings;
  - vice OCR aliases win over legacy `OCR_FALLBACK_*` settings;
  - OCR fallback/provider wiring passes env names, not secret values;
  - `OCR_EXTERNAL_PROVIDER_ALLOWED=false` returns `NoopVisionProvider`;
  - OCR fallback logs omit provider URLs and API key env names.
- If the direct visible failure path changes,
  `tests/test_direct_reply_inflight.py` must still assert the exact notice
  `没有油烧了谁给我加加油` with reply/@ prefix behavior.
- Syntax and focused validation:
  ```bash
  ./venv/bin/python -m py_compile bridge.py qq_hermes_bridge/*.py
  ./venv/bin/python -m pytest tests/test_config_utils_module.py tests/test_hermes_runtime_module.py tests/test_hermes_group_sessions.py tests/test_bridge_ocr.py tests/test_direct_reply_inflight.py -q
  ```

#### 7. Wrong vs Correct

##### Wrong

```python
# Gives legacy/fallback precedence over aliases and copies a secret value.
hermes_model = os.getenv("HERMES_MODEL", os.getenv("PRIMARY_CHAT_MODEL", ""))
hermes_provider = os.getenv("HERMES_FALLBACK_PROVIDER", os.getenv("HERMES_PROVIDER", ""))
ocr_api_key_env = os.getenv("PRIMARY_OCR_MODEL_API", os.getenv("OCR_API_KEY_ENV", ""))
```

##### Correct

```python
# Resolve aliases first, keep vice config fallback-only, and pass env names only.
hermes_model = _env_first("PRIMARY_CHAT_MODEL", "HERMES_MODEL", default="deepseekv4flash")
hermes_provider = _env_first("PRIMARY_CHAT_MODEL_PROVIDER", "HERMES_PROVIDER", default="custom")
hermes_provider_base_url = _env_first(*config_utils.PRIMARY_CHAT_PROVIDER_URL_ENV_NAMES)
hermes_api_key_env = config_utils.api_key_env_name_from_groups(
    config_utils.PRIMARY_CHAT_API_KEY_ENV_GROUPS
)
hermes_fallback_model = _env_first(
    "VICE_CHAT_MODEL",
    "HERMES_FALLBACK_MODEL",
    default="deepseekv4flash",
)
hermes_fallback_provider = _env_first(
    "VICE_CHAT_MODEL_PROVIDER",
    "HERMES_FALLBACK_PROVIDER",
    default="deepseek",
)
ocr_api_key_env = _api_key_env_name(
    explicit_names=("PRIMARY_OCR_MODEL_API_KEY_ENV", "IMAGE_MODEL_API_KEY_ENV", "OCR_API_KEY_ENV"),
    raw_names=(
        "PRIMARY_OCR_MODEL_API_KEY",
        "PRIMARY_OCR_MODEL_API",
        "IMAGE_MODEL_API_KEY",
        "IMAGE_MODEL_API",
        "OCR_API_KEY",
    ),
)
```

---

## API Error Responses

The bridge does not expose provider or env-resolution failure details directly
through a public API. For QQ-visible direct generation failures, send only the
stable notice from `direct_failure_notice_for_event()`. Internal HTTP endpoints
such as `/health` and `/metrics` must remain content-safe and low-cardinality.

---

## Common Mistakes

- Treating vice/fallback text config as the default routing path for all groups.
- Forgetting that `HERMES_MODEL_BY_GROUP` / `HERMES_PROVIDER_BY_GROUP` are
  explicit overrides only; groups without entries use the primary text block.
- Using a provider display/vendor label that Hermes CLI does not recognize, except
  the supported legacy `官方` alias that is normalized to `deepseek`.
- Assuming a direct-compatible provider always uses HTTP; direct HTTP also
  requires URL and API-key env-name configuration.
- Treating `OCR_API_KEY_ENV` / `OCR_FALLBACK_API_KEY_ENV` as API key values, or
  copying raw key values into other env/config fields.
- Logging prompts, model output, OCR text, provider base URLs, API key env
  names/values, or raw provider payloads while debugging fallback/provider
  failures.
- Documenting new alias families before code and tests actually wire them into
  `config.py` / `runtime.py`.
