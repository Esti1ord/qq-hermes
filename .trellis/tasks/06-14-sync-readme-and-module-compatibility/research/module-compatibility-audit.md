# Module compatibility audit

## Scope

Audit compatibility across config/runtime/reply_queue/metrics/runtime_stats/admin/prompt/proactive/OCR/commands after completed reply-speed improvements.

## Confirmed-compatible items

- Direct config knobs are present and scoped in `qq_hermes_bridge/config.py::Config/load_config()` and mirrored by runtime globals: direct fast/strong aliases, direct transport override, timeout/output cap, prompt profile/budget, coalescing window, OCR wait, and proactive queue max age.
- Direct/proactive queues are separated in `qq_hermes_bridge/reply_queue.py`; direct drains before proactive, and proactive replacement does not affect direct.
- Direct burst coalescing is conservative and direct-only via `reply_queue.is_safe_direct_coalesce_intent()` and `coalesced_user_text_for_prompt()`; commands, media/OCR, reply markers, already-started intents, non-text messages, and non-direct intents are excluded.
- Direct fast/strong routing is scoped through `runtime.direct_model_for_group()`, `direct_profile_for_intent()`, `direct_text_http_config_for_group()`, `run_direct_hermes_raw_result()`, and `run_direct_hermes_raw()`.
- Strong direct applies to reply-to-bot/media/OCR-dependent direct intents only and preserves provider/base URL/API-key env/session/fallback behavior.
- Generic Hermes, proactive, command, OCR, and summary paths remain separate from direct wrappers.
- Runtime stats, Prometheus metrics, and admin state use content-safe booleans, lengths, statuses, durations, queue sizes, and low-cardinality profile labels.
- Direct prompt profile handling is compatible with speed work; proactive prompt still keeps `<SILENT>` exactly once.
- OCR/media direct wait remains isolated to direct prompt construction; timeout proceeds without OCR and late OCR can still update context/cache.
- Proactive priority/stale behavior remains compatible: stale proactive is skipped and direct pending takes priority.
- Commands are selected before direct/proactive generation and should not use direct model knobs.

## Caveats / gaps to verify

- When only `DIRECT_STRONG_MODEL_ALIAS` is set, standard direct replies enter the direct wrapper path but should pass `strong=False` and must not use the strong alias.
- Add narrow tests to prove direct-only model/transport knobs do not affect command/proactive flows.
- Add narrow test to prove completed OCR/media context can trigger `strong=True` direct routing while stats remain safe.
- Metrics naming: outbound duplicate suppression uses `qq_hermes_direct_coalesced_total`; burst queue coalescing is represented as queue event `status="coalesced"`. This is documentation terminology, not a regression.
