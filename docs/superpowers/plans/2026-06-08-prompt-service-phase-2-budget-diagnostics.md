# PromptService Phase 2 Budget Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add section-level character budgets and render diagnostics to PromptService while preserving existing direct/proactive string builder compatibility.

**Architecture:** Extend `RenderedPrompt` with immutable per-section diagnostics and keep `PromptRequest` unchanged. Apply default budgets inside `render_prompt()` based on prompt kind and section key, truncating only section body text while preserving section metadata, rules, and output contracts.

**Tech Stack:** Python 3.11+, dataclasses, pytest, existing `qq_hermes_bridge.prompt_service` module.

---

## Files

- Modify: `qq_hermes_bridge/prompt_service.py`
  - Add `RenderedSection`, budget constants, truncation helpers, and diagnostics-aware rendering.
- Modify: `tests/test_prompt_service_module.py`
  - Add tests for diagnostics and truncation behavior.

Do not modify:

- `bridge.py`
- `qq_hermes_bridge/commands.py` unless a compatibility test proves a wrapper defect
- removed search command modules
- context persistence modules
- `qq_hermes_bridge/jrrp.py`

Do not commit:

- `.codegraph/`
- `docs/superpowers/specs/.~lock.2026-06-08-prompt-service-design.md#`

---

### Task 1: Add diagnostics model and truncation helpers

**Files:**
- Modify: `qq_hermes_bridge/prompt_service.py`
- Modify: `tests/test_prompt_service_module.py`

- [ ] **Step 1: Add failing tests for diagnostics and helper behavior**

Append tests to `tests/test_prompt_service_module.py`:

```python

def rendered_section_by_key(rendered, key):
    return next(section for section in rendered.sections if section.key == key)


def test_render_prompt_exposes_section_diagnostics_without_truncation():
    request = prompt_service.build_direct_prompt_request(**DIRECT_PROMPT_KWARGS)

    rendered = prompt_service.render_prompt(request)

    assert len(rendered.sections) == len(request.sections)
    assert rendered.section_keys == tuple(section.key for section in request.sections)
    current = rendered_section_by_key(rendered, "current_message")
    current_request = next(section for section in request.sections if section.key == "current_message")
    assert current.key == "current_message"
    assert current.source == "current_message"
    assert current.priority == "critical"
    assert current.original_char_count == len(current_request.body.strip())
    assert current.rendered_char_count == current.original_char_count
    assert current.budget_chars is None
    assert current.truncated is False


def test_truncate_text_respects_budget_and_marks_truncation():
    rendered, truncated = prompt_service._truncate_text("abcdef", 5)

    assert truncated is True
    assert len(rendered) == 5

    rendered, truncated = prompt_service._truncate_text("abcdef", 20)

    assert rendered == "abcdef"
    assert truncated is False
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```bash
./venv/bin/python -m pytest \
  tests/test_prompt_service_module.py::test_render_prompt_exposes_section_diagnostics_without_truncation \
  tests/test_prompt_service_module.py::test_truncate_text_respects_budget_and_marks_truncation \
  -q
```

Expected: fail because `RenderedPrompt.sections` and `_truncate_text()` do not exist yet.

- [ ] **Step 3: Implement dataclass, constants, helpers, and diagnostics collection**

In `qq_hermes_bridge/prompt_service.py`:

- Add after `PromptRequest`:

```python
@dataclass(frozen=True)
class RenderedSection:
    key: str
    source: PromptSource
    priority: PromptPriority
    original_char_count: int
    rendered_char_count: int
    budget_chars: int | None
    truncated: bool
```

- Change `RenderedPrompt` to:

```python
@dataclass(frozen=True)
class RenderedPrompt:
    text: str
    section_keys: tuple[str, ...]
    char_count: int
    sections: tuple[RenderedSection, ...] = ()
```

- Add constants before `render_prompt()`:

```python
TRUNCATION_SUFFIX = "\n……（本 section 因长度限制已截断）"

