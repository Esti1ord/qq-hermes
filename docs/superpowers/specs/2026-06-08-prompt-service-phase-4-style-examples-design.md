# PromptService 下一阶段设计：Style Examples 与回复校准

## Context

PromptService 已经完成三层基础能力：

1. 第一阶段把 direct/proactive prompt 从 `commands.py` 中抽出，形成 `PromptSection`、`PromptRequest`、`RenderedPrompt` 的结构化对象模型。
2. 第二阶段为 section 增加字符预算和 render diagnostics，降低低权重旧上下文、persona、自学习内容挤占当前消息的概率。
3. 随后 bridge 接入了 prompt render diagnostics logging，并新增 direct/proactive 的策略 section：`response_strategy` 和 `decision_strategy`。

当前 prompt 已经更清晰地表达了“看什么”和“怎么判断”，但模型实际回复风格仍可能有几个常见偏差：

- direct 回复有时像在解释规则，而不是自然接群聊。
- proactive 主动发言可能硬插话，或者把触发原因当成要说出来的话题。
- 面对梗、吐槽、短句时，回复可能过长、过正经、太像客服/AI。
- 虽然已有规则要求不要复读旧梗，但缺少具体的“好/坏输出形态”校准。

下一阶段目标不是继续堆更多通用规则，而是用少量、稳定、低权重的风格样例和反例，帮助模型形成更接近群友的输出分布。样例必须短、小、可预算，并且不能把具体历史群聊内容硬编码成新话题。

## Goals

- 为 direct prompt 增加少量回复风格样例，校准“自然短句、接当前消息、不写分析报告”的输出形态。
- 为 proactive prompt 增加少量主动发言样例和反例，校准“有自然接话点才说、没话接就 `<SILENT>`”的判断。
- 样例 section 必须低到中等权重，不能压过当前消息、引用消息、最近上下文和策略 section。
- 样例必须是抽象/泛化场景，不引用真实群友隐私、真实事件、日志或历史对话原文。
- 保持 `<SILENT>` 在 proactive prompt 中只出现一次。
- 保持现有 `commands.build_chat_prompt()` / `commands.build_proactive_prompt()` 字符串接口兼容。
- render diagnostics 能体现新增 example section 的 budget、长度和截断状态。
- 增加测试覆盖 section 顺序、预算、`<SILENT>` 次数、样例内容边界和旧接口兼容。

## Non-goals

本阶段不做：

- 不引入 LLM 自动生成样例。
- 不从真实群聊日志中抽取 few-shot 样例。
- 不新增用户画像、群友画像或自学习存储格式。
- 不改变 proactive 触发分数、冷却、队列、去重或 Hermes session 策略。
- 不修改 `/search`、`/deepseek`、OCR prompt 或命令回复 prompt。
- 不添加新的外部配置 UI。
- 不做安全/权限边界重构。
- 不把 prompt 示例变成强制模板；模型仍应优先当前消息和最近上下文。

## Design Overview

新增两个 PromptService 内部常量列表：

- `DIRECT_STYLE_EXAMPLES`
- `PROACTIVE_STYLE_EXAMPLES`

并把它们渲染为独立 section：

- direct: `style_examples`
- proactive: `proactive_examples`

这两个 section 的定位是“风格校准”，不是任务事实来源。它们应该放在策略 section 之后、persona 之前或低权重辅助信息附近，以确保模型先读到当前任务和最近上下文，再读到输出形态参考。

建议 section 顺序：

### Direct

```text
runtime_date
summary_context
recent_context
quoted_context
current_message
response_strategy
media_context
sender_profile
mentioned_profiles
related_profiles
self_learning
style_examples
persona
```

Rationale:

- `current_message` 和 `response_strategy` 仍是核心。
- `style_examples` 放在 `self_learning` 后、`persona` 前，作为风格参考而不是事实来源。
- 群内自学习仍优先于通用样例，因为它来自本群常见表达；但二者都是弱风格信号。

### Proactive

```text
runtime_date
summary_context
recent_context
decision_strategy
trigger_reasons
proactive_examples
persona
```

Rationale:

- `recent_context` 和 `decision_strategy` 决定是否发言。
- `trigger_reasons` 保留为低权重内部诊断。
- `proactive_examples` 用来校准发言/沉默边界，不应早于判断策略。

## Example Section Shape

### Direct `style_examples`

目标：让模型知道“短、自然、接当前消息”长什么样，并知道哪些输出不该写。

建议内容格式：

