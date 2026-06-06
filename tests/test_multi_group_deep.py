import importlib.util
from pathlib import Path

BRIDGE_PATH = Path(__file__).resolve().parents[1] / "bridge.py"


def load_bridge_module():
    spec = importlib.util.spec_from_file_location("bridge_under_test_multi_group_deep", BRIDGE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def make_event(group_id, text="你好", user_id=111, nickname="提问者"):
    return {
        "post_type": "message",
        "message_type": "group",
        "group_id": group_id,
        "user_id": user_id,
        "self_id": 3975680980,
        "sender": {"nickname": nickname},
        "message": [
            {"type": "at", "data": {"qq": "3975680980", "name": "Esti1ord"}},
            {"type": "text", "data": {"text": " " + text}},
        ],
    }


def test_context_cache_persists_groups_separately(tmp_path):
    bridge = load_bridge_module()
    bridge.CONTEXT_CACHE_FILE = tmp_path / "recent_context.jsonl"
    bridge.ALLOWED_GROUP_IDS = {975805598, 781423661}
    bridge._recent_messages.clear()
    bridge._recent_messages_by_group.clear()

    bridge.remember_message(make_event(975805598, "旧群缓存", nickname="旧群人"))
    bridge.remember_message(make_event(781423661, "新群缓存", nickname="新群人"))
    bridge.save_context_cache()

    bridge._recent_messages.clear()
    bridge._recent_messages_by_group.clear()
    bridge.load_context_cache()

    old_context = bridge.format_recent_context(975805598)
    new_context = bridge.format_recent_context(781423661)
    assert "旧群缓存" in old_context
    assert "新群缓存" not in old_context
    assert "新群缓存" in new_context
    assert "旧群缓存" not in new_context


def test_cooldown_is_separated_by_group():
    bridge = load_bridge_module()
    bridge.USER_COOLDOWN_SECONDS = 30
    bridge._last_user_reply_at.clear()
    bridge.mark_user_replied(975805598, 123, now=1000.0)

    limited_same_group, _ = bridge.should_rate_limit(975805598, 123, now=1005.0)
    limited_other_group, _ = bridge.should_rate_limit(781423661, 123, now=1005.0)

    assert limited_same_group is True
    assert limited_other_group is False


def test_test_endpoint_can_target_new_group_prompt(tmp_path):
    bridge = load_bridge_module()
    bridge.PERSONA_FILE = tmp_path / "persona.md"
    bridge.GROUP_CONFIG_DIR = tmp_path / "groups"
    bridge.PERSONA_FILE.write_text("旧群人格", encoding="utf-8")
    (bridge.GROUP_CONFIG_DIR / "781423661").mkdir(parents=True)
    (bridge.GROUP_CONFIG_DIR / "781423661" / "persona.md").write_text("新群人格", encoding="utf-8")

    prompt = bridge.build_prompt(make_event(781423661, "测试"), "测试")

    assert "群号：781423661" in prompt
    assert "新群人格" in prompt
    assert "旧群人格" not in prompt
