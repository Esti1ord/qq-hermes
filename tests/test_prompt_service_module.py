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
        "media_context",
        "sender_profile",
        "mentioned_profiles",
        "related_profiles",
        "self_learning",
        "persona",
    ]
    metadata = {section.key: (section.source, section.priority) for section in request.sections}
    assert metadata["current_message"] == ("current_message", "critical")
    assert metadata["recent_context"] == ("recent_context", "high")
    assert metadata["summary_context"] == ("generated_summary", "low")
    assert metadata["self_learning"] == ("self_learning", "low")
    assert metadata["persona"] == ("persona", "medium")
    assert request.output_contract == "只输出要发到群里的正文。"


def test_build_direct_prompt_renders_existing_direct_guidance():
    prompt = prompt_service.build_chat_prompt(**DIRECT_PROMPT_KWARGS)

    assert "你在 QQ 群里以 Esti 的口吻回复被 @ 的消息" in prompt
    assert "## 当前被 @ 的消息" in prompt
    assert "优先级：critical" in prompt
    assert "内容：@Esti 今晚吃啥" in prompt
    assert "## 群聊近况摘要" in prompt
    assert "优先级：low" in prompt
    assert "普通聊天不要声称自己正在联网搜索" in prompt
    assert "只输出要发到群里的正文。" in prompt
