from qq_hermes_bridge import commands


def build_chat_prompt_for_test(**overrides):
    values = {
        "group_id": 123,
        "date_context": "今天",
        "context_summaries": "摘要",
        "recent_context": "最近",
        "reply_context": "引用",
        "reply_to_bot_note": "回复bot",
        "nick": "甲",
        "user_id": 42,
        "mentioned_labels": "乙",
        "user_text": "内容",
        "person_profile": "甲资料",
        "mentioned_profiles": "乙资料",
        "related_profiles": "相关资料",
        "persona": "人设",
        "max_prompt_chars": 10,
        "style_hint": "短句",
    }
    values.update(overrides)
    return commands.build_chat_prompt(**values)


def test_build_chat_prompt_renders_runtime_context_and_rules():
    prompt = build_chat_prompt_for_test()

    assert "群号：123" in prompt
    assert "当前日期：今天" in prompt
    assert "发送者：甲（QQ: 42）" in prompt
    assert "内容：内容" in prompt
    assert "本次风格：短句" in prompt
    assert "群内用语与说话风格学习提示" in prompt
    assert "（暂无群内用语/风格学习提示）" in prompt
    assert "当前被 @ 的消息和被回复/引用的消息是本次任务" in prompt
    assert "不是必须复用的话题清单" in prompt
    assert "相关群友资料只是弱匹配线索" in prompt
    assert "群内用语与说话风格学习提示只作为低权重理解线索" in prompt
    assert "基础人设和 Esti 原始语气优先" in prompt
    assert "不要主动复刻、复读或强化群友话术" in prompt
    assert "不要模仿或重复旧措辞/旧梗" in prompt
    assert "只输出要发到群里的正文" in prompt


def test_build_chat_prompt_accepts_custom_learning_context():
    prompt = build_chat_prompt_for_test(
        learning_context="- 低权重理解线索：只判断互动节奏\n- 风格信号：短句偏多"
    )

    assert "群内用语与说话风格学习提示" in prompt
    assert "低权重理解线索：只判断互动节奏" in prompt
    assert "风格信号：短句偏多" in prompt


def test_build_proactive_prompt_renders_trigger_reasons_or_default():
    prompt = commands.build_proactive_prompt(
        group_id=123,
        date_context="今天",
        context_summaries="摘要",
        recent_context="最近",
        persona="人设",
        reasons=["burst", "multi_user"],
    )

    assert "你是 QQ 群友 Esti" in prompt
    assert "触发原因：burst、multi_user" in prompt
    assert "触发原因只是内部诊断" in prompt
    assert "低权重旧消息和近况摘要只作背景" in prompt
    assert "只能重复旧关键词、旧梗或 Esti 之前的说法" in prompt
    assert "群内用语与说话风格学习提示" not in prompt
    assert "只输出要发到群里的内容" in prompt

    default_prompt = commands.build_proactive_prompt(
        group_id=123,
        date_context="今天",
        context_summaries="摘要",
        recent_context="最近",
        persona="人设",
        reasons=[],
    )
    assert "触发原因：群聊气氛达到主动发言阈值" in default_prompt
    assert "群内用语与说话风格学习提示" not in default_prompt
def test_context_command_reply_hides_context_command_echoes_and_fits_budget():
    summaries = ["摘要一很长" * 20, "摘要二"]
    messages = [
        {"role": "用户", "name": "甲", "text": "/context"},
        {"role": "机器人", "name": "Esti", "text": "我现在记住的前情：\n旧输出"},
        {"role": "用户", "name": "乙乙乙乙乙乙乙乙乙乙乙乙乙", "text": "最近一条有效消息" * 10},
    ]

    reply = commands.build_context_command_reply(
        summaries=summaries,
        messages=messages,
        fallback_messages=[],
        target_group=False,
        max_reply_chars=180,
        reply_prefix="",
        is_context_command_fn=lambda text: text.strip() == "/context",
    )

    assert reply.startswith("我现在记住的前情：")
    assert "/context" not in reply
    assert "旧输出" not in reply
    assert "乙乙乙乙乙乙乙乙乙乙乙乙" in reply
    assert len(reply) <= 180
