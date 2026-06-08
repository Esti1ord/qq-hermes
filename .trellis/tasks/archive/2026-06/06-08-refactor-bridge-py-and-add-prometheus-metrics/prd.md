# Refactor bridge.py and Add Prometheus Metrics

## Goal

Split the monolithic `bridge.py` (3485 lines, 255 functions) into a maintainable module structure, and add production-grade Prometheus metrics for observability. This will improve code maintainability, reduce cognitive load, and enable proper production monitoring.

## What I Already Know

### Current Architecture
- **bridge.py**: 3485 lines, 255 functions/classes, mix of:
  - 100+ global config variables (lines 1-263)
  - Utility functions (log, stats, OCR, context helpers)
  - FastAPI app definition and 4 routes (`/health`, `/onebot`, `/test`)
  - Direct/proactive reply workers
  - Main entry point (uvicorn)
  
- **Existing modules** (well-organized):
  - 25 modules in `qq_hermes_bridge/` package
  - `runtime_stats.py`: JSON logging (no Prometheus yet)
  - `app_helpers.py`: Health endpoint logic
  - Other focused modules: `commands.py`, `handlers.py`, `context_store.py`, etc.

### Deployment Context
- Runs as systemd user service: `qq-hermes-bridge.service`
- FastAPI app on port 8765
- Health check: `http://127.0.0.1:8765/health`
- 338 existing tests (must remain passing)

### Constraints
- Private data in `groups/`, `logs/`, `napcat-data/` (gitignored)
- Must not break existing integrations (NapCat webhook, health checks)
- Tests must pass: `./venv/bin/python -m pytest tests -q`
- Config conventions from CLAUDE.md and README.md

## Requirements

### Phase 1: Refactor bridge.py

**Goal**: Extract reusable logic from bridge.py into focused modules

1. **Config module** (`qq_hermes_bridge/config.py`)
   - Centralize all 100+ global config variables
   - Provide typed config dataclass/namespace
   - Keep `.env` loading in bridge.py for now (avoid breaking systemd)

2. **App factory** (`qq_hermes_bridge/app.py`)
   - FastAPI app creation
   - Move route definitions here
   - Keep bridge.py as thin entry point

3. **Metrics module** (`qq_hermes_bridge/metrics.py`)
   - Runtime stat helpers currently in bridge.py
   - Bridge to Prometheus (Phase 2)

4. **Slimmed bridge.py**
   - Import config, create app, run uvicorn
   - Target: <500 lines

### Phase 2: Add Prometheus Metrics

**Goal**: Export metrics on `/metrics` endpoint for Prometheus scraping

1. **Core metrics** (map from existing `runtime_stats.jsonl` events):
   - **Counters**:
     - `qq_hermes_messages_total{route, group_id, result}` - Message routing decisions
     - `qq_hermes_replies_total{type, status}` - Reply attempts and outcomes
     - `qq_hermes_errors_total{component, error_type}` - Error tracking
   
   - **Histograms**:
     - `qq_hermes_reply_duration_seconds{type}` - E2E reply latency
     - `qq_hermes_hermes_call_duration_seconds` - Hermes CLI call time
     - `qq_hermes_ocr_duration_seconds{status}` - OCR processing time
   
   - **Gauges**:
     - `qq_hermes_queue_size{group_id, type}` - Current queue depth
     - `qq_hermes_context_messages{group_id}` - Context cache size

2. **Integration points**:
   - Replace/augment `runtime_stat()` calls with Prometheus metrics
   - Keep JSONL logging for detailed debugging (dual output)
   - Add `/metrics` route to FastAPI app

3. **Configuration**:
   - `PROMETHEUS_ENABLED` (default: true)
   - `PROMETHEUS_INCLUDE_GROUP_ID_LABEL` (default: false, privacy consideration)

## Acceptance Criteria

- [ ] bridge.py reduced to <500 lines
- [ ] Config extracted to `qq_hermes_bridge/config.py` with typed interface
- [ ] FastAPI app and routes in `qq_hermes_bridge/app.py`
- [ ] All 338 existing tests pass
- [ ] `/metrics` endpoint returns Prometheus format
- [ ] Core metrics captured (messages, replies, duration, queue size)
- [ ] Both JSONL and Prometheus metrics work simultaneously
- [ ] No breaking changes to existing deployment (systemd service still works)
- [ ] Documentation updated (README.md section on metrics)

## Definition of Done

- Tests added/updated (unit tests for new modules, integration test for /metrics)
- Lint / typecheck / CI green (`python -m py_compile`)
- Docs updated (README.md Prometheus section, CLAUDE.md updated)
- Rollout plan: backward compatible, can deploy incrementally

## Out of Scope (Explicit)

