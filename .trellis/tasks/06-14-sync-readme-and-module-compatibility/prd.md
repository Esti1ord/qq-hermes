# Sync README documentation and audit module compatibility

## Goal

Synchronize README documentation with the completed reply-speed improvements and audit adjacent module compatibility so direct reply coalescing, fast/strong model routing, observability, admin state, metrics, and tests remain consistent across the project.

## What I already know

* The reply-speed task completed and was archived after commits `cb2dd81`, `f9374dc`, `bcf8195`, and `02ad2e7`.
* Implemented behavior includes default-off direct burst coalescing, direct fast/strong model/output knobs, conservative strong direct routing, and content-safe observability/spec coverage.
* Remaining dirty `README.md` and `.env.example` changes were intentionally not committed during the reply-speed finish-work because they belonged to other/parallel documentation organization work.
* The user has restarted the service and now wants README synchronization plus an audit of adaptation/compatibility with other modules.
* Project safety constraints still apply: do not print or commit local secrets; do not expose provider URLs/API keys/API-key env names/raw chat/prompt/OCR/model output in logs/docs/examples.

## Assumptions (temporary)

* The README sync should document the newly completed reply-speed configuration and operational behavior in a content-safe way.
* The compatibility audit should focus on modules touched or affected by reply-speed changes: config, runtime/direct reply flow, reply queue, metrics, admin state, prompt service/proactive behavior, OCR/media handling, and tests.
* Any code changes should be conservative and only fix verified integration gaps found during the audit.

## Open Questions

* None for MVP. Scope is limited to reply-speed README/env synchronization plus narrow compatibility tests; broader README/environment organization WIP stays out of this task.

## Requirements (evolving)

* Review current README documentation against the implemented reply-speed behavior.
* Update README examples/env sections so operators can safely configure direct coalescing and direct fast/strong routing.
* Clarify that `DIRECT_STRONG_MODEL_ALIAS` is model-only and applies only to reply-to-bot and media/OCR-dependent direct intents.
* Clarify that `DIRECT_COALESCE_WINDOW_MS` is default-off and only merges pending same-group/same-sender/same-route ordinary text direct intents.
* Audit adjacent modules for compatibility regressions or mismatch with the new direct reply behavior.
* Add narrow tests for verified adaptation boundaries: direct-only knobs do not affect commands/proactive, and OCR/media direct context can select the strong direct profile safely.
* Preserve content-safe observability and secret-redaction guarantees in docs and code.
* Avoid staging unrelated JRRP/persona/bootstrap/local WIP.

## Acceptance Criteria (evolving)

* [x] README documents `DIRECT_COALESCE_WINDOW_MS` default-off behavior and safe coalescing boundaries.
* [x] README documents direct fast/strong model knobs and clarifies empty/zero values preserve existing behavior.
* [x] README documents strong direct routing as reply-to-bot/media/OCR direct only, model-only, preserving provider/session/fallback behavior.
* [x] README avoids raw provider URLs, API keys, prompt text, chat text, OCR text, image URLs, or model output examples.
* [x] `.env.example` comments for direct strong/coalescing match implementation boundaries.
* [x] Compatibility audit covers config/runtime/reply queue/metrics/admin/prompt/proactive/OCR-adjacent behavior and records findings.
* [x] Focused tests cover direct-only config isolation for commands/proactive and OCR/media strong direct routing.
* [x] Focused tests and syntax checks pass; full suite is run if code changes are made.

## Definition of Done (team quality bar)

* Tests added/updated where behavior changes.
* Syntax/lint/regression checks pass at the appropriate scope.
* Docs/spec notes updated if behavior changes.
* Rollout/rollback considered for config changes.
* Commits are scoped; important improvements are committed separately.

## Out of Scope (explicit)

* Reworking JRRP behavior or fortune grading.
* Committing local secret config, `.env`, runtime caches, or broad `.trellis/` local state.
* Increasing direct reply concurrency above one.
* Adding outbound worker queues unless the audit proves a concrete need.

## Technical Notes

* Created from user request on 2026-06-14 after the service restart.
* Prior reply-speed work commits to reference: `cb2dd81`, `f9374dc`, `bcf8195`, `02ad2e7`.
* Need to inspect README, `.env.example`, config/runtime/reply queue/metrics/admin tests, and relevant backend specs before implementation.
