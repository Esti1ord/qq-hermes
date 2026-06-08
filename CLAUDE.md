# qq-hermes Claude Notes

- `./venv/bin/python -m pytest tests -q` - full regression suite; recent prompt changes passed with 331 tests.
- `./venv/bin/python -m py_compile bridge.py qq_hermes_bridge/*.py` - quick syntax check before prompt/bridge commits.
- Prompt changes - keep direct/proactive PromptService changes scoped and commit each key improvement separately.
- Proactive prompt - keep `<SILENT>` appearing exactly once in the rendered prompt.
- Prompt diagnostics - bridge logs section metadata only; never log full prompt text.
- `/home/roxy/.hermes/config.yaml` - local secret config; do not print or commit.
- `.codegraph/` - local codegraph index; ignore and do not commit.
- `docs/superpowers/specs/.~lock.*` - editor lock files; ignore and do not commit.
