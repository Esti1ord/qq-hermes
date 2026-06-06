import importlib.util
from pathlib import Path

BRIDGE_PATH = Path(__file__).resolve().parents[1] / "bridge.py"


def load_bridge_module():
    spec = importlib.util.spec_from_file_location("bridge_under_test_keyword_profiles", BRIDGE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def make_event(text="武汉这地方咋样", user_id=111, nickname="提问者"):
    return {
        "post_type": "message",
        "message_type": "group",
        "group_id": 975805598,
        "user_id": user_id,
        "self_id": 3975680980,
        "sender": {"nickname": nickname},
        "message": [
            {"type": "at", "data": {"qq": "3975680980", "name": "Esti1ord"}},
            {"type": "text", "data": {"text": " " + text}},
        ],
    }


def test_prompt_includes_related_people_when_query_mentions_background_keyword(tmp_path):
    bridge = load_bridge_module()
    bridge.PEOPLE_FILE = tmp_path / "people.md"
    bridge.PERSONA_FILE = tmp_path / "persona.md"
    bridge.PERSONA_FILE.write_text("简短回复", encoding="utf-8")
    bridge.PEOPLE_FILE.write_text(
        """# 群成员资料\n\n## 10001\n- 昵称：阿武\n- 关系/身份：群友。\n- 经历/背景：在武汉上学，熟悉武汉高校和生活。\n\n## 10002\n- 昵称：海边人\n- 关系/身份：群友。\n- 经历/背景：在青岛工作。\n""",
        encoding="utf-8",
    )

    event = make_event("武汉读研体验怎么样")
    prompt = bridge.build_prompt(event, bridge.message_to_text(event["message"]))

    assert "相关群友资料" in prompt
    assert "在武汉上学" in prompt
    assert "在青岛工作" not in prompt


def test_keyword_related_profiles_limit_matches_to_avoid_dumping_people_file(tmp_path):
    bridge = load_bridge_module()
    bridge.PEOPLE_FILE = tmp_path / "people.md"
    bridge.PERSONA_FILE = tmp_path / "persona.md"
    bridge.RELATED_PROFILE_MAX_MATCHES = 2
    bridge.PERSONA_FILE.write_text("简短回复", encoding="utf-8")
    bridge.PEOPLE_FILE.write_text(
        """# 群成员资料\n\n## 1\n- 昵称：一号\n- 经历/背景：在武汉上学。\n\n## 2\n- 昵称：二号\n- 经历/背景：武汉本地人。\n\n## 3\n- 昵称：三号\n- 经历/背景：也在武汉。\n""",
        encoding="utf-8",
    )

    event = make_event("武汉有什么好玩的")
    prompt = bridge.build_prompt(event, bridge.message_to_text(event["message"]))

    assert "一号" in prompt
    assert "二号" in prompt
    assert "三号" not in prompt
