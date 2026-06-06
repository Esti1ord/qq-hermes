import importlib.util
from pathlib import Path

BRIDGE_PATH = Path(__file__).resolve().parents[1] / "bridge.py"


def load_bridge_module():
    spec = importlib.util.spec_from_file_location("bridge_under_test_group_isolation_review", BRIDGE_PATH)
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


def test_missing_group_id_is_not_allowed():
    bridge = load_bridge_module()
    event = make_event(975805598)
    del event["group_id"]

    assert bridge.is_allowed_group(event) is False


def test_second_group_does_not_receive_global_people_profiles(tmp_path):
    bridge = load_bridge_module()
    bridge.PERSONA_FILE = tmp_path / "persona.md"
    bridge.PEOPLE_FILE = tmp_path / "people.md"
    bridge.GROUP_CONFIG_DIR = tmp_path / "groups"
    bridge.PERSONA_FILE.write_text("默认人格", encoding="utf-8")
    bridge.PEOPLE_FILE.write_text("""# people\n\n## 1\n- 昵称：武汉人\n- 标签：武汉\n- 经历/背景：旧群的武汉资料。\n""", encoding="utf-8")
    (bridge.GROUP_CONFIG_DIR / "781423661").mkdir(parents=True)
    (bridge.GROUP_CONFIG_DIR / "781423661" / "persona.md").write_text("新群人格", encoding="utf-8")

    prompt = bridge.build_prompt(make_event(781423661, "武汉怎么样"), "武汉怎么样")

    assert "新群人格" in prompt
    assert "旧群的武汉资料" not in prompt


def test_default_group_still_receives_global_people_profiles(tmp_path):
    bridge = load_bridge_module()
    bridge.PERSONA_FILE = tmp_path / "persona.md"
    bridge.PEOPLE_FILE = tmp_path / "people.md"
    bridge.GROUP_CONFIG_DIR = tmp_path / "groups"
    bridge.PERSONA_FILE.write_text("默认人格", encoding="utf-8")
    bridge.PEOPLE_FILE.write_text("""# people\n\n## 1\n- 昵称：武汉人\n- 标签：武汉\n- 经历/背景：旧群的武汉资料。\n""", encoding="utf-8")

    prompt = bridge.build_prompt(make_event(975805598, "武汉怎么样"), "武汉怎么样")

    assert "旧群的武汉资料" in prompt


def test_test_request_can_choose_group_id():
    bridge = load_bridge_module()
    req = bridge.TestRequest(text="测试", group_id=781423661)

    assert req.group_id == 781423661
