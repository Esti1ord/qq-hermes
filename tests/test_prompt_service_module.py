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
