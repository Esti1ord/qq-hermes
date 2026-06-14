# Continue reply speed improvement plan

## Goal

Continue implementing the remaining high-value items from the June 14 QQ group reply-speed plan after the first observability/prompt/OCR/proactive pass. This follow-up should keep changes conservative, content-safe, and rollbackable while improving latency under bursty direct traffic and making fast-lane model/output knobs explicit.

## What I already know

* The prior task already implemented content-safe reply latency metrics/stats, direct prompt fast profile and total budget metadata, proactive/direct scheduling safeguards, OCR direct wait metrics, config/spec coverage, and clean-checkout `/context` test isolation.
* The saved plan still calls out follow-up work for direct burst coalescing, model/transport fast-lane knobs, outbound send observability/decoupling, and later cautious direct concurrency.
* Current `reply_queue.py` has separate direct/proactive queues and direct priority, but no direct coalescing helper.
* Current `runtime.py` exposes `enqueue_reply_intent()`, `dequeue_reply_intent()`, `process_one_reply_intent()`, `drain_reply_queue()`, and `ensure_reply_worker()` around the queue; direct intents are processed serially per group.
* Current model path uses `hermes_model_for_group()`, `hermes_provider_for_group()`, `primary_text_http_config_for_group()`, `run_text_http_result()`, `run_hermes_raw_result()`, `run_direct_hermes_raw()`, and `generate_direct_reply()`; the prior pass added prompt fast profile but not explicit direct fast/strong model aliases or direct-specific timeout/output caps.
* Current outbound path already records send duration and rate-limit wait through `send_group_msg_rate_limited()`; full outbound queue decoupling is higher risk and should remain out of scope unless metrics prove send wait dominates.
* Content safety remains non-negotiable: no raw prompt/message/reply/OCR text/image URL/provider URL/API key/env secret values in runtime stats, metrics, admin state, or logs.
* Proactive rendered prompts must keep `<SILENT>` exactly once.
* There is unrelated WIP in this checkout (`.env.example`, `README.md`, JRRP files, untracked Trellis/bootstrap files, etc.); commits for this task must stage only relevant files.

## Requirements

* Add a conservative direct burst coalescing mechanism controlled by `DIRECT_COALESCE_WINDOW_MS`, default disabled (`0`) or otherwise rollbackable by setting `0`.
* Coalesce only not-yet-started direct intents in the same group from the same sender/route when safe; do not merge proactive, commands, different senders, different route kinds, strong reply-target/image-dependent/direct OCR cases, or already-started intents.
* Preserve original message order and enough event metadata for the actual reply target; merged text should be represented only inside the prompt path, not in content-safe metrics/log fields.
* Emit content-safe coalescing metadata/counters only: group id (subject to existing sanitizer/metrics rules), kind, merged count, window ms, queue sizes, statuses.
* Add explicit direct fast-lane model/output config plumbing where it can be done safely without changing default routing semantics unexpectedly: fast/strong aliases, direct timeout, and direct output cap should be configurable and observable only as safe metadata.
* Avoid broad retries that multiply latency; keep existing fallback semantics and direct failure notice behavior.
* Update config/docs/tests for any new knobs introduced in this task.
* Commit each important improvement separately, without staging unrelated WIP.

## Acceptance Criteria

* [ ] `reply_queue.py` has focused tests for safe direct coalescing and no coalescing across unsafe boundaries.
* [ ] Runtime enqueue/dequeue behavior honors `DIRECT_COALESCE_WINDOW_MS` and records safe `direct_coalesced`/queue metadata.
* [ ] Metrics map coalescing events to existing or new safe counters without exposing message text.
* [ ] Direct fast-lane model/output config is covered by focused tests and does not leak model provider URLs/API env names or prompt text.
* [ ] Proactive `<SILENT>` invariant remains covered by existing tests.
* [ ] Syntax check passes: `./venv/bin/python -m py_compile bridge.py qq_hermes_bridge/*.py`.
* [ ] Focused tests for changed modules pass; full suite is run when practical.

## Definition of Done

* Tests added/updated for changed behavior.
* Relevant specs/docs updated if new runtime contracts are introduced.
* Important improvement commits are made separately and contain only scoped files.
* Existing unrelated WIP is preserved and not mixed into these commits.
* Rollback path is clear through env/config defaults.

## Technical Approach

1. Implement direct coalescing in `reply_queue.py` as a small helper used by runtime enqueue, with conservative safety checks and default-off `DIRECT_COALESCE_WINDOW_MS`.
2. Add runtime/config/docs/tests for direct coalescing and safe `queue_event`/metrics observation.
3. Add direct fast-lane configuration plumbing for direct-specific model alias/timeout/output cap with default-compatible behavior and tests.
4. Verify with syntax and focused tests, then commit scoped changes after each important improvement.

## Decision (ADR-lite)

**Context**: The first speed pass reduced prompt size and observability gaps. Remaining latency during rapid user bursts can still be amplified by duplicate direct model calls, and model/output latency knobs are not explicit enough for rollbackable fast-lane tuning.

**Decision**: Prioritize conservative, default-off direct burst coalescing and explicit fast-lane config plumbing. Defer outbound worker decoupling and direct concurrency because those alter ordering/semantics more substantially and should be driven by collected metrics.

**Consequences**: This adds small queue/prompt complexity but keeps rollout safe: setting `DIRECT_COALESCE_WINDOW_MS=0` disables coalescing, and direct concurrency remains unchanged at one inflight reply per group.

## Out of Scope

* Do not implement direct concurrency greater than 1 in this task.
* Do not add a per-group outbound worker queue unless tests/metrics prove send wait dominates.
* Do not replace provider-neutral/OpenAI-compatible code with Anthropic-specific SDK code.
* Do not commit unrelated JRRP/docs/persona/bootstrap WIP.

## Technical Notes

* Relevant plan: `/home/roxy/.claude/plans/superpower-skill-qq-concurrent-fog.md`.
* Relevant specs read: backend directory structure, logging guidelines, error handling, quality guidelines, shared cross-layer and code-reuse guides.
* Key files likely touched: `qq_hermes_bridge/reply_queue.py`, `qq_hermes_bridge/runtime.py`, `qq_hermes_bridge/config.py`, `qq_hermes_bridge/metrics.py`, tests for reply queue/runtime/config/metrics, and docs/env examples only if scoped.
