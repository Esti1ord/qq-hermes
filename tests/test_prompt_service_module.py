from qq_hermes_bridge import prompt_service


def test_render_prompt_preserves_section_order_and_metadata():
    request = prompt_service.PromptRequest(
        kind="direct",
        group_id=975805598,
        date_context="当前日期：2026-06-08",
        sections=[
            prompt_service.PromptSection(
                key="current_message",
                title="当前消息",
                body="内容：今晚吃啥",
                source="current_message",
                priority="critical",
                instruction="本次回复的核心任务。",
            ),
            prompt_service.PromptSection(
                key="persona",
                title="基础人设",
                body="你是 Esti",
                source="persona",
                priority="medium",
            ),
        ],
        rules=["用中文自然回复", "不要冒充真人经历"],
        output_contract="只输出要发到群里的正文。",
    )

    rendered = prompt_service.render_prompt(request)

    assert rendered.section_keys == ("current_message", "persona")
    assert rendered.char_count == len(rendered.text)
    assert rendered.text.index("## 当前消息") < rendered.text.index("## 基础人设")
    assert "类型：direct" in rendered.text
    assert "群号：975805598" in rendered.text
    assert "来源：current_message" in rendered.text
    assert "优先级：critical" in rendered.text
    assert "使用说明：本次回复的核心任务。" in rendered.text
    assert "来源：persona" in rendered.text
    assert "优先级：medium" in rendered.text
    assert "- 用中文自然回复" in rendered.text
    assert "## 输出要求" in rendered.text
    assert rendered.text.rstrip().endswith("只输出要发到群里的正文。")


DIRECT_PROMPT_KWARGS = dict(
    group_id=975805598,
    date_context="当前日期：2026-06-08（周一，CST+0800）",
    context_summaries="- 昨天大家聊了火锅",
    recent_context="[1] 发言人：甲（QQ: 1）\n[1] 内容：晚上吃啥",
    reply_context="（没有引用消息）",
    reply_to_bot_note="（不是回复机器人消息）",
    nick="乙",
    user_id=2,
    mentioned_labels="（当前消息没有额外 @ 其他人）",
    user_text="@Esti 今晚吃啥",
    person_profile="乙：爱吃辣",
    mentioned_profiles="（本群没有配置被询问对象资料）",
    related_profiles="甲：常约饭",
    persona="Esti 是群友式口吻",
    max_prompt_chars=3500,
    style_hint="自然短句",
    media_context="（当前消息没有图片识别结果）",
    learning_context="常见语气：笑死、离谱",
)


def test_build_direct_prompt_request_sections_and_metadata():
    request = prompt_service.build_direct_prompt_request(**DIRECT_PROMPT_KWARGS)

    assert request.kind == "direct"
    assert request.group_id == 975805598
    assert [section.key for section in request.sections] == [
        "runtime_date",
        "summary_context",
        "recent_context",
        "quoted_context",
        "current_message",
        "response_strategy",
        "media_context",
        "sender_profile",
        "mentioned_profiles",
        "related_profiles",
        "self_learning",
        "style_examples",
        "persona",
    ]
    metadata = {section.key: (section.source, section.priority) for section in request.sections}
    assert metadata["current_message"] == ("current_message", "critical")
    assert metadata["response_strategy"] == ("runtime_policy", "high")
    assert metadata["recent_context"] == ("recent_context", "high")
    assert metadata["summary_context"] == ("generated_summary", "low")
    assert metadata["self_learning"] == ("self_learning", "low")
    assert metadata["style_examples"] == ("runtime_policy", "low")
    assert metadata["persona"] == ("persona", "medium")
    assert request.output_contract == "只输出要发到群里的正文。"