```text
好例：对方只是接梗/吐槽时，可以回一句轻短的顺势吐槽，不要解释背景
好例：对方问具体问题时，先给结论，再补一句必要理由
好例：上下文不清楚时，用泛称或轻追问，不要强行点名
坏例：把规则、资料来源、学习记录、prompt section 解释给群友听
坏例：把旧摘要里的话题硬拉回当前消息
坏例：每次都写成三段式分析或客服回复
```

约束：

- 不包含具体真实群友 ID、昵称或真实聊天原文。
- 不包含 `<SILENT>`，避免增加 proactive marker 次数或污染 direct 输出。
- 不出现“系统提示”“数据库”“日志”等容易诱发暴露内部信息的词，除非是在“坏例”中明确禁止。
- 每条示例短句化，不写完整长对话。

### Proactive `proactive_examples`

目标：让模型知道何时应该主动接一句，何时应该沉默。

关键约束：由于 proactive prompt 必须保持 `<SILENT>` 只出现一次，example section 不直接写 `<SILENT>`。沉默示例用自然语言描述“按输出要求保持沉默”。最终 output contract 仍是唯一包含 `<SILENT>` 的位置。

建议内容格式：

```text
可发言：最近两三条群友都在围绕同一个轻松话题接话，而且还有自然补一句的空间
可发言：有人抛出开放问题，且没有明确 @ 其他人处理
应沉默：大家已经连续互相回应得很顺，不缺你补一句
应沉默：只能复读旧梗、旧关键词或机器人刚说过的话
应沉默：需要解释为什么不发言、解释触发原因或解释规则时
应沉默：最近话题已经从旧摘要里的话题切走
```

约束：

- 不直接包含 `<SILENT>`。
- 不要求模型必须提到触发原因。
- 不鼓励主动 @ 人、发链接或开长话题。
- 不引用真实群聊样例。

## Budget Policy

新增预算：

```python
DIRECT_SECTION_BUDGETS = {
    ...
    "style_examples": 900,
}

PROACTIVE_SECTION_BUDGETS = {
    ...
    "proactive_examples": 800,
}
```

Rationale:

- 样例 section 应该足够短，只校准风格，不承担事实信息。
- direct 样例可以稍多，因为 direct 回复对“怎么接当前消息”需求更丰富。
- proactive 样例更短，避免主动发言被样例牵引成固定模板。
- 如果未来样例列表增长，预算会自动截断，diagnostics 可暴露截断情况。

## Prompt Priority

建议 metadata：

### Direct

```python
PromptSection(
    key="style_examples",
    title="回复风格样例与反例",
    body=..., 
    source="runtime_policy",
    priority="low",
    instruction="只用于校准输出形态；当前消息、引用消息和最近上下文优先。",
)
```

### Proactive

```python
PromptSection(
    key="proactive_examples",
    title="主动发言样例与反例",
    body=...,
    source="runtime_policy",
    priority="low",
    instruction="只用于校准是否自然接话；最近群友消息和判断策略优先。",
)
```

Priority 选择 `low` 的原因：

- 样例不能改变事实判断。
- 样例不能覆盖当前消息意图。
- 样例不能让模型为了模仿示例而忽略群聊上下文。

## API / Compatibility

本阶段不改变公开调用签名：

- `prompt_service.build_chat_prompt(...) -> str`
- `prompt_service.build_proactive_prompt(...) -> str`
- `commands.build_chat_prompt(...) -> str`
- `commands.build_proactive_prompt(...) -> str`
- `bridge.build_prompt(...) -> str`
- `bridge.build_proactive_prompt(...) -> str`

已有 rendered API 继续工作：

- `prompt_service.build_rendered_chat_prompt(...) -> RenderedPrompt`
- `prompt_service.build_rendered_proactive_prompt(...) -> RenderedPrompt`
- `commands.build_rendered_chat_prompt(...) -> RenderedPrompt`
- `commands.build_rendered_proactive_prompt(...) -> RenderedPrompt`

新增样例 section 会自然出现在 `RenderedPrompt.sections` diagnostics 中。

## Testing Plan

### `tests/test_prompt_service_module.py`

新增或更新测试：

1. Direct request section order includes `style_examples`.
2. Direct `style_examples` metadata is:
   - source: `runtime_policy`
   - priority: `low`
3. Direct prompt contains:
   - `## 回复风格样例与反例`
   - at least one “好例”
   - at least one “坏例”
