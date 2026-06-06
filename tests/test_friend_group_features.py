import importlib.util
from pathlib import Path

BRIDGE_PATH = Path(__file__).resolve().parents[1] / "bridge.py"


def load_bridge_module():
    spec = importlib.util.spec_from_file_location("bridge_under_test_feature_batch", BRIDGE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def make_event(text="问题？", user_id=111, nickname="提问者", extra=None):
    message = [
        {"type": "at", "data": {"qq": "3975680980", "name": "Esti1ord"}},
        {"type": "text", "data": {"text": " " + text}},
    ]
    if extra:
        message.extend(extra)
    return {
        "post_type": "message",
        "message_type": "group",
        "group_id": 975805598,
        "user_id": user_id,
        "self_id": 3975680980,
        "sender": {"nickname": nickname},
        "message": message,
    }


def test_per_user_cooldown_blocks_repeated_mentions():
    bridge = load_bridge_module()
    bridge.USER_COOLDOWN_SECONDS = 30
    bridge._last_user_reply_at.clear()
    now = 1000.0

    allowed, reason = bridge.should_rate_limit(975805598, 123, now)
    assert allowed is False
    assert reason == ""
    bridge.mark_user_replied(975805598, 123, now)

    limited, reason = bridge.should_rate_limit(975805598, 123, now + 5)
    assert limited is True
    assert "太频繁" in reason

    other_user_limited, _ = bridge.should_rate_limit(975805598, 456, now + 5)
    assert other_user_limited is False


def test_should_skip_unclear_bare_mentions():
    bridge = load_bridge_module()
    assert bridge.should_skip_unclear_mention("@Esti1ord") is True
    assert bridge.should_skip_unclear_mention("@Esti1ord ？") is True
    assert bridge.should_skip_unclear_mention("@Esti1ord 你怎么看") is False
    assert bridge.should_skip_unclear_mention("@Esti1ord 哈哈哈") is False


def test_finalize_reply_removes_ai_phrases_and_limits_length():
    bridge = load_bridge_module()
    bridge.MAX_REPLY_CHARS = 20
    text = "作为一个AI，我无法真正体验。" + "很长" * 30

    out = bridge.finalize_reply(text)

    assert "作为一个AI" not in out
    assert len(out) <= 20


def test_reply_segment_context_is_preserved_in_prompt():
    bridge = load_bridge_module()
    event = make_event("这句啥意思", extra=[{"type": "reply", "data": {"text": "原话内容", "message_id": "abc"}}])

    prompt = bridge.build_prompt(event, bridge.message_to_text(event["message"]))

    assert "被回复/引用的消息" in prompt
    assert "原话内容" in prompt


def test_tags_in_people_md_are_prioritized_for_related_profiles(tmp_path):
    bridge = load_bridge_module()
    bridge.PEOPLE_FILE = tmp_path / "people.md"
    bridge.PERSONA_FILE = tmp_path / "persona.md"
    bridge.PERSONA_FILE.write_text("简短回复", encoding="utf-8")
    bridge.PEOPLE_FILE.write_text(
        """# 群成员资料\n\n## 1\n- 昵称：标签命中\n- 标签：武汉、读研、华科\n- 经历/背景：标签命中的资料。\n\n## 2\n- 昵称：正文弱命中\n- 经历/背景：武汉相关但不是优先。\n""",
        encoding="utf-8",
    )

    profiles = bridge.keyword_related_profiles("武汉怎么样")

    assert profiles.index("标签命中") < profiles.index("正文弱命中")


def test_context_can_be_saved_and_loaded_from_disk(tmp_path):
    bridge = load_bridge_module()
    bridge.CONTEXT_CACHE_FILE = tmp_path / "context.jsonl"
    bridge._recent_messages.clear()
    bridge._recent_messages_by_group.clear()
    bridge.recent_messages_for_group(bridge.TARGET_GROUP_ID).append({"user_id": 1, "name": "甲", "text": "缓存消息"})

    bridge.save_context_cache()
    bridge._recent_messages.clear()
    bridge.load_context_cache()

    assert list(bridge._recent_messages)[0]["text"] == "缓存消息"


def test_style_hint_varies_by_user_and_message_without_random_module():
    bridge = load_bridge_module()
    a = bridge.style_hint_for(make_event("同一句", user_id=1))
    b = bridge.style_hint_for(make_event("同一句", user_id=2))

    assert a
    assert b
    assert a in bridge.STYLE_HINTS
    assert b in bridge.STYLE_HINTS