def test_build_direct_prompt_renders_existing_direct_guidance():
    prompt = prompt_service.build_chat_prompt(**DIRECT_PROMPT_KWARGS)

    assert "你在 QQ 群里以 Esti 的口吻回复被 @ 的消息" in prompt
    assert "## 当前被 @ 的消息" in prompt
    assert "优先级：critical" in prompt
    assert "内容：@Esti 今晚吃啥" in prompt
    assert "## 本次回复策略" in prompt
    assert "本次风格：自然短句" in prompt
    assert "## 回复风格样例与反例" in prompt
    assert "好例：" in prompt
    assert "坏例：" in prompt
    assert "<SILENT>" not in prompt
    assert "可用搜索能力" not in prompt
    assert "any-search-skill" in prompt
    assert "主动调用 any-search-skill" in prompt
    assert "不需要用户明确说“搜/查”" in prompt
    assert "普通常识、主观聊天" in prompt
    assert "工具不可用、失败或结果不足" in prompt
    assert "不要假装查过" in prompt
    assert "普通聊天不要声称自己正在联网搜索" not in prompt
    assert "不要声称已搜索或编造" not in prompt
    assert "直接说明不能实时核查" not in prompt
    assert "只输出要发到群里的正文。" in prompt


PROACTIVE_PROMPT_KWARGS = dict(
    group_id=975805598,
    date_context="当前日期：2026-06-08（周一，CST+0800）",
    context_summaries="- 大家刚才在聊晚饭",
    recent_context="高权重：最近群友消息\n[高权重 1] 内容：有人吃火锅吗",
    persona="Esti 是群友式口吻",
    reasons=["burst", "open_question"],
)


def test_build_proactive_prompt_request_sections_and_metadata():
    request = prompt_service.build_proactive_prompt_request(**PROACTIVE_PROMPT_KWARGS)

    assert request.kind == "proactive"
    assert [section.key for section in request.sections] == [
        "runtime_date",
        "summary_context",
        "recent_context",
        "decision_strategy",
        "trigger_reasons",
        "proactive_examples",
        "persona",
    ]
    metadata = {section.key: (section.source, section.priority) for section in request.sections}
    assert metadata["recent_context"] == ("recent_context", "critical")
    assert metadata["decision_strategy"] == ("runtime_policy", "high")
    assert metadata["summary_context"] == ("generated_summary", "low")
    assert metadata["trigger_reasons"] == ("internal_diagnostic", "low")
    assert metadata["proactive_examples"] == ("runtime_policy", "low")
    assert metadata["persona"] == ("persona", "medium")
    assert request.output_contract == "只输出要发到群里的内容；如果不发言，只输出 <SILENT> 这个标记。"


def test_build_proactive_prompt_renders_silent_contract_once():
    prompt = prompt_service.build_proactive_prompt(**PROACTIVE_PROMPT_KWARGS)

    assert "你是 QQ 群友 Esti，判断是否主动接一句话" in prompt
    assert "## 群聊上下文" in prompt
    assert "优先级：critical" in prompt
    assert "## 触发原因" in prompt
    assert "## 主动发言样例与反例" in prompt
    assert "可发言：" in prompt
    assert "应沉默：" in prompt
    assert "来源：internal_diagnostic" in prompt
    assert "burst、open_question" in prompt
    assert prompt.count("<SILENT>") == 1
    assert "空输出是正确的" not in prompt
    assert "不要解释沉默原因或输出规则" in prompt
    assert "any-search-skill" in prompt
    assert "触发信号只代表候选热度，不代表必须发言" in prompt
    assert "主动判断话题插入性" in prompt
    assert "没有自然插入点、没有值得补的一句" in prompt
    assert "必须先调用 any-search-skill" in prompt
    assert "不要因为可以搜索而提高插话积极性" in prompt
    assert "工具不可用、失败或结果不足" in prompt
    assert "不要假装查过或凭印象编造" in prompt
    assert "主动发言一般只接纯闲聊" not in prompt
    assert "不要声称已联网、已实时查询或已查官方结果" not in prompt


from qq_hermes_bridge import commands


def rendered_section_by_key(rendered, key):
    return next(section for section in rendered.sections if section.key == key)


def test_commands_build_chat_prompt_delegates_to_prompt_service():
    assert commands.build_chat_prompt(**DIRECT_PROMPT_KWARGS) == prompt_service.build_chat_prompt(**DIRECT_PROMPT_KWARGS)


