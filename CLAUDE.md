# qq-hermes Claude Notes

- `./venv/bin/python -m pytest tests -q` - full regression suite; recent prompt changes passed with 331 tests.
- `./venv/bin/python -m py_compile bridge.py qq_hermes_bridge/*.py` - quick syntax check before prompt/bridge commits.
- Prompt changes - keep direct/proactive PromptService changes scoped and commit each key improvement separately.
- Proactive prompt - keep `<SILENT>` appearing exactly once in the rendered prompt.
- Prompt diagnostics - bridge logs section metadata only; never log full prompt text.
- `/home/roxy/.hermes/config.yaml` - local secret config; do not print or commit.
- `.codegraph/` - local codegraph index; ignore and do not commit.
- `docs/superpowers/specs/.~lock.*` - editor lock files; ignore and do not commit.
- Git workflow - feature branches merge to main with `--no-ff` for clear history.
- Root `bridge.py` is a thin compatibility shim that execs `qq_hermes_bridge/runtime.py`; keep runtime changes in `runtime.py` while preserving `bridge:app` imports and legacy monkeypatchable globals.
- Metrics - `qq_hermes_bridge/metrics.py` is dependency-free and content-safe; `/metrics` omits `group_id` labels by default unless `PROMETHEUS_INCLUDE_GROUP_ID_LABEL=true`.
- Hermes CLI warnings - `strip_cli_warning_lines()` removes "Warning: Unknown toolsets:" from stdout.
- XML cleanup - process matched tag pairs first, then standalone tags; avoid removing content between unrelated tags.
- Test file creation - use Bash heredoc for complex multi-line strings with special chars instead of inline Python.
