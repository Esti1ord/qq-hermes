# README / env alignment audit

## Scope

Audit README and `.env.example` alignment for completed reply-speed improvements: direct burst coalescing, direct fast/strong model routing, safe defaults, rollback, and content-safety.

## Findings

- README already documents `DIRECT_COALESCE_WINDOW_MS=0`, default-off behavior, same-sender direct burst coalescing, and rollback to `0`.
- README documents direct fast-lane knobs but under-specifies `DIRECT_STRONG_MODEL_ALIAS`: implemented behavior limits it to reply-to-bot and media/OCR direct intents, model-only, preserving provider/session/fallback behavior.
- `.env.example` already has direct model/transport knobs under text routing and `DIRECT_COALESCE_WINDOW_MS` under prompt/reply behavior.
- `.env.example` comments should clarify:
  - strong-lane boundaries: reply-to-bot and direct media/OCR only;
  - coalescing only merges pending same-group/same-sender/same-route ordinary text direct intents;
  - empty/zero values inherit normal direct routing.
- Existing dirty README / `.env.example` include broad documentation organization WIP. Stage only focused hunks for this task.

## Content safety notes

- Keep examples generic and avoid real provider URLs, API keys, raw chat, prompt text, OCR text, image URLs, or model output.
- API-key env-name fields are allowed as configuration keys, but README prose should avoid exposing local secret env names from a real machine.

## Recommended edits

- README: expand the direct fast/strong paragraph to state exact strong triggers and model-only preservation contract.
- README: expand direct coalescing paragraph with safe merge boundaries and operational rollback.
- `.env.example`: add comments near `DIRECT_STRONG_MODEL_ALIAS` and `DIRECT_COALESCE_WINDOW_MS` documenting the same boundaries.
