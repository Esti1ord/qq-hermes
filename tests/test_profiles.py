import importlib.util
from pathlib import Path

BRIDGE_PATH = Path(__file__).resolve().parents[1] / "bridge.py"


def load_bridge_module():
    spec = importlib.util.spec_from_file_location("bridge_under_test_profile", BRIDGE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def make_event(user_id=123456789, nickname="小明", text="测试"):
    return {
        "post_type": "message",
        "message_type": "group",
        "group_id": 975805598,
        "user_id": user_id,
        "self_id": 3975680980,
        "sender": {"nickname": nickname},
        "message": [{"type": "text", "data": {"text": text}}],
    }


def test_load_text_file_returns_fallback_when_missing(tmp_path):
    bridge = load_bridge_module()

    result = bridge.load_text_file(tmp_path / "missing.md", "默认内容")

    assert result == "默认内容"


def test_prompt_includes_persona_and_matching_person_profile(tmp_path):
    bridge = load_bridge_module()
    bridge.PERSONA_FILE = tmp_path / "persona.md"
    bridge.PEOPLE_FILE = tmp_path / "people.md"
    bridge.PERSONA_FILE.write_text("像朋友一样简短回复", encoding="utf-8")
    bridge.PEOPLE_FILE.write_text(
        """# 群成员资料\n\n## 123456789\n- 昵称：小明\n- 经历/背景：喜欢 Linux。\n\n## 987654321\n- 昵称：小红\n- 经历/背景：准备考试。\n""",
        encoding="utf-8",
    )

    prompt = bridge.build_prompt(make_event(user_id=123456789, nickname="小明"), "怎么配环境？")

    assert "像朋友一样简短回复" in prompt
    assert "喜欢 Linux" in prompt
    assert "准备考试" not in prompt


def test_prompt_falls_back_to_nickname_profile_when_qq_id_missing(tmp_path):
    bridge = load_bridge_module()
    bridge.PERSONA_FILE = tmp_path / "persona.md"
    bridge.PEOPLE_FILE = tmp_path / "people.md"
    bridge.PERSONA_FILE.write_text("轻松回复", encoding="utf-8")
    bridge.PEOPLE_FILE.write_text(
        """# 群成员资料\n\n## 未知QQ\n- 昵称：小明、明哥\n- 经历/背景：喜欢折腾电脑。\n""",
        encoding="utf-8",
    )

    prompt = bridge.build_prompt(make_event(user_id=111, nickname="明哥"), "这咋办？")

    assert "喜欢折腾电脑" in prompt
