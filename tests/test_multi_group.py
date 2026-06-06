import importlib.util
from pathlib import Path

BRIDGE_PATH = Path(__file__).resolve().parents[1] / "bridge.py"


def load_bridge_module():
    spec = importlib.util.spec_from_file_location("bridge_under_test_multi_group", BRIDGE_PATH)
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


def test_group_persona_file_overrides_default_persona(tmp_path):
    bridge = load_bridge_module()
    bridge.PERSONA_FILE = tmp_path / "persona.md"
    bridge.GROUP_CONFIG_DIR = tmp_path / "groups"
    bridge.PERSONA_FILE.write_text("默认群人格", encoding="utf-8")
    (bridge.GROUP_CONFIG_DIR / "781423661").mkdir(parents=True)
    (bridge.GROUP_CONFIG_DIR / "781423661" / "persona.md").write_text("新群独立人格", encoding="utf-8")

    prompt = bridge.build_prompt(make_event(781423661), "你好")

    assert "新群独立人格" in prompt
    assert "默认群人格" not in prompt


def test_allowed_group_ids_accepts_old_and_new_group():
    bridge = load_bridge_module()
    bridge.ALLOWED_GROUP_IDS = {975805598, 781423661}

    assert bridge.is_allowed_group(make_event(975805598)) is True
    assert bridge.is_allowed_group(make_event(781423661)) is True
    assert bridge.is_allowed_group(make_event(123)) is False


def test_recent_context_is_separated_by_group():
    bridge = load_bridge_module()
    bridge.ALLOWED_GROUP_IDS = {975805598, 781423661}
    bridge._recent_messages_by_group.clear()
    bridge.remember_message(make_event(975805598, text="旧群上下文", nickname="旧群人"))
    bridge.remember_message(make_event(781423661, text="新群上下文", nickname="新群人"))

    old_prompt = bridge.build_prompt(make_event(975805598, text="问"), "问")
    new_prompt = bridge.build_prompt(make_event(781423661, text="问"), "问")

    assert "旧群上下文" in old_prompt
    assert "新群上下文" not in old_prompt
    assert "新群上下文" in new_prompt
    assert "旧群上下文" not in new_prompt
