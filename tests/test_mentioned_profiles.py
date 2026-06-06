import importlib.util
from pathlib import Path

BRIDGE_PATH = Path(__file__).resolve().parents[1] / "bridge.py"


def load_bridge_module():
    spec = importlib.util.spec_from_file_location("bridge_under_test_mentions", BRIDGE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def make_event(user_id=2544866989, nickname="曲", message=None):
    if message is None:
        message = [
            {"type": "at", "data": {"qq": "3975680980"}},
            {"type": "text", "data": {"text": " 这个人是谁"}},
            {"type": "at", "data": {"qq": "1223608029"}},
        ]
    return {
        "post_type": "message",
        "message_type": "group",
        "group_id": 975805598,
        "user_id": user_id,
        "self_id": 3975680980,
        "sender": {"nickname": nickname},
        "message": message,
    }


def test_prompt_includes_profile_for_mentioned_qq(tmp_path):
    bridge = load_bridge_module()
    bridge.PERSONA_FILE = tmp_path / "persona.md"
    bridge.PEOPLE_FILE = tmp_path / "people.md"
    bridge.PERSONA_FILE.write_text("简短吐槽", encoding="utf-8")
    bridge.PEOPLE_FILE.write_text(
        """# 群成员资料\n\n## 1223608029\n- 昵称：czq、程子乾\n- 经历/背景：河海大学学生。\n\n## 999\n- 昵称：无关人员\n- 经历/背景：不应该出现。\n""",
        encoding="utf-8",
    )

    event = make_event()
    prompt = bridge.build_prompt(event, bridge.message_to_text(event["message"]))

    assert "被提及的人资料" in prompt
    assert "河海大学学生" in prompt
    assert "不应该出现" not in prompt


def test_prompt_includes_profile_for_name_in_question(tmp_path):
    bridge = load_bridge_module()
    bridge.PERSONA_FILE = tmp_path / "persona.md"
    bridge.PEOPLE_FILE = tmp_path / "people.md"
    bridge.PERSONA_FILE.write_text("简短回复", encoding="utf-8")
    bridge.PEOPLE_FILE.write_text(
        """# 群成员资料\n\n## 1223608029\n- 昵称：czq、程子乾\n- 经历/背景：申请到了香港大学研究生。\n""",
        encoding="utf-8",
    )
    event = make_event(message=[
        {"type": "at", "data": {"qq": "3975680980"}},
        {"type": "text", "data": {"text": " 程子乾是谁"}},
    ])

    prompt = bridge.build_prompt(event, bridge.message_to_text(event["message"]))

    assert "申请到了香港大学研究生" in prompt