DIRECT_SECTION_BUDGETS = {
    "runtime_date": 200,
    "summary_context": 1000,
    "recent_context": 4000,
    "quoted_context": 1600,
    "current_message": None,
    "media_context": 1600,
    "sender_profile": 1200,
    "mentioned_profiles": 1200,
    "related_profiles": 800,
    "self_learning": 800,
    "persona": 1600,
}

PROACTIVE_SECTION_BUDGETS = {
    "runtime_date": 200,
    "summary_context": 600,
    "recent_context": 3500,
    "trigger_reasons": 300,
    "persona": 1200,
}

PRIORITY_FALLBACK_BUDGETS = {
    "critical": None,
    "high": 2400,
    "medium": 1200,
    "low": 800,
}
```

- Add helpers:

```python
def _budget_for_section(kind: PromptKind, section: PromptSection) -> int | None:
    budgets = DIRECT_SECTION_BUDGETS if kind == "direct" else PROACTIVE_SECTION_BUDGETS
    if section.key in budgets:
        return budgets[section.key]
    return PRIORITY_FALLBACK_BUDGETS[section.priority]


def _truncate_text(text: str, budget_chars: int | None) -> tuple[str, bool]:
    if budget_chars is None or len(text) <= budget_chars:
        return text, False
    if budget_chars <= len(TRUNCATION_SUFFIX):
        return TRUNCATION_SUFFIX[:budget_chars], True
    keep = budget_chars - len(TRUNCATION_SUFFIX)
    return f"{text[:keep]}{TRUNCATION_SUFFIX}", True
```

- Update `render_prompt()` loop to use `_budget_for_section()` and `_truncate_text()`, append `RenderedSection`, and return `RenderedPrompt(..., sections=tuple(diagnostics))`.

- [ ] **Step 4: Run focused diagnostics tests**

Run:

```bash
./venv/bin/python -m pytest \
  tests/test_prompt_service_module.py::test_render_prompt_exposes_section_diagnostics_without_truncation \
  tests/test_prompt_service_module.py::test_truncate_text_respects_budget_and_marks_truncation \
  -q
```

Expected: pass.

- [ ] **Step 5: Commit Task 1**

Run:

```bash
git add qq_hermes_bridge/prompt_service.py tests/test_prompt_service_module.py
git commit -m "Add PromptService render diagnostics"
```

---

### Task 2: Add section budget truncation tests

**Files:**
- Modify: `tests/test_prompt_service_module.py`
- Modify: `qq_hermes_bridge/prompt_service.py` only if tests expose a defect.

- [ ] **Step 1: Add failing/passing behavior tests for direct and proactive budgets**

Append tests to `tests/test_prompt_service_module.py`:

```python

def test_direct_low_priority_sections_are_truncated_but_current_message_is_not():
    kwargs = dict(DIRECT_PROMPT_KWARGS)
    kwargs["context_summaries"] = "摘" * 1500
    kwargs["learning_context"] = "学" * 1200
    kwargs["user_text"] = "问" * 3600
    kwargs["max_prompt_chars"] = 3500
    request = prompt_service.build_direct_prompt_request(**kwargs)

    rendered = prompt_service.render_prompt(request)

    summary = rendered_section_by_key(rendered, "summary_context")
    learning = rendered_section_by_key(rendered, "self_learning")
    current = rendered_section_by_key(rendered, "current_message")
    assert summary.budget_chars == 1000
    assert summary.truncated is True
    assert summary.rendered_char_count == 1000
    assert learning.budget_chars == 800
    assert learning.truncated is True
    assert learning.rendered_char_count == 800
    assert current.budget_chars is None
    assert current.truncated is False
    assert prompt_service.TRUNCATION_SUFFIX in rendered.text


