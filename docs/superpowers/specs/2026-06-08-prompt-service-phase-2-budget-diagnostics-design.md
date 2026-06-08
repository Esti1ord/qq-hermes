# PromptService 第二阶段设计：Section Budget 与渲染诊断

## Context

PromptService 第一阶段已经把 direct/proactive prompt 从 `commands.py` 的大段 f-string 中抽出，形成了 `PromptSection`、`PromptRequest`、`RenderedPrompt` 和 deterministic renderer。当前 prompt 已经显式表达 section 的 `source`、`priority` 和 `instruction`，但还没有真正利用这些 metadata 做上下文预算、裁剪和诊断。

继续优化 prompt 的核心问题不是继续堆规则，而是防止低权重信息挤占高权重信息：旧摘要、自学习、相关资料或 persona 过长时，可能让模型被历史话题带偏；proactive 场景尤其容易被旧上下文、触发原因或旧梗牵引，导致不自然插话。

本阶段目标是在保持桥接层调用方式不变的前提下，为 PromptService 增加 section-level budget 和 render diagnostics。Hermes 仍接收普通字符串；`commands.build_chat_prompt()` / `commands.build_proactive_prompt()` 仍返回字符串；新增诊断信息主要供测试和后续 debug 使用。

## Goals

- 为每个 rendered section 记录诊断信息：原始长度、渲染长度、是否裁剪、使用的预算。
- 在 `render_prompt()` 内部按 prompt kind 和 section key 应用默认 section budget。
- 保护高优先级内容：当前消息、引用消息、最近上下文不被低权重内容挤掉。
- 对低权重内容做保守裁剪：旧摘要、相关资料、自学习、触发原因优先缩短。
- 保持 direct/proactive 现有 builder 和 `commands.py` wrapper 调用方式兼容。
- 保持 proactive prompt 中 `<SILENT>` 只出现一次。
- 增加单元测试，验证裁剪、诊断、section 顺序、兼容 wrapper 和关键 prompt 行为。

## Non-goals

本阶段不做：

- 不迁移 `/search` 或 `/deepseek` prompt。
- 不改 `bridge.py` 的上下文收集逻辑。
- 不改 Hermes CLI 调用、session 策略或队列策略。
- 不改 context persistence、summary 生成或 self-learning 存储格式。
- 不引入 group-specific 配置文件或运行时调参 UI。
- 不做 tokenizer-level token budget，只使用字符数预算。
- 不把 PromptService class 化或引入依赖注入。
- 不新增外部日志输出；诊断信息先留在 `RenderedPrompt` 对象中供测试和后续调用。
- 不处理权限/安全边界类问题。

## Design Overview

本阶段采用最小 API 扩展：

1. 新增 `RenderedSection` dataclass，记录每个 section 的裁剪诊断。
2. 扩展 `RenderedPrompt`，增加 `sections: tuple[RenderedSection, ...] = ()`。
3. 在 `render_prompt()` 内部根据 `request.kind` 和 section key 选择默认 budget。
4. 对 section body 做字符级裁剪，并在正文尾部加入简短裁剪提示。
5. `build_chat_prompt()` 和 `build_proactive_prompt()` 仍返回字符串，不暴露诊断给 bridge。
6. 测试直接调用 request builder + `render_prompt()` 检查 diagnostics。

这个方案保持低风险：调用方无需改变，PromptService 内部开始真正利用第一阶段的 `key/source/priority` metadata。

## Object Model Changes

### `RenderedSection`

新增：

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

Purpose:

- `key` 对应 `PromptSection.key`，稳定可测。
- `source` / `priority` 方便后续按来源或优先级分析 prompt 构成。
- `original_char_count` 是清理后 section body 的原始字符数。
- `rendered_char_count` 是实际进入 prompt 的 body 字符数。
- `budget_chars` 表示本次使用的预算；`None` 表示不裁剪。
- `truncated` 表示 body 是否被裁剪。

### `RenderedPrompt`

从：

```python
@dataclass(frozen=True)
class RenderedPrompt:
    text: str
    section_keys: tuple[str, ...]
    char_count: int
```

扩展为：

```python
@dataclass(frozen=True)
class RenderedPrompt:
    text: str
    section_keys: tuple[str, ...]
    char_count: int
    sections: tuple[RenderedSection, ...] = ()
```

Compatibility:

- 现有字段保持不变。
- 新字段有默认值，降低测试和调用兼容风险。
- `build_chat_prompt()` / `build_proactive_prompt()` 仍只返回 `.text`。

### `PromptRequest`

本阶段不新增公开字段。

原因：

- Phase 2 先使用模块内默认 budget，避免提前暴露配置面。
- 后续如果需要 group-specific budget，再考虑增加可选 `section_budgets` 或从配置层注入。
- 现有 `max_prompt_chars` 暂时保留，用于 direct 当前消息裁剪兼容；本阶段不改变其语义。