- Grafana dashboards (future enhancement)
- Alerting rules (future enhancement)
- Metrics for self-learning system (can add later)
- Rewriting existing `qq_hermes_bridge/*` modules
- Changing `.env` format or config loading mechanism
- Adding new features beyond observability

## Technical Notes

### Files to Create
- `qq_hermes_bridge/config.py` - Config centralization
- `qq_hermes_bridge/app.py` - FastAPI app factory
- `qq_hermes_bridge/metrics.py` - Prometheus metrics definitions

### Files to Modify
- `bridge.py` - Slim down to entry point
- `qq_hermes_bridge/runtime_stats.py` - Add Prometheus integration points
- `README.md` - Add Prometheus documentation section
- `CLAUDE.md` - Update project conventions

### Dependencies to Add
- `prometheus-client` (standard Python Prometheus library)

### Testing Strategy
- Unit tests for config module (validate parsing)
- Integration test for `/metrics` endpoint (verify format)
- Regression: all existing tests must pass
- Manual: verify systemd service restart works

## Technical Approach

### Phase 1: Extract Configuration (Low Risk)

**Step 1a: Create config module**
- Extract all 100+ config vars from bridge.py lines 43-263 to `qq_hermes_bridge/config.py`
- Provide `Config` dataclass with typed fields
- Add `load_config()` function that returns Config instance
- bridge.py imports and uses: `config = load_config()`

**Step 1b: Create app factory**
- Move FastAPI app creation + routes to `qq_hermes_bridge/app.py`
- Function signature: `create_app(config: Config) -> FastAPI`
- Includes all 4 routes: `/health`, `/onebot`, `/test`, `/metrics` (stub for Phase 2)
- bridge.py becomes: load config → create app → pass to uvicorn

**Step 1c: Extract metrics helpers**
- Move bridge.py runtime stat functions to `qq_hermes_bridge/metrics.py`
- Keep JSONL logging working as-is
- Add stubs for Prometheus integration

**Result**: bridge.py reduces from 3485 to ~200 lines (just glue code)

### Phase 2: Add Prometheus Metrics (Medium Risk)

**Step 2a: Install prometheus-client**
- Add to project dependencies (no requirements.txt found, will document manual install)
- Standard Python library: `prometheus-client`

**Step 2b: Define metrics in metrics.py**
- Counter/Histogram/Gauge definitions
- Increment functions that mirror existing `runtime_stat()` calls
- Dual output: both Prometheus and JSONL

**Step 2c: Instrument existing code**
- Add metric increments to key points in bridge.py
- Preserve existing `runtime_stat()` calls for debugging
- No changes to worker logic, just add metrics

**Step 2d: Add /metrics endpoint**
- FastAPI route in `app.py`
- Returns `prometheus_client.generate_latest()`
- Format: standard Prometheus exposition format

### Implementation Order (Small PRs)

**PR1: Config extraction** (Scaffolding)
- Create `qq_hermes_bridge/config.py`
- Move config loading, keep bridge.py working
- Tests: config parsing correctness
- Risk: Low (pure refactor)

**PR2: App factory** (Core refactor)
- Create `qq_hermes_bridge/app.py`
- Move routes and workers
- Slim bridge.py to entry point
- Tests: existing tests should pass as-is
- Risk: Medium (routing changes)

**PR3: Prometheus metrics** (New feature)
- Install prometheus-client
- Create metrics in `metrics.py`
- Add `/metrics` endpoint
- Instrument key paths
- Tests: metrics endpoint format test
- Risk: Low (additive only)

**PR4: Documentation** (Cleanup)
- Update README.md with Prometheus section
- Update CLAUDE.md conventions
- Add deployment notes

## Decision (ADR-lite)

**Context**: bridge.py has grown to 3485 lines mixing concerns (config, routing, workers, utilities). No production metrics exist beyond JSONL logs.

**Decision**: 
1. Extract config → **flat dataclass** with typed interface (100+ fields, one-to-one mapping from globals)
2. Extract app → factory pattern for testability
3. Add Prometheus → standard `/metrics` endpoint, dual output with JSONL

**Rationale for flat config**:
- Project is a single-instance group chatbot, not multi-tenant
- Current code uses flat globals already (low migration risk)
- Simple one-to-one replacement (HERMES_BIN → config.hermes_bin)
- Can refactor to grouped config later if needed

**Consequences**:
- **Pros**: Better maintainability, production-grade observability, easier testing, low refactor risk
- **Cons**: Large dataclass (100+ fields), more files to navigate
- **Mitigations**: Keep backward compatibility, preserve existing tests, document clearly

## Open Questions

None currently - ready to proceed after confirmation.

## Research References

(None needed - using established patterns)