def test_proactive_summary_budget_is_smaller_than_direct_summary_budget():
    long_summary = "摘" * 1500
    direct_kwargs = dict(DIRECT_PROMPT_KWARGS)
    direct_kwargs["context_summaries"] = long_summary
    proactive_kwargs = dict(PROACTIVE_PROMPT_KWARGS)
    proactive_kwargs["context_summaries"] = long_summary

    direct = prompt_service.render_prompt(prompt_service.build_direct_prompt_request(**direct_kwargs))
    proactive = prompt_service.render_prompt(prompt_service.build_proactive_prompt_request(**proactive_kwargs))

    direct_summary = rendered_section_by_key(direct, "summary_context")
    proactive_summary = rendered_section_by_key(proactive, "summary_context")
    assert direct_summary.budget_chars == 1000
    assert proactive_summary.budget_chars == 600
    assert direct_summary.rendered_char_count == 1000
    assert proactive_summary.rendered_char_count == 600


def test_proactive_prompt_keeps_silent_contract_once_when_sections_truncate():
    kwargs = dict(PROACTIVE_PROMPT_KWARGS)
    kwargs["context_summaries"] = "摘" * 1000
    kwargs["recent_context"] = "近" * 5000
    kwargs["persona"] = "人" * 2000

    prompt = prompt_service.build_proactive_prompt(**kwargs)

    assert prompt.count("<SILENT>") == 1
    assert prompt_service.TRUNCATION_SUFFIX in prompt
    assert "空输出是正确的" not in prompt
```

- [ ] **Step 2: Run new budget tests**

Run:

```bash
./venv/bin/python -m pytest \
  tests/test_prompt_service_module.py::test_direct_low_priority_sections_are_truncated_but_current_message_is_not \
  tests/test_prompt_service_module.py::test_proactive_summary_budget_is_smaller_than_direct_summary_budget \
  tests/test_prompt_service_module.py::test_proactive_prompt_keeps_silent_contract_once_when_sections_truncate \
  -q
```

Expected: pass if Task 1 implementation is correct; otherwise fix `prompt_service.py` minimally.

- [ ] **Step 3: Run all PromptService tests**

Run:

```bash
./venv/bin/python -m pytest tests/test_prompt_service_module.py -q
```

Expected: all tests pass.

- [ ] **Step 4: Commit Task 2**

Run:

```bash
git add qq_hermes_bridge/prompt_service.py tests/test_prompt_service_module.py
git commit -m "Add PromptService section budget tests"
```

Skip the commit if Task 2 only added tests and Task 1 commit already included them because the implementation worker batched work intentionally; otherwise keep tasks separated.

---

### Task 3: Verify full Phase 2 behavior

**Files:**
- Test only unless verification reveals a defect in planned files.

- [ ] **Step 1: Compile changed modules**

Run:

```bash
./venv/bin/python -m py_compile qq_hermes_bridge/prompt_service.py qq_hermes_bridge/commands.py bridge.py
```

Expected: no output.

- [ ] **Step 2: Run focused tests**

Run:

```bash
GROUP_IDS=975805598,781423661 ./venv/bin/python -m pytest tests/test_prompt_service_module.py tests/test_proactive_speaking.py tests/test_context.py -q
```

Expected: all pass.

- [ ] **Step 3: Run full suite**

Run:

```bash
GROUP_IDS=975805598,781423661 ./venv/bin/python -m pytest tests -q
```

Expected: all pass.

- [ ] **Step 4: Check diff whitespace and status**

Run:

```bash
git diff --check
git status --short
```

Expected: no whitespace errors. Only planned files should be modified/staged. `.codegraph/` and lock file may remain untracked but must not be staged.

- [ ] **Step 5: Commit final stabilization if needed**

If verification required additional planned-file fixes, commit them:

```bash
git add qq_hermes_bridge/prompt_service.py tests/test_prompt_service_module.py
git commit -m "Stabilize PromptService section budgets"
```

Skip if no additional changes.