## Budget Policy

预算单位：Python 字符数，不是 tokenizer token。

原则：

- `None` 表示不裁剪。
- 预算只作用于 section body，不作用于标题、来源、优先级、使用说明、规则和输出要求。
- 裁剪后保留前部内容，并追加简短中文提示，避免模型误以为文本自然结束。
- 预算值包含裁剪提示本身。
- 如果预算小于裁剪提示长度，返回提示的截断版，保证不会超过预算。

### Direct Budget

```python
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
```

Rationale:

- `current_message` 已由 builder 使用 `max_prompt_chars` 裁剪，本阶段不再二次裁剪。
- `recent_context` 和 `quoted_context` 是 high priority，预算较高。
- `summary_context`、`related_profiles`、`self_learning` 是低权重，预算较低。
- `persona` 保持中等预算，避免人设过长压过当前任务。
- `media_context` 中等预算，承认 OCR/图片识别有用但可能误导。

### Proactive Budget

```python
PROACTIVE_SECTION_BUDGETS = {
    "runtime_date": 200,
    "summary_context": 600,
    "recent_context": 3500,
    "trigger_reasons": 300,
    "persona": 1200,
}
```

Rationale:

- proactive 的决策核心是最近高权重人类消息，所以 `recent_context` 预算最高。
- `summary_context` 只保留少量背景，避免旧话题把主动发言拉偏。
- `trigger_reasons` 是 internal diagnostic，不应该占大量内容，也不应成为回复主题。
- `persona` 控制语气，不应压过最近上下文。

### Fallback Budget

如果出现未知 section key：

```python
PRIORITY_FALLBACK_BUDGETS = {
    "critical": None,
    "high": 2400,
    "medium": 1200,
    "low": 800,
}
```

Rationale:

- 保证未来新增 section 时不会完全失控。
- `critical` 默认不裁剪，避免核心任务被破坏。
- `low` 默认较短，符合旧背景/辅助信息的权重定位。

## Truncation Format

裁剪格式：

```text
<前缀内容>
……（本 section 因长度限制已截断）
```

要求：

- 裁剪提示不包含 section key，避免污染自然语言 prompt 太多。
- 裁剪提示不应出现在未裁剪 section。
- 裁剪后文本长度不超过 budget。
- 空 body 仍渲染为 `（无）`，并计入 diagnostics。

示例：

```python
_trim_section_body("abcdef", 5)
# "ab……（" 或等价的不超过 5 字符的裁剪提示前缀
```

实际实现可以通过 helper 保证长度：

```python
TRUNCATION_SUFFIX = "\n……（本 section 因长度限制已截断）"


def _truncate_text(text: str, budget_chars: int | None) -> tuple[str, bool]:
    if budget_chars is None or len(text) <= budget_chars:
        return text, False
    if budget_chars <= len(TRUNCATION_SUFFIX):
        return TRUNCATION_SUFFIX[:budget_chars], True
    keep = budget_chars - len(TRUNCATION_SUFFIX)
    return f"{text[:keep]}{TRUNCATION_SUFFIX}", True
```

## Rendering Flow

`render_prompt()` flow becomes:

1. Create intro/header lines.
2. For each `PromptSection`:
   - clean body with `_clean_body()`;
   - resolve budget by request kind and section key;
   - truncate body if needed;
   - append section header/metadata/instruction/truncated body;
   - append `RenderedSection` diagnostic.
3. Append rules.
4. Append output contract.
5. Return `RenderedPrompt(text, section_keys, char_count, sections)`.

Example implementation shape:

```python
def render_prompt(request: PromptRequest) -> RenderedPrompt:
    diagnostics: list[RenderedSection] = []
    lines: list[str] = [
        "你正在为 QQ 群聊生成回复。请按各 section 的来源、优先级和使用说明判断权重。",
        f"类型：{request.kind}",
        f"群号：{request.group_id}",
        f"当前日期：{request.date_context}",
    ]

    for section in request.sections:
        clean_body = _clean_body(section.body)
        budget = _budget_for_section(request.kind, section)
        rendered_body, truncated = _truncate_text(clean_body, budget)
        diagnostics.append(RenderedSection(
            key=section.key,
            source=section.source,
            priority=section.priority,
            original_char_count=len(clean_body),
            rendered_char_count=len(rendered_body),
            budget_chars=budget,
            truncated=truncated,
        ))
        lines.extend([
            "",
            f"## {section.title}",
            f"来源：{section.source}",
            f"优先级：{section.priority}",
        ])
        if section.instruction:
            lines.append(f"使用说明：{section.instruction}")
        lines.append(rendered_body)

    if request.rules:
        lines.extend(["", "## 规则"])
        lines.extend(f"- {rule}" for rule in request.rules if str(rule or "").strip())

    lines.extend(["", "## 输出要求", _clean_body(request.output_contract)])
    text = "\n".join(lines)
    return RenderedPrompt(
        text=text,
        section_keys=tuple(section.key for section in request.sections),
        char_count=len(text),
        sections=tuple(diagnostics),
    )
```