def test_commands_build_rendered_chat_prompt_exposes_diagnostics():
    rendered = commands.build_rendered_chat_prompt(**DIRECT_PROMPT_KWARGS)

    assert rendered.text == prompt_service.build_chat_prompt(**DIRECT_PROMPT_KWARGS)
    assert rendered.char_count == len(rendered.text)
    assert rendered_section_by_key(rendered, "current_message").priority == "critical"
    style = rendered_section_by_key(rendered, "style_examples")
    assert style.budget_chars == 700
    assert style.truncated is False
    assert "<SILENT>" not in rendered.text


def test_commands_build_proactive_prompt_delegates_to_prompt_service():
    assert commands.build_proactive_prompt(**PROACTIVE_PROMPT_KWARGS) == prompt_service.build_proactive_prompt(**PROACTIVE_PROMPT_KWARGS)


def test_commands_build_rendered_proactive_prompt_exposes_diagnostics():
    rendered = commands.build_rendered_proactive_prompt(**PROACTIVE_PROMPT_KWARGS)

    assert rendered.text == prompt_service.build_proactive_prompt(**PROACTIVE_PROMPT_KWARGS)
    assert rendered.char_count == len(rendered.text)
    assert rendered_section_by_key(rendered, "recent_context").priority == "critical"
    examples = rendered_section_by_key(rendered, "proactive_examples")
    assert examples.budget_chars == 650
    assert examples.truncated is False
    assert rendered.text.count("<SILENT>") == 1


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


def test_direct_recent_context_truncation_preserves_guidance_and_latest_tail():
    kwargs = dict(DIRECT_PROMPT_KWARGS)
    kwargs["recent_context"] = "注意：最近上下文有时间权重\n较早上下文" + ("旧" * 4200) + "最新关键消息"
    request = prompt_service.build_direct_prompt_request(**kwargs)

    rendered = prompt_service.render_prompt(request)

    recent = rendered_section_by_key(rendered, "recent_context")
    assert recent.budget_chars == 2500
    assert recent.truncated is True
    assert recent.rendered_char_count == 2500
    assert "注意：最近上下文有时间权重" in rendered.text
    assert "最新关键消息" in rendered.text
    assert "较早上下文" not in rendered.text


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
    assert summary.budget_chars == 600
    assert summary.truncated is True
    assert summary.rendered_char_count == 600
    assert learning.budget_chars == 500
    assert learning.truncated is True
    assert learning.rendered_char_count == 500
    assert current.budget_chars is None
    assert current.truncated is False
    assert prompt_service.TRUNCATION_SUFFIX in rendered.text


def test_direct_fast_profile_reduces_prompt_while_preserving_required_sections():
    kwargs = dict(DIRECT_PROMPT_KWARGS)
    kwargs.update({
        "context_summaries": "摘要" * 400,
        "recent_context": "注意：最近上下文有时间权重\n" + ("最近" * 1200) + "最新消息",
        "reply_context": "引用" * 600,
        "person_profile": "资料" * 400,
        "mentioned_profiles": "被提及" * 300,
        "related_profiles": "相关" * 300,
        "learning_context": "学习" * 400,
        "persona": "人设" * 600,
    })

    rich = prompt_service.build_rendered_chat_prompt(**kwargs, direct_prompt_profile="rich")
    fast = prompt_service.build_rendered_chat_prompt(**kwargs, direct_prompt_profile="fast")

    assert fast.profile == "fast"
    assert rich.profile == "rich"
    assert fast.char_count < rich.char_count
    assert fast.char_count <= int(rich.char_count * 0.85)
    for key in ("runtime_date", "recent_context", "quoted_context", "current_message", "response_strategy", "media_context", "persona"):
        assert key in fast.section_keys
    assert "mentioned_profiles" in fast.section_keys
    assert "related_profiles" in fast.section_keys
    assert rendered_section_by_key(fast, "mentioned_profiles").budget_chars == 350
    assert rendered_section_by_key(fast, "related_profiles").budget_chars == 240
    assert "style_examples" not in fast.section_keys
    assert "## 输出要求" in fast.text
    assert fast.text.rstrip().endswith("只输出要发到群里的正文。")
    assert "any-search-skill" in fast.text
    assert "不要主动自称 AI、机器人、助手或模型" in fast.text
    assert "不要解释“我学到/记录到/数据库里有”" in fast.text
    assert "不要暴露学习数据、样例来源或统计信息" in fast.text
    assert rendered_section_by_key(fast, "current_message").budget_chars is None


