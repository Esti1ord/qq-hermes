import importlib.util
from pathlib import Path

BRIDGE_PATH = Path(__file__).resolve().parents[1] / "bridge.py"


def load_bridge_module():
    spec = importlib.util.spec_from_file_location("bridge_under_test", BRIDGE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_reply_template_choice_is_stable_but_varies_by_key():
    bridge = load_bridge_module()

    a1 = bridge.pick_template("hermes_error", "group:1:user:a")
    a2 = bridge.pick_template("hermes_error", "group:1:user:a")
    choices = {bridge.pick_template("hermes_error", f"group:1:user:{i}") for i in range(20)}

    assert a1 == a2
    assert len(choices) >= 2
    assert a1 in bridge.REPLY_TEMPLATES["hermes_error"]


def test_finalize_empty_reply_uses_template_pool(monkeypatch):
    bridge = load_bridge_module()
    monkeypatch.setattr(bridge, "pick_template", lambda name, key="": "先略过 我还没组织好")

    assert bridge.finalize_reply("") == "先略过 我还没组织好"


def test_finalize_reply_flattens_casual_blank_lines():
    bridge = load_bridge_module()

    raw = "厄齐尔啊 这俩现在不是一个赛道\n\n赫伊森是潜力股 厄齐尔是已经打完履历的顶级前腰\n\n真要比 goat 先让赫伊森踢十年再来碰瓷吧"

    assert bridge.finalize_reply(raw) == "厄齐尔啊 这俩现在不是一个赛道 赫伊森是潜力股 厄齐尔是已经打完履历的顶级前腰 真要比 goat 先让赫伊森踢十年再来碰瓷吧"


def test_finalize_reply_preserves_structured_lists():
    bridge = load_bridge_module()

    raw = "可以这样：\n\n1. 先检查日志\n2. 再重启服务"

    assert bridge.finalize_reply(raw) == "可以这样：\n\n1. 先检查日志\n2. 再重启服务"
