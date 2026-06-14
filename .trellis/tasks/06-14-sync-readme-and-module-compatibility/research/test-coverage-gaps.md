# Test coverage gap audit

## Existing coverage

- Direct coalescing has queue-helper, runtime integration, runtime-stat, and Prometheus metric coverage.
- Direct fast/strong routing has config loading, empty-knob compatibility, CLI/HTTP direct lanes, timeout/output cap, safe logs, fallback identity skip, and admin-state coverage.
- Direct/proactive queue priority is covered, including direct FIFO before proactive and proactive direct-pending/stale skips.
- Commands are covered as deterministic no-LLM routes in normal settings.
- OCR/media behavior is covered for prompt inclusion, quoted/embedded image lookup, `direct_only` exclusion, slow OCR timeout, OCR fallback, safe stats, and direct media/reply-to-bot strong profile separately.

## High-value focused tests to run

```bash
./venv/bin/python -m py_compile bridge.py qq_hermes_bridge/*.py
./venv/bin/python -m pytest tests/test_reply_queue_module.py tests/test_direct_reply_inflight.py tests/test_metrics_module.py tests/test_runtime_stats_module.py -q
./venv/bin/python -m pytest tests/test_config_utils_module.py tests/test_hermes_group_sessions.py tests/test_admin_routes.py -q
./venv/bin/python -m pytest tests/test_bridge_ocr.py tests/test_prompt_service_module.py -q
./venv/bin/python -m pytest tests/test_proactive_speaking.py tests/test_context.py tests/test_persona_and_commands.py tests/test_handlers_module.py -q
```

## Recommended new focused tests

- OCR/direct-strong integration for completed OCR wait plus `strong=True` direct routing and safe stats.
- Command compatibility under direct-only model/transport knobs.
- Proactive compatibility under direct-only model/transport knobs.
- Optional coalescing edge cases: exact window boundary, CQ-string reply/image, and `@all` segments.
