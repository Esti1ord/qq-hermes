import importlib.util
from pathlib import Path

BRIDGE_PATH = Path(__file__).resolve().parents[1] / "bridge.py"


def load_bridge_module():
    spec = importlib.util.spec_from_file_location("bridge_under_test_at_names", BRIDGE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_at_segment_with_name_matches_people_profile(tmp_path):
    bridge = load_bridge_module()
    bridge.PEOPLE_FILE = tmp_path / "people.md"
    bridge.PERSONA_FILE = tmp_path / "persona.md"
    bridge.PERSONA_FILE.write_text("简短回复", encoding="utf-8")
    bridge.PEOPLE_FILE.write_text(
        """# 群成员资料\n\n## 2544866989\n- 昵称：曲\n- 经历/背景：群友曲的资料。\n\n## 1223608029\n- 昵称：程子乾\n- 经历/背景：不应匹配。\n""",
        encoding="utf-8",
    )
    event = {
        "post_type": "message",
        "message_type": "group",
        "group_id": 975805598,
        "user_id": 111,
        "self_id": 3975680980,
        "sender": {"nickname": "提问者"},
        "message": [
            {"type": "at", "data": {"qq": "3975680980", "name": "Esti1ord"}},
            {"type": "text", "data": {"text": " 这个人是谁 "}},
            {"type": "at", "data": {"qq": "2544866989", "name": "曲"}},
        ],
    }

    prompt = bridge.build_prompt(event, bridge.message_to_text(event["message"]))

    assert "群友曲的资料" in prompt
    assert "不应匹配" not in prompt
    assert "@曲" in prompt


def test_cq_at_with_qq_keeps_at_name_from_people_profile(tmp_path):
    bridge = load_bridge_module()
    bridge.PEOPLE_FILE = tmp_path / "people.md"
    bridge.PERSONA_FILE = tmp_path / "persona.md"
    bridge.PERSONA_FILE.write_text("简短回复", encoding="utf-8")
    bridge.PEOPLE_FILE.write_text(
        """# 群成员资料\n\n## 2544866989\n- 昵称：曲\n- 经历/背景：群友曲的资料。\n""",
        encoding="utf-8",
    )
    event = {
        "post_type": "message",
        "message_type": "group",
        "group_id": 975805598,
        "user_id": 111,
        "self_id": 3975680980,
        "sender": {"nickname": "提问者"},
        "message": "[CQ:at,qq=3975680980] 这个人是谁 [CQ:at,qq=2544866989]",
    }

    prompt = bridge.build_prompt(event, bridge.message_to_text(event["message"]))

    assert "群友曲的资料" in prompt
    assert "@曲" in prompt