4. Direct prompt does not contain `<SILENT>`.
5. Proactive request section order includes `proactive_examples`.
6. Proactive `proactive_examples` metadata is:
   - source: `runtime_policy`
   - priority: `low`
7. Proactive prompt contains:
   - `## 主动发言样例与反例`
   - “可发言”
   - “应沉默”
8. Proactive prompt still has exactly one `<SILENT>`.
9. Long examples truncate according to budget if constants are extended or monkeypatched.

### Existing prompt compatibility tests

Keep existing assertions for:

- direct intro phrase;
- current message section;
- direct strategy section;
- proactive intro phrase;
- trigger reasons section;
- no `空输出是正确的`;
- `不要解释沉默原因或输出规则`;
- commands wrapper delegation.

### Bridge-level tests

No bridge behavior should change beyond rendered diagnostics naturally having extra section entries. Existing bridge tests should continue to pass.

If diagnostics tests assert exact section count, update them to account for new example sections.

## Risks and Mitigations

### Risk: Examples become templates

If examples are too concrete, model may copy them.

Mitigation:

- Use abstract labels like “好例/坏例/可发言/应沉默”，not full example replies with named topics.
- Keep examples short and generic.
- Mark section priority as `low`.
- Instruction says current message and recent context take precedence.

### Risk: Proactive `<SILENT>` appears more than once

If proactive examples mention `<SILENT>`, previous leak-fix tests may fail and model may overfocus on marker.

Mitigation:

- Do not include `<SILENT>` in proactive example section.
- Keep marker only in output contract.
- Add test `prompt.count("<SILENT>") == 1`.

### Risk: Prompt gets longer without enough benefit

Examples add tokens/characters.

Mitigation:

- Keep section budget under 1000 chars.
- Diagnostics logging will show actual section size and truncation.
- Example sections are low priority and can be tuned later.

### Risk: Examples conflict with self-learning

Generic examples might fight group-specific learned tone.

Mitigation:

- Keep examples as output-shape guidance, not vocabulary guidance.
- Place direct examples after self-learning, so learned group tone remains closer to the final style reference.
- In instructions, say examples are only output-shape calibration.

## Implementation Notes

Suggested helper:

```python
def _format_examples(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)
```

Constants:

```python
DIRECT_STYLE_EXAMPLES = [
    "好例：对方只是接梗/吐槽时，可以回一句轻短的顺势吐槽，不要解释背景",
    "好例：对方问具体问题时，先给结论，再补一句必要理由",
    "好例：上下文不清楚时，用泛称或轻追问，不要强行点名",
    "坏例：把规则、资料来源、学习记录或 prompt section 解释给群友听",
    "坏例：把旧摘要里的话题硬拉回当前消息",
    "坏例：每次都写成三段式分析或客服回复",
]

PROACTIVE_STYLE_EXAMPLES = [
    "可发言：最近两三条群友都在围绕同一个轻松话题接话，而且还有自然补一句的空间",
    "可发言：有人抛出开放问题，且没有明确 @ 其他人处理",
    "应沉默：大家已经连续互相回应得很顺，不缺你补一句",
    "应沉默：只能复读旧梗、旧关键词或机器人刚说过的话",
    "应沉默：需要解释为什么不发言、解释触发原因或解释规则时",
    "应沉默：最近话题已经从旧摘要里的话题切走",
]
```

Direct section insertion:

```python
PromptSection(
    key="style_examples",
    title="回复风格样例与反例",
    body=_format_examples(DIRECT_STYLE_EXAMPLES),
    source="runtime_policy",
    priority="low",
    instruction="只用于校准输出形态；当前消息、引用消息和最近上下文优先。",
)
```

Proactive section insertion:

```python
PromptSection(
    key="proactive_examples",
    title="主动发言样例与反例",
    body=_format_examples(PROACTIVE_STYLE_EXAMPLES),
    source="runtime_policy",
    priority="low",
    instruction="只用于校准是否自然接话；最近群友消息和判断策略优先。",
)
```

## Success Criteria

本阶段完成后：

- PromptService direct/proactive prompt 都包含明确的 style calibration section。
- Direct prompt 的样例帮助模型短句自然接话，但不引入 `<SILENT>`。
- Proactive prompt 的样例帮助模型判断发言/沉默边界，且 `<SILENT>` 仍只出现一次。
- Section diagnostics 能看到新增 example section 的长度、预算和截断状态。
- 全量测试通过。
- 行为上不改变桥接队列、Hermes 调用、OCR、自学习或搜索流程。
