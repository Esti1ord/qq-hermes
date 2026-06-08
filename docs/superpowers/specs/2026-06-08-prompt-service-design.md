# PromptService 第一阶段设计

## Context

qq-hermes 已经从单文件 bridge 脚本演进成一个本地 QQ 群聊天机器人应用。当前 direct/proactive prompt 仍主要由 `qq_hermes_bridge/commands.py` 中的大段 f-string 构造，`bridge.py` 负责收集上下文、资料、OCR、自学习提示和 persona 后一次性传入。

这种方式现在可用，但继续扩展会遇到两个问题：

1. prompt 中的信息来源、优先级和使用说明只靠自然语言段落表达，后续调整容易散落在大段模板里；
2. 想继续优化上下文权重、旧摘要降权、OCR/自学习使用方式、proactive 接话判断时，缺少一个清晰的 prompt 编排层。

本阶段目标是抽出一个完整但低风险的 PromptService 对象模型，只接管 direct/proactive 两条主链路。Hermes 仍接收普通字符串，`bridge.py` 现有入口和运行行为保持兼容。

用户已明确：当前接入群成员是现实可信朋友，因此公网权限、安全边界、严格访问控制类优化暂时搁置。本设计中的 `source`/`priority` metadata 主要用于功能质量、上下文权重和后续架构演进，不以防御恶意群友为第一目标。

## Goals

- 新增 `qq_hermes_bridge/prompt_service.py`，作为 direct/proactive prompt 的编排层。
- 引入完整对象模型：`PromptSection`、`PromptRequest`、`RenderedPrompt`。
- 让 prompt 信息来源和优先级显式化，例如当前消息、最近上下文、旧摘要、OCR、自学习、人设。
- 保持现有 `commands.build_chat_prompt()` 和 `commands.build_proactive_prompt()` 函数签名作为兼容 wrapper。
- 不改变 Hermes CLI 调用方式、session 策略、context persistence、search/deepseek 行为。
- 增加单元测试，验证 section 顺序、metadata、关键规则和 wrapper 兼容性。

## Non-goals

本阶段不做：

- `/search` 或 `/deepseek` prompt 迁移；
- summary age/source metadata 持久化；
- PromptService class 化或依赖注入；
- BridgeConfig / BridgeState 抽取；
- ContextService 或 LLMClient 抽取；
- 权限、安全默认值、`/context` 访问控制；
- OCR fetch、self-learning 存储、Hermes session 策略调整；
- proactive 阈值/档位调优。

## Object Model

### `PromptSection`

```python
@dataclass(frozen=True)
class PromptSection:
    key: str
    title: str
    body: str
    source: Literal[
        "runtime_policy",
        "current_message",
        "recent_context",
        "quoted_context",
        "generated_summary",
        "media_recognition",
        "group_profile",
        "self_learning",
        "persona",
        "internal_diagnostic",
    ]
    priority: Literal["critical", "high", "medium", "low"]
    instruction: str = ""
```

Purpose:

- `key` is stable and testable.
- `title` is human-readable in the rendered prompt.
- `body` is the content.
- `source` describes where the content came from.
- `priority` describes how strongly the model should use it.
- `instruction` is optional section-specific guidance.

### `PromptRequest`

```python
@dataclass(frozen=True)
class PromptRequest:
    kind: Literal["direct", "proactive"]
    group_id: int | None
    date_context: str
    sections: list[PromptSection]
    rules: list[str]
    output_contract: str
    max_prompt_chars: int | None = None
```

Purpose:

- Represents one prompt construction task.
- Keeps rules and output contract separate from data sections.
- Enables later budget/cropping/debug support without changing call sites.

### `RenderedPrompt`

```python
@dataclass(frozen=True)
class RenderedPrompt:
    text: str
    section_keys: tuple[str, ...]
    char_count: int
```

Purpose:

- Returns the final Hermes-compatible text.
- Exposes section order for tests and future diagnostics.
- Captures rendered length for later budget work.

## Public API

`qq_hermes_bridge/prompt_service.py` should expose:

```python
def render_prompt(request: PromptRequest) -> RenderedPrompt:
    """Render a PromptRequest into Hermes-compatible text."""

def build_direct_prompt_request(**prompt_parts: object) -> PromptRequest:
    """Build a direct PromptRequest from the current direct prompt inputs."""

def build_proactive_prompt_request(**prompt_parts: object) -> PromptRequest:
    """Build a proactive PromptRequest from the current proactive prompt inputs."""

def build_chat_prompt(**prompt_parts: object) -> str:
    """Compatibility string builder for direct chat prompts."""

def build_proactive_prompt(**prompt_parts: object) -> str:
    """Compatibility string builder for proactive prompts."""
```

`commands.py` keeps its existing public functions but delegates:

```python
from . import prompt_service


def build_chat_prompt(**prompt_parts: object) -> str:
    return prompt_service.build_chat_prompt(**prompt_parts)


def build_proactive_prompt(**prompt_parts: object) -> str:
    return prompt_service.build_proactive_prompt(**prompt_parts)
```

This keeps `bridge.py` and existing tests stable while moving prompt ownership to the new module.

## Rendering Format

Use a deterministic, readable format:

```text
<intro>

## <title>
来源：<source>
优先级：<priority>
使用说明：<instruction>   # omitted if empty
<body>

## 规则
- 第一条规则
- 第二条规则

## 输出要求
<output_contract>
```

The exact Chinese wording may match existing prompt style, but the important part is stable section titles/metadata.

## Direct Prompt Sections

Build direct prompts in this order:

1. `runtime_date`
   - source: `runtime_policy`
   - priority: `high`
2. `summary_context`
   - source: `generated_summary`
   - priority: `low`
3. `recent_context`
   - source: `recent_context`
   - priority: `high`
4. `quoted_context`
   - source: `quoted_context`
   - priority: `high`
5. `current_message`
   - source: `current_message`
   - priority: `critical`
6. `media_context`
   - source: `media_recognition`
   - priority: `medium`
7. `sender_profile`
   - source: `group_profile`
   - priority: `medium`
8. `mentioned_profiles`
   - source: `group_profile`
   - priority: `medium`
9. `related_profiles`
   - source: `group_profile`
   - priority: `low`
10. `self_learning`
    - source: `self_learning`
    - priority: `low`
11. `persona`
    - source: `persona`
    - priority: `medium`

Direct rules should preserve current behavior:

- current message and quoted message are the task;
- recent context is for deixis, tone, and continuity;
- summaries and old background are not topics to force back;
- profile/self-learning/persona are weak or soft constraints;
- do not repeat pending bot replies;
- image recognition is auxiliary and may be wrong;
- ordinary chat should not claim live web search;
- concise Chinese group-chat style;
- no system/config/token/path leakage.

Direct output contract remains: only output the group message body.

## Proactive Prompt Sections

Build proactive prompts in this order:

1. `runtime_date`
   - source: `runtime_policy`
   - priority: `high`
2. `summary_context`
   - source: `generated_summary`
   - priority: `low`
3. `recent_context`
   - source: `recent_context`
   - priority: `critical`
4. `trigger_reasons`
   - source: `internal_diagnostic`
   - priority: `low`
5. `persona`
   - source: `persona`
   - priority: `medium`

Proactive rules should preserve current behavior:

- trigger reasons are diagnostics, not required topics;
- recent high-weight human messages decide whether there is a natural entry point;
- old summaries do not pull back past topics;
- if the bot would repeat old wording or old jokes, stay silent;
- if inappropriate or no natural line, stay silent without explanation;
- if suitable, output one short natural group-chat line;
- no fake live search claims;
- no links or internal details;
- no fabricated real-world identity/location/experience.

Proactive output contract remains: if not speaking, output exactly `<SILENT>`.

`<SILENT>` should appear once in the proactive prompt, in the output contract.

## Compatibility Strategy

- `bridge.py::build_prompt()` continues calling `commands.build_chat_prompt()`.
- `bridge.py::build_proactive_prompt()` continues calling `commands.build_proactive_prompt()`.
- Existing function signatures in `commands.py` remain stable.
- New tests should target `prompt_service.py` directly, while existing integration tests keep covering `bridge.py` wrappers.
- No persisted data changes are introduced.
- No runtime side-effect changes are introduced.

## Testing Plan

Add `tests/test_prompt_service_module.py` covering:

1. `render_prompt()` preserves section order and exposes `section_keys`.
2. Direct prompt request contains expected section keys and metadata.
3. Direct rendered prompt marks:
   - current message as `critical`;
   - recent context as `high`;
   - summary/self-learning as `low`;
   - persona as `medium`.
4. Proactive prompt request marks:
   - recent context as `critical`;
   - summary as `low`;
   - trigger reasons as `internal_diagnostic` and `low`.
5. Proactive rendered prompt includes `<SILENT>` once and does not contain `空输出是正确的`.
6. `commands.build_chat_prompt()` output matches `prompt_service.build_chat_prompt()` for the same inputs.
7. `commands.build_proactive_prompt()` output matches `prompt_service.build_proactive_prompt()` for the same inputs.

Run focused tests:

```bash
./venv/bin/python -m pytest tests/test_prompt_service_module.py tests/test_proactive_speaking.py tests/test_context.py -q
```

Run full tests:

```bash
./venv/bin/python -m pytest tests -q
```

Also run:

```bash
./venv/bin/python -m py_compile qq_hermes_bridge/prompt_service.py qq_hermes_bridge/commands.py bridge.py
git diff --check
```

## Implementation Steps

1. Create `qq_hermes_bridge/prompt_service.py` with dataclasses and renderer.
2. Move direct prompt construction logic from `commands.build_chat_prompt()` into `prompt_service.build_chat_prompt()` via a `PromptRequest` builder.
3. Move proactive prompt construction logic from `commands.build_proactive_prompt()` into `prompt_service.build_proactive_prompt()` via a `PromptRequest` builder.
4. Turn `commands.py` direct/proactive prompt functions into compatibility wrappers.
5. Add `tests/test_prompt_service_module.py`.
6. Update existing prompt assertions only if wording changes while preserving behavior.
7. Run focused and full verification.

## Future Phases

After this phase is stable, follow-up phases can handle:

- `/search` and `/deepseek` prompt migration;
- summary age/source metadata;
- prompt length budget and section-level truncation;
- PromptService as an injectable class;
- ContextService and BridgeState;
- LLMClient/HermesCliClient abstraction;
- proactive behavior levels and group-specific persona tuning.