## Public API Behavior

### `render_prompt()`

- Public return type gains diagnostics.
- Existing `text`, `section_keys`, `char_count` behavior remains.
- Applies section budgets by default.

### `build_chat_prompt()`

- Still returns `str`.
- Direct prompt may be shorter when low/medium sections are long.
- Current message remains protected by existing `max_prompt_chars` builder behavior.

### `build_proactive_prompt()`

- Still returns `str`.
- `<SILENT>` remains only in output contract.
- Long summaries/persona/reasons are cropped through section budgets.

## Testing Plan

Add/extend `tests/test_prompt_service_module.py`.

### 1. Renderer diagnostics for non-truncated sections

Verify:

- `RenderedPrompt.sections` has one item per section.
- `RenderedSection.key/source/priority` match original section.
- `original_char_count == rendered_char_count` when not truncated.
- `budget_chars` matches default budget or `None`.
- `truncated is False`.

### 2. Direct low-priority sections are truncated

Construct a direct request with a long `summary_context` and long `self_learning`.

Verify:

- `summary_context` diagnostic has `budget_chars == 1000` and `truncated is True`.
- `self_learning` diagnostic has `budget_chars == 800` and `truncated is True`.
- rendered prompt contains the truncation suffix.
- `current_message` remains untruncated.

### 3. Proactive summary is more aggressively truncated than direct summary

Construct direct and proactive requests with same long summary.

Verify:

- direct `summary_context.budget_chars == 1000`.
- proactive `summary_context.budget_chars == 600`.
- proactive rendered summary is shorter.

### 4. Proactive `<SILENT>` contract remains once

Use `build_proactive_prompt()` with long section bodies.

Verify:

- prompt contains `<SILENT>` exactly once.
- truncation suffix does not introduce `<SILENT>`.
- prompt does not contain `空输出是正确的`.

### 5. Commands wrappers remain compatible

Existing wrapper tests should continue passing:

- `commands.build_chat_prompt(...) == prompt_service.build_chat_prompt(...)`
- `commands.build_proactive_prompt(...) == prompt_service.build_proactive_prompt(...)`

### 6. Existing integration prompt tests remain green

Run:

```bash
GROUP_IDS=975805598,781423661 ./venv/bin/python -m pytest tests/test_prompt_service_module.py tests/test_proactive_speaking.py tests/test_context.py -q
```

Run full suite:

```bash
GROUP_IDS=975805598,781423661 ./venv/bin/python -m pytest tests -q
```

Compile:

```bash
./venv/bin/python -m py_compile qq_hermes_bridge/prompt_service.py qq_hermes_bridge/commands.py bridge.py
```

Check whitespace:

```bash
git diff --check
```

## Compatibility and Risk

### Compatibility

- `commands.py` wrappers do not change.
- `bridge.py` still receives strings and does not need to know about diagnostics.
- Existing code accessing `RenderedPrompt.text`, `.section_keys`, `.char_count` remains valid.
- New diagnostics are additive.

### Main Risk: over-truncation

Risk:

- A budget may cut useful context too aggressively.

Mitigation:

- Keep `recent_context`, `quoted_context`, and `current_message` protected.
- Start with conservative budgets rather than tiny budgets.
- Add tests for key protected sections.

### Main Risk: prompt wording regression

Risk:

- Existing tests expect specific prompt phrases.

Mitigation:

- Keep all section titles, rules, and output contracts unchanged.
- Truncate only body content.
- Run existing `test_proactive_speaking.py` and `test_context.py`.

### Main Risk: diagnostics accidentally mutate

Risk:

- `RenderedPrompt.sections` could expose mutable state.

Mitigation:

- Use `tuple[RenderedSection, ...]`.
- Keep `RenderedSection` frozen.

## Implementation Steps

1. Add `RenderedSection` dataclass and extend `RenderedPrompt`.
2. Add budget constants: `DIRECT_SECTION_BUDGETS`, `PROACTIVE_SECTION_BUDGETS`, `PRIORITY_FALLBACK_BUDGETS`, `TRUNCATION_SUFFIX`.
3. Add helpers:
   - `_budget_for_section(kind, section)`
   - `_truncate_text(text, budget_chars)`
4. Update `render_prompt()` to collect diagnostics and truncate section body only.
5. Add tests for diagnostics and truncation.
6. Run focused and full verification.

## Future Phases

After this phase, follow-ups can include:

- logging render diagnostics from `bridge.py` for selected debug modes;
- group-specific prompt budgets;
- summary age/source metadata;
- self-learning compaction into structured categories;
- ContextService extraction;
- proactive behavior levels and per-group persona tuning.