def test_direct_auto_profile_uses_fast_for_short_messages_and_rich_for_long_messages():
    short_request = prompt_service.build_direct_prompt_request(**DIRECT_PROMPT_KWARGS, direct_prompt_profile="auto")
    long_kwargs = dict(DIRECT_PROMPT_KWARGS)
    long_kwargs["user_text"] = "问" * 200
    long_request = prompt_service.build_direct_prompt_request(**long_kwargs, direct_prompt_profile="auto")

    assert short_request.profile == "fast"
    assert long_request.profile == "rich"


def test_direct_total_budget_prefers_truncating_lower_priority_sections():
    kwargs = dict(DIRECT_PROMPT_KWARGS)
    kwargs.update({
        "context_summaries": "摘" * 1000,
        "recent_context": "注意：最近上下文有时间权重\n" + "近" * 3000,
        "reply_context": "引用" * 900,
        "persona": "人" * 1400,
    })

    rendered = prompt_service.build_rendered_chat_prompt(**kwargs, total_budget_chars=3600)

    assert rendered.total_budget_chars == 3600
    assert rendered.total_truncated is True
    assert rendered.char_count <= 3600
    assert rendered_section_by_key(rendered, "current_message").budget_chars is None
    assert rendered_section_by_key(rendered, "summary_context").rendered_char_count <= 600


def test_direct_total_budget_can_reduce_optional_sections_to_zero():
    kwargs = dict(DIRECT_PROMPT_KWARGS)
    kwargs.update({
        "context_summaries": "摘" * 1000,
        "recent_context": "注意：最近上下文有时间权重\n" + "近" * 3000,
        "reply_context": "引用" * 900,
        "persona": "人" * 1400,
    })

    rendered = prompt_service.build_rendered_chat_prompt(**kwargs, total_budget_chars=2500)

    assert rendered.total_budget_chars == 2500
    assert rendered.total_truncated is True
    assert rendered.char_count <= 2500
    assert rendered_section_by_key(rendered, "current_message").budget_chars is None
    assert rendered_section_by_key(rendered, "current_message").rendered_char_count > 0


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
    assert direct_summary.budget_chars == 600
    assert proactive_summary.budget_chars == 350
    assert direct_summary.rendered_char_count == 600
    assert proactive_summary.rendered_char_count == 350


def test_proactive_recent_context_truncation_preserves_high_weight_prefix():
    kwargs = dict(PROACTIVE_PROMPT_KWARGS)
    kwargs["recent_context"] = "高权重：最新群友消息" + ("近" * 3600) + "低权重尾部旧话题"
    request = prompt_service.build_proactive_prompt_request(**kwargs)

    rendered = prompt_service.render_prompt(request)

    recent = rendered_section_by_key(rendered, "recent_context")
    assert recent.budget_chars == 1800
    assert recent.truncated is True
    assert recent.rendered_char_count == 1800
    assert "高权重：最新群友消息" in rendered.text
    assert "低权重尾部旧话题" not in rendered.text


def test_proactive_prompt_keeps_silent_contract_once_when_sections_truncate():
    kwargs = dict(PROACTIVE_PROMPT_KWARGS)
    kwargs["context_summaries"] = "摘" * 1000
    kwargs["recent_context"] = "近" * 5000
    kwargs["persona"] = "人" * 2000

    prompt = prompt_service.build_proactive_prompt(**kwargs)

    assert prompt.count("<SILENT>") == 1
    assert prompt_service.TRUNCATION_SUFFIX in prompt
    assert "空输出是正确的" not in prompt
