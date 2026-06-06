import importlib.util
from pathlib import Path

BRIDGE_PATH = Path(__file__).resolve().parents[1] / "bridge.py"


def load_bridge_module():
    spec = importlib.util.spec_from_file_location("bridge_under_test", BRIDGE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_group_session_name_is_stable_and_group_scoped():
    bridge = load_bridge_module()

    assert bridge.hermes_session_name_for_group(975805598) == "qq-group-975805598"
    assert bridge.hermes_session_name_for_group(781423661) == "qq-group-781423661"


def test_run_hermes_bootstraps_missing_group_session_then_renames(monkeypatch):
    bridge = load_bridge_module()
    bridge.HERMES_BIN = "hermes"
    bridge.HERMES_MODEL = ""
    bridge.HERMES_PROVIDER = ""
    bridge.HERMES_GROUP_SESSIONS_ENABLED = True
    bridge.HERMES_SESSION_AUTOCOMPACT_ENABLED = False
    calls = []

    class FakeMissing:
        returncode = 1
        stdout = "No session found matching 'qq-group-781423661'."
        stderr = ""

    class FakeCreated:
        returncode = 0
        stdout = "好的\n\nsession_id: 20260530_224159_7ab561\n"
        stderr = ""

    class FakeRenamed:
        returncode = 0
        stdout = "renamed"
        stderr = ""

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if len(calls) == 1:
            return FakeMissing()
        if cmd[:3] == ["hermes", "sessions", "rename"]:
            return FakeRenamed()
        return FakeCreated()

    monkeypatch.setattr(bridge.subprocess, "run", fake_run)

    reply = bridge.run_hermes("prompt", group_id=781423661)

    assert reply == "好的"
    assert calls[0][:4] == ["hermes", "chat", "-q", "prompt"]
    assert "--continue" in calls[0]
    assert calls[1][:4] == ["hermes", "chat", "-q", "prompt"]
    assert "--continue" not in calls[1]
    assert calls[2] == ["hermes", "sessions", "rename", "20260530_224159_7ab561", "qq-group-781423661"]


def test_run_hermes_uses_existing_group_continue_session(monkeypatch):
    bridge = load_bridge_module()
    bridge.HERMES_BIN = "hermes"
    bridge.HERMES_MODEL = ""
    bridge.HERMES_PROVIDER = ""
    bridge.HERMES_GROUP_SESSIONS_ENABLED = True
    bridge.HERMES_SESSION_AUTOCOMPACT_ENABLED = False
    seen = {}

    class FakeCompleted:
        returncode = 0
        stdout = "好的"
        stderr = ""

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        return FakeCompleted()

    monkeypatch.setattr(bridge.subprocess, "run", fake_run)

    reply = bridge.run_hermes("prompt", group_id=781423661)

    assert reply == "好的"
    assert seen["cmd"][:4] == ["hermes", "chat", "-q", "prompt"]
    assert "--continue" in seen["cmd"]
    idx = seen["cmd"].index("--continue")
    assert seen["cmd"][idx + 1] == "qq-group-781423661"
    assert "--source" in seen["cmd"]
    assert seen["cmd"][seen["cmd"].index("--source") + 1] == "qq-bridge:781423661"




def test_build_hermes_cmd_uses_group_model_provider_overrides():
    bridge = load_bridge_module()
    bridge.HERMES_BIN = "hermes"
    bridge.HERMES_MODEL = "default-model"
    bridge.HERMES_PROVIDER = "default-provider"
    bridge.HERMES_MODEL_BY_GROUP = {781423661: "deepseek-v4-flash"}
    bridge.HERMES_PROVIDER_BY_GROUP = {781423661: "deepseek"}
    bridge.HERMES_GROUP_SESSIONS_ENABLED = True

    routed = bridge.build_hermes_cmd("prompt", group_id=781423661)
    default = bridge.build_hermes_cmd("prompt", group_id=975805598)

    assert routed[routed.index("--model") + 1] == "deepseek-v4-flash"
    assert routed[routed.index("--provider") + 1] == "deepseek"
    assert default[default.index("--model") + 1] == "default-model"
    assert default[default.index("--provider") + 1] == "default-provider"


def test_run_hermes_can_disable_group_sessions(monkeypatch):
    bridge = load_bridge_module()
    bridge.HERMES_BIN = "hermes"
    bridge.HERMES_GROUP_SESSIONS_ENABLED = False
    seen = {}

    class FakeCompleted:
        returncode = 0
        stdout = "好的"
        stderr = ""

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        return FakeCompleted()

    monkeypatch.setattr(bridge.subprocess, "run", fake_run)

    bridge.run_hermes("prompt", group_id=781423661)

    assert "--continue" not in seen["cmd"]


def test_run_hermes_autocompacts_oversized_group_session(monkeypatch):
    bridge = load_bridge_module()
    bridge.HERMES_BIN = "hermes"
    bridge.HERMES_MODEL = ""
    bridge.HERMES_PROVIDER = ""
    bridge.HERMES_GROUP_SESSIONS_ENABLED = True
    bridge.HERMES_SESSION_AUTOCOMPACT_ENABLED = True
    bridge.HERMES_SESSION_MAX_MESSAGES = 10
    bridge.HERMES_SESSION_MAX_BODY_CHARS = 0
    calls = []

    class FakeCompleted:
        returncode = 0
        stderr = ""

        def __init__(self, stdout="好的"):
            self.stdout = stdout

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[:3] == ["hermes", "sessions", "delete"]:
            return FakeCompleted("Deleted")
        if cmd[:3] == ["hermes", "sessions", "rename"]:
            return FakeCompleted("renamed")
        if "--continue" not in cmd:
            return FakeCompleted("压缩摘要已记录\n\nsession_id: 20260531_compacted\n")
        return FakeCompleted("好的")

    monkeypatch.setattr(bridge, "hermes_session_id_by_title", lambda name: "old_session")
    monkeypatch.setattr(bridge, "_sqlite_message_count_for_session", lambda session_id: 12)
    monkeypatch.setattr(bridge, "_estimated_session_body_chars", lambda session_id: 100)
    monkeypatch.setattr(bridge.subprocess, "run", fake_run)

    reply = bridge.run_hermes("prompt", group_id=781423661)

    assert reply == "好的"
    assert ["hermes", "sessions", "delete", "--yes", "old_session"] in calls
    assert ["hermes", "sessions", "rename", "20260531_compacted", "qq-group-781423661"] in calls
    assert calls[-1][:4] == ["hermes", "chat", "-q", "prompt"]
    assert "--continue" in calls[-1]
