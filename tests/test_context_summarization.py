import asyncio
import importlib.util
from pathlib import Path

BRIDGE_PATH = Path(__file__).resolve().parents[1] / "bridge.py"


def load_bridge_module():
    spec = importlib.util.spec_from_file_location("bridge_under_test", BRIDGE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def make_event(group_id=975805598, user_id=111, name="群友", text="消息"):
    return {
        "post_type": "message",
        "message_type": "group",
        "group_id": group_id,
        "user_id": user_id,
        "self_id": 3975680980,
        "sender": {"nickname": name},
        "message": [{"type": "text", "data": {"text": text}}],
    }


def test_build_prompt_puts_context_before_persona_and_marks_persona_as_soft(tmp_path):
    bridge = load_bridge_module()
    bridge.GROUP_CONFIG_DIR = tmp_path / "groups"
    group_dir = bridge.GROUP_CONFIG_DIR / "975805598"
    group_dir.mkdir(parents=True)
    (group_dir / "persona.md").write_text("必须非常机械地回复", encoding="utf-8")
    bridge._context_summaries_by_group.clear()
    bridge._recent_messages_by_group.clear()
    bridge.recent_messages_for_group(975805598).append({"user_id": 1, "name": "甲", "text": "最近话题是实习 offer"})
    bridge.context_summaries_for_group(975805598).append("前情摘要：大家在聊秋招选择。")

    event = make_event(text="那你怎么看")
    prompt = bridge.build_prompt(event, "那你怎么看")

    assert prompt.index("群聊近况摘要") < prompt.index("群聊近二十条上下文") < prompt.index("预设提示词")
    assert "预设提示词是弱约束" in prompt
    assert "最近话题是实习 offer" in prompt
    assert "前情摘要：大家在聊秋招选择。" in prompt


def test_remember_message_compresses_older_messages_into_group_summaries(monkeypatch):
    bridge = load_bridge_module()
    bridge.CONTEXT_MAX_MESSAGES = 20
    bridge.CONTEXT_SUMMARIZE_BATCH = 5
    bridge.CONTEXT_SUMMARY_MAX = 30
    bridge.CONTEXT_PERSIST_ENABLED = False
    bridge._context_summaries_by_group.clear()
    bridge._recent_messages_by_group.clear()

    calls = []

    def fake_summarize(group_id, messages):
        calls.append((group_id, list(messages)))
        return "、".join(m["text"] for m in messages)

    monkeypatch.setattr(bridge, "summarize_context_messages", fake_summarize)

    for i in range(30):
        bridge.remember_message(make_event(text=f"第{i}条"))

    assert len(calls) == 2
    assert calls[0][0] == 975805598
    assert [m["text"] for m in calls[0][1]] == ["第0条", "第1条", "第2条", "第3条", "第4条"]
    assert [m["text"] for m in calls[1][1]] == ["第5条", "第6条", "第7条", "第8条", "第9条"]
    assert list(bridge.context_summaries_for_group(975805598)) == [
        "第0条、第1条、第2条、第3条、第4条",
        "第5条、第6条、第7条、第8条、第9条",
    ]
    recent = list(bridge.recent_messages_for_group(975805598))
    assert len(recent) == 20
    assert recent[0]["text"] == "第10条"


def test_async_remember_message_schedules_context_compaction_off_critical_path(monkeypatch):
    bridge = load_bridge_module()
    bridge.CONTEXT_MAX_MESSAGES = 20
    bridge.CONTEXT_SUMMARIZE_BATCH = 5
    bridge.CONTEXT_SUMMARY_MAX = 30
    bridge.CONTEXT_SUMMARIZE_ENABLED = True
    bridge.CONTEXT_PERSIST_ENABLED = False
    bridge._context_summaries_by_group.clear()
    bridge._recent_messages_by_group.clear()
    bridge._context_compaction_pending_by_group.clear()
    bridge._context_compaction_tasks_by_group.clear()
    calls = []

    def fake_summarize(group_id, messages):
        calls.append((group_id, list(messages)))
        return "、".join(m["text"] for m in messages)

    monkeypatch.setattr(bridge, "summarize_context_messages", fake_summarize)

    async def run():
        for i in range(25):
            bridge.remember_message(make_event(text=f"第{i}条"))
        assert calls == []
        assert len(bridge._context_compaction_pending_by_group[975805598]) == 1
        recent = list(bridge.recent_messages_for_group(975805598))
        assert len(recent) == 20
        assert recent[0]["text"] == "第5条"
        await bridge.wait_context_compaction_tasks(975805598)

    asyncio.run(run())

    assert len(calls) == 1
    assert [m["text"] for m in calls[0][1]] == ["第0条", "第1条", "第2条", "第3条", "第4条"]
    assert list(bridge.context_summaries_for_group(975805598)) == ["第0条、第1条、第2条、第3条、第4条"]


def test_context_summaries_are_limited_to_30(monkeypatch):
    bridge = load_bridge_module()
    bridge.CONTEXT_SUMMARY_MAX = 30
    bridge._context_summaries_by_group.clear()
    summaries = bridge.context_summaries_for_group(975805598)
    for i in range(35):
        summaries.append(f"摘要{i}")
    assert len(summaries) == 30
    assert summaries[0] == "摘要5"
    assert summaries[-1] == "摘要34"


def test_context_cache_persists_recent_and_summaries_by_group(tmp_path):
    bridge = load_bridge_module()
    bridge.CONTEXT_CACHE_FILE = tmp_path / "ctx.jsonl"
    bridge._recent_messages_by_group.clear()
    bridge._context_summaries_by_group.clear()
    bridge.recent_messages_for_group(975805598).append({"user_id": 1, "name": "甲", "text": "旧群近况"})
    bridge.recent_messages_for_group(781423661).append({"user_id": 2, "name": "乙", "text": "新群近况"})
    bridge.context_summaries_for_group(975805598).append("旧群摘要")
    bridge.context_summaries_for_group(781423661).append("新群摘要")

    bridge.save_context_cache()
    bridge._recent_messages_by_group.clear()
    bridge._context_summaries_by_group.clear()
    bridge.load_context_cache()

    old_context = bridge.format_recent_context(975805598)
    new_context = bridge.format_recent_context(781423661)
    assert "[1] 发言人：甲（QQ: 1）" in old_context
    assert "[1] 内容：旧群近况" in old_context
    assert "[1] 发言人：乙（QQ: 2）" in new_context
    assert "[1] 内容：新群近况" in new_context
    assert bridge.format_context_summaries(975805598) == "- 旧群摘要"
    assert bridge.format_context_summaries(781423661) == "- 新群摘要"


def test_summarization_prompt_marks_bot_role_and_discourages_reusing_bot_catchphrases():
    bridge = load_bridge_module()
    messages = [
        {"user_id": 1, "name": "甲", "text": "精神状态不太行"},
        {"user_id": 3975680980, "name": "Esti", "role": "机器人", "text": "这群今天像集体低电量"},
        {"user_id": 2, "name": "乙", "text": "晚上吃火锅吗"},
    ]

    prompt = bridge.summarization_prompt(975805598, messages)

    assert "Esti（QQ: 3975680980，机器人）" in prompt
    assert "不要保留机器人旧笑话、旧措辞或重复口头禅" in prompt
    assert "不要把已经过去的旧词写得像当前仍在继续的话题" in prompt
    assert "只保留话题、关键事实、群友态度或待回答线索" in prompt
