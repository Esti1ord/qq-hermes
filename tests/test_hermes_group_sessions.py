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


def test_bridge_import_prefers_primary_and_vice_chat_aliases(monkeypatch):
    monkeypatch.setenv("PRIMARY_CHAT_MODEL", "alias-primary-text")
    monkeypatch.setenv("PRIMARY_CHAT_MODEL_PROVIDER", "deepseek")
    monkeypatch.setenv("VICE_CHAT_MODEL", "alias-fallback-text")
    monkeypatch.setenv("VICE_CHAT_MODEL_PROVIDER", "openai-gpt")
    monkeypatch.setenv("HERMES_MODEL", "legacy-primary-text")
    monkeypatch.setenv("HERMES_PROVIDER", "legacy-primary-provider")
    monkeypatch.setenv("HERMES_FALLBACK_MODEL", "legacy-fallback-text")
    monkeypatch.setenv("HERMES_FALLBACK_PROVIDER", "legacy-fallback-provider")

    bridge = load_bridge_module()

    assert bridge.HERMES_MODEL == "alias-primary-text"
    assert bridge.HERMES_PROVIDER == "deepseek"
    assert bridge.HERMES_FALLBACK_MODEL == "alias-fallback-text"
    assert bridge.HERMES_FALLBACK_PROVIDER == "openai-gpt"


def test_run_hermes_start_log_does_not_include_prompt_model_or_provider(monkeypatch):
    bridge = load_bridge_module()
    bridge.HERMES_BIN = "hermes"
    bridge.HERMES_MODEL = "secret-model-name"
    bridge.HERMES_PROVIDER = "secret-provider-name"
    bridge.HERMES_MODEL_BY_GROUP = {}
    bridge.HERMES_PROVIDER_BY_GROUP = {}
    bridge.HERMES_GROUP_SESSIONS_ENABLED = False
    bridge.HERMES_SESSION_AUTOCOMPACT_ENABLED = False
    logs = []

    class FakeCompleted:
        returncode = 0
        stdout = "answer"
        stderr = ""

    monkeypatch.setattr(bridge, "log", lambda event: logs.append(event))
    monkeypatch.setattr(bridge.subprocess, "run", lambda cmd, **kwargs: FakeCompleted())

    assert bridge.run_hermes_raw("SECRET_PROMPT_TEXT", group_id=781423661) == "answer"

    rendered = repr(logs)
    assert "SECRET_PROMPT_TEXT" not in rendered
    assert "secret-model-name" not in rendered
    assert "secret-provider-name" not in rendered
    start = next(item for item in logs if item.get("type") == "hermes_start")
    assert start["has_model"] is True
    assert start["has_provider"] is True
    assert "cmd" not in start


def test_group_session_error_logs_do_not_include_stdout_or_stderr(monkeypatch):
    bridge = load_bridge_module()
    bridge.HERMES_BIN = "hermes"
    bridge.HERMES_MODEL = ""
    bridge.HERMES_PROVIDER = ""
    bridge.HERMES_GROUP_SESSIONS_ENABLED = True
    bridge.HERMES_SESSION_AUTOCOMPACT_ENABLED = False
    logs = []
    calls = []

    class FakeMissing:
        returncode = 1
        stdout = "No session found matching 'qq-group-781423661'."
        stderr = ""

    class FakeCreated:
        returncode = 0
        stdout = "session created\n\nsession_id: 20260530_224159_7ab561\n"
        stderr = ""

    class FakeRenameFailed:
        returncode = 2
        stdout = "SECRET_RENAME_STDOUT"
        stderr = "SECRET_RENAME_STDERR"

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if len(calls) == 1:
            return FakeMissing()
        if cmd[:3] == ["hermes", "sessions", "rename"]:
            return FakeRenameFailed()
        return FakeCreated()

    monkeypatch.setattr(bridge, "log", lambda event: logs.append(event))
    monkeypatch.setattr(bridge.subprocess, "run", fake_run)

    assert bridge.run_hermes_raw("prompt", group_id=781423661) == "session created"

    rendered = repr(logs)
    assert "SECRET_RENAME_STDOUT" not in rendered
    assert "SECRET_RENAME_STDERR" not in rendered
    rename_error = next(item for item in logs if item.get("type") == "hermes_session_rename_error")
    assert "stdout" not in rename_error
    assert "stderr" not in rename_error
    assert rename_error["stdout_len"] == len("SECRET_RENAME_STDOUT")
    assert rename_error["stderr_len"] == len("SECRET_RENAME_STDERR")


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


def test_run_hermes_uses_no_session_fallback_model_when_primary_fails(monkeypatch):
    bridge = load_bridge_module()
    bridge.HERMES_BIN = "hermes"
    bridge.HERMES_MODEL = "primary-model"
    bridge.HERMES_PROVIDER = "primary-provider"
    bridge.HERMES_MODEL_BY_GROUP = {}
    bridge.HERMES_PROVIDER_BY_GROUP = {}
    bridge.HERMES_FALLBACK_ENABLED = True
    bridge.HERMES_FALLBACK_MODEL = "deepseekv4flash"
    bridge.HERMES_FALLBACK_PROVIDER = "官方"
    bridge.HERMES_GROUP_SESSIONS_ENABLED = True
    bridge.HERMES_SESSION_AUTOCOMPACT_ENABLED = False
    calls = []

    class FakeCompleted:
        stderr = ""

        def __init__(self, returncode, stdout):
            self.returncode = returncode
            self.stdout = stdout

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if len(calls) == 1:
            return FakeCompleted(1, "")
        return FakeCompleted(0, "fallback answer")

    monkeypatch.setattr(bridge.subprocess, "run", fake_run)

    reply = bridge.run_hermes_raw("prompt", group_id=781423661)

    assert reply == "fallback answer"
    assert len(calls) == 2
    assert "--continue" in calls[0]
    assert "--continue" not in calls[1]
    assert calls[1][calls[1].index("--model") + 1] == "deepseekv4flash"
    assert calls[1][calls[1].index("--provider") + 1] == "deepseek"


def test_run_hermes_uses_fallback_for_empty_primary_output(monkeypatch):
    bridge = load_bridge_module()
    bridge.HERMES_BIN = "hermes"
    bridge.HERMES_MODEL = "primary-model"
    bridge.HERMES_PROVIDER = "primary-provider"
    bridge.HERMES_MODEL_BY_GROUP = {}
    bridge.HERMES_PROVIDER_BY_GROUP = {}
    bridge.HERMES_FALLBACK_ENABLED = True
    bridge.HERMES_FALLBACK_MODEL = "deepseekv4flash"
    bridge.HERMES_FALLBACK_PROVIDER = "官方"
    bridge.HERMES_GROUP_SESSIONS_ENABLED = False
    calls = []

    class FakeCompleted:
        returncode = 0
        stderr = ""

        def __init__(self, stdout):
            self.stdout = stdout

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return FakeCompleted("" if len(calls) == 1 else "fallback answer")

    monkeypatch.setattr(bridge.subprocess, "run", fake_run)

    reply = bridge.run_hermes_raw("prompt", group_id=781423661)

    assert reply == "fallback answer"
    assert len(calls) == 2


def test_run_hermes_skips_fallback_when_same_as_active_primary(monkeypatch):
    bridge = load_bridge_module()
    bridge.HERMES_BIN = "hermes"
    bridge.HERMES_MODEL = "deepseekv4flash"
    bridge.HERMES_PROVIDER = "官方"
    bridge.HERMES_MODEL_BY_GROUP = {}
    bridge.HERMES_PROVIDER_BY_GROUP = {}
    bridge.HERMES_FALLBACK_ENABLED = True
    bridge.HERMES_FALLBACK_MODEL = "deepseekv4flash"
    bridge.HERMES_FALLBACK_PROVIDER = "官方"
    bridge.HERMES_GROUP_SESSIONS_ENABLED = False
    calls = []

    class FakeCompleted:
        returncode = 1
        stdout = ""
        stderr = "down"

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return FakeCompleted()

    monkeypatch.setattr(bridge.subprocess, "run", fake_run)

    result = bridge.run_hermes_raw_result("prompt", group_id=781423661)

    assert result["ok"] is False
    assert result["reason"] == "hermes_nonzero"
    assert len(calls) == 1


def test_build_hermes_cmd_maps_official_chinese_provider_alias_to_deepseek():
    bridge = load_bridge_module()
    bridge.HERMES_BIN = "hermes"
    bridge.HERMES_MODEL = "deepseek-v4-flash"
    bridge.HERMES_PROVIDER = "官方"
    bridge.HERMES_MODEL_BY_GROUP = {}
    bridge.HERMES_PROVIDER_BY_GROUP = {}
    bridge.HERMES_GROUP_SESSIONS_ENABLED = False

    cmd = bridge.build_hermes_cmd("prompt", group_id=781423661)

    assert cmd[cmd.index("--provider") + 1] == "deepseek"


def test_bridge_import_custom_chat_aliases_activate_direct_http(monkeypatch):
    monkeypatch.setenv("PRIMARY_CHAT_MODEL_PROVIDER", "custom")
    monkeypatch.setenv("PRIMARY_CHAT_MODEL", "custom-chat-model")
    monkeypatch.setenv("PRIMARY_CHAT_MODEL_URL", "")
    monkeypatch.setenv("PRIMARY_CHAT_MODEL_BASE_URL", "")
    monkeypatch.setenv("PRIMARY_CHAT_MODEL_API_KEY_ENV", "")
    monkeypatch.setenv("PRIMARY_CHAT_MODEL_API_KEY", "")
    monkeypatch.setenv("PRIMARY_CHAT_MODEL_API", "")
    monkeypatch.setenv("CUSTOM_CHAT_MODEL_URL", "https://custom-chat.example.test/v1")
    monkeypatch.setenv("CUSTOM_CHAT_MODEL_API_KEY", "dummy-custom-chat-key")
    monkeypatch.setenv("HERMES_PROVIDER_BASE_URL", "https://legacy-chat.example.test/v1")
    monkeypatch.setenv("HERMES_API_KEY_ENV", "LEGACY_TEXT_KEY")

    bridge = load_bridge_module()

    config = bridge.primary_text_http_config_for_group(781423661)
    assert config == {
        "model": "custom-chat-model",
        "provider": "custom",
        "base_url": "https://custom-chat.example.test/v1",
        "api_key_env": "CUSTOM_CHAT_MODEL_API_KEY",
    }


def test_run_hermes_imported_custom_aliases_use_direct_http_safely(monkeypatch):
    monkeypatch.setenv("PRIMARY_CHAT_MODEL_PROVIDER", "custom")
    monkeypatch.setenv("PRIMARY_CHAT_MODEL", "custom-chat-model")
    monkeypatch.setenv("PRIMARY_CHAT_MODEL_URL", "")
    monkeypatch.setenv("PRIMARY_CHAT_MODEL_BASE_URL", "")
    monkeypatch.setenv("PRIMARY_CHAT_MODEL_API_KEY_ENV", "")
    monkeypatch.setenv("PRIMARY_CHAT_MODEL_API_KEY", "")
    monkeypatch.setenv("PRIMARY_CHAT_MODEL_API", "")
    monkeypatch.setenv("CUSTOM_CHAT_MODEL_URL", "")
    monkeypatch.setenv("CUSTOM_CHAT_MODEL_API_KEY_ENV", "")
    monkeypatch.setenv("CUSTOM_CHAT_MODEL_API_KEY", "")
    monkeypatch.setenv("CUSTOM_CHAT_MODEL_BASE_URL", "https://custom-chat.example.test/v1")
    monkeypatch.setenv("CUSTOM_CHAT_MODEL_API", "dummy-custom-chat-key")

    bridge = load_bridge_module()
    bridge.HERMES_MODEL_BY_GROUP = {}
    bridge.HERMES_PROVIDER_BY_GROUP = {}
    bridge.HERMES_FALLBACK_ENABLED = False
    logs = []
    calls = []

    def fake_http(prompt, **kwargs):
        calls.append({"prompt": prompt, **kwargs})
        return {"ok": True, "text": "custom direct answer", "reason": ""}

    monkeypatch.setattr(bridge, "log", lambda event: logs.append(event))
    monkeypatch.setattr(bridge.hermes_runtime, "run_openai_compatible_chat_completion", fake_http)
    monkeypatch.setattr(bridge.subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("CLI should not run")))

    assert bridge.run_hermes_raw("SECRET_PROMPT", group_id=781423661) == "custom direct answer"

    assert len(calls) == 1
    assert calls[0]["base_url"] == "https://custom-chat.example.test/v1"
    assert calls[0]["api_key_env"] == "CUSTOM_CHAT_MODEL_API"
    assert calls[0]["model"] == "custom-chat-model"
    rendered_logs = repr(logs)
    assert "SECRET_PROMPT" not in rendered_logs
    assert "https://custom-chat.example.test" not in rendered_logs
    assert "CUSTOM_CHAT_MODEL_API" not in rendered_logs
    assert any(item.get("type") == "text_http_start" for item in logs)
    assert any(item.get("type") == "text_http_result" for item in logs)


def test_run_hermes_uses_direct_http_primary_when_url_and_api_env_configured(monkeypatch):
    bridge = load_bridge_module()
    bridge.HERMES_MODEL = "custom-deepseek"
    bridge.HERMES_PROVIDER = "custom"
    bridge.HERMES_PROVIDER_BASE_URL = "https://chat.example.test/v1"
    bridge.HERMES_API_KEY_ENV = "TEXT_API_KEY"
    bridge.HERMES_MODEL_BY_GROUP = {}
    bridge.HERMES_PROVIDER_BY_GROUP = {}
    bridge.HERMES_FALLBACK_ENABLED = False
    bridge.HERMES_GROUP_SESSIONS_ENABLED = True
    logs = []
    calls = []

    def fake_http(prompt, **kwargs):
        calls.append({"prompt": prompt, **kwargs})
        return {"ok": True, "text": "direct answer", "reason": ""}

    monkeypatch.setattr(bridge, "log", lambda event: logs.append(event))
    monkeypatch.setattr(bridge.hermes_runtime, "run_openai_compatible_chat_completion", fake_http)
    monkeypatch.setattr(bridge.subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("CLI should not run")))

    assert bridge.run_hermes_raw("SECRET_PROMPT", group_id=781423661) == "direct answer"

    assert len(calls) == 1
    assert calls[0]["base_url"] == "https://chat.example.test/v1"
    assert calls[0]["model"] == "custom-deepseek"
    assert calls[0]["api_key_env"] == "TEXT_API_KEY"
    assert calls[0]["prompt"] == "SECRET_PROMPT"
    rendered_logs = repr(logs)
    assert "SECRET_PROMPT" not in rendered_logs
    assert "https://chat.example.test" not in rendered_logs
    assert "TEXT_API_KEY" not in rendered_logs
    assert any(item.get("type") == "text_http_start" for item in logs)
    assert any(item.get("type") == "text_http_result" for item in logs)


def test_run_direct_hermes_raw_uses_legacy_path_when_direct_knobs_unset(monkeypatch):
    bridge = load_bridge_module()
    bridge.DIRECT_FAST_MODEL_ALIAS = ""
    bridge.DIRECT_STRONG_MODEL_ALIAS = ""
    bridge.DIRECT_CHAT_MODEL_PROVIDER = ""
    bridge.DIRECT_CHAT_MODEL_BASE_URL = ""
    bridge.DIRECT_CHAT_MODEL_API_KEY_ENV = ""
    bridge.DIRECT_MODEL_TIMEOUT_SECONDS = 0
    bridge.DIRECT_MAX_OUTPUT_CHARS = 0
    calls = []

    def fake_run_hermes_raw(prompt, group_id=None, use_group_session=True, purpose="unknown"):
        calls.append({"prompt": prompt, "group_id": group_id, "use_group_session": use_group_session, "purpose": purpose})
        return "legacy direct answer"

    monkeypatch.setattr(bridge, "run_hermes_raw", fake_run_hermes_raw)

    assert bridge.run_direct_hermes_raw("SECRET_PROMPT", group_id=781423661, use_group_session=False, purpose="direct_reply") == "legacy direct answer"

    assert calls == [
        {
            "prompt": "SECRET_PROMPT",
            "group_id": 781423661,
            "use_group_session": False,
            "purpose": "direct_reply",
        }
    ]


def test_direct_fast_lane_cli_uses_direct_model_timeout_and_output_cap_safely(monkeypatch):
    bridge = load_bridge_module()
    bridge.HERMES_BIN = "hermes"
    bridge.HERMES_MODEL = "primary-model"
    bridge.HERMES_PROVIDER = "deepseek"
    bridge.HERMES_MODEL_BY_GROUP = {}
    bridge.HERMES_PROVIDER_BY_GROUP = {}
    bridge.HERMES_FALLBACK_ENABLED = False
    bridge.HERMES_GROUP_SESSIONS_ENABLED = False
    bridge.DIRECT_FAST_MODEL_ALIAS = "fast-direct-model"
    bridge.DIRECT_STRONG_MODEL_ALIAS = ""
    bridge.DIRECT_CHAT_MODEL_PROVIDER = ""
    bridge.DIRECT_CHAT_MODEL_BASE_URL = ""
    bridge.DIRECT_CHAT_MODEL_API_KEY_ENV = ""
    bridge.DIRECT_MODEL_TIMEOUT_SECONDS = 7
    bridge.DIRECT_MAX_OUTPUT_CHARS = 5
    logs = []
    calls = []

    class FakeCompleted:
        returncode = 0
        stdout = "abcdefghijk"
        stderr = ""

    def fake_run(cmd, **kwargs):
        calls.append({"cmd": cmd, "kwargs": kwargs})
        return FakeCompleted()

    monkeypatch.setattr(bridge, "log", lambda event: logs.append(event))
    monkeypatch.setattr(bridge.subprocess, "run", fake_run)

    result = bridge.generate_direct_reply("SECRET_PROMPT", group_id=781423661)

    assert result == {"ok": True, "generation_failed": False, "reply": "abcde"}
    assert len(calls) == 1
    cmd = calls[0]["cmd"]
    assert cmd[cmd.index("--model") + 1] == "fast-direct-model"
    assert cmd[cmd.index("--provider") + 1] == "deepseek"
    assert calls[0]["kwargs"]["timeout"] == 7
    rendered_logs = repr(logs)
    assert "SECRET_PROMPT" not in rendered_logs
    assert "fast-direct-model" not in rendered_logs
    start = next(item for item in logs if item.get("type") == "hermes_start")
    assert start["timeout_s"] == 7
    assert start["has_model"] is True
    assert start["has_provider"] is True


def test_direct_fast_lane_http_override_passes_limits_and_logs_safely(monkeypatch):
    bridge = load_bridge_module()
    bridge.HERMES_MODEL_BY_GROUP = {}
    bridge.HERMES_PROVIDER_BY_GROUP = {}
    bridge.HERMES_FALLBACK_ENABLED = False
    bridge.DIRECT_FAST_MODEL_ALIAS = "fast-direct-model"
    bridge.DIRECT_STRONG_MODEL_ALIAS = ""
    bridge.DIRECT_CHAT_MODEL_PROVIDER = "custom"
    bridge.DIRECT_CHAT_MODEL_BASE_URL = "https://direct-chat.example.test/v1"
    bridge.DIRECT_CHAT_MODEL_API_KEY_ENV = "DIRECT_TEXT_API_KEY"
    bridge.DIRECT_MODEL_TIMEOUT_SECONDS = 6
    bridge.DIRECT_MAX_OUTPUT_CHARS = 42
    logs = []
    calls = []

    def fake_http(prompt, **kwargs):
        calls.append({"prompt": prompt, **kwargs})
        return {"ok": True, "text": "direct http answer", "reason": ""}

    monkeypatch.setattr(bridge, "log", lambda event: logs.append(event))
    monkeypatch.setattr(bridge.hermes_runtime, "run_openai_compatible_chat_completion", fake_http)
    monkeypatch.setattr(bridge.subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("CLI should not run")))

    assert bridge.run_direct_hermes_raw("SECRET_PROMPT", group_id=781423661) == "direct http answer"

    assert len(calls) == 1
    assert calls[0]["prompt"] == "SECRET_PROMPT"
    assert calls[0]["base_url"] == "https://direct-chat.example.test/v1"
    assert calls[0]["api_key_env"] == "DIRECT_TEXT_API_KEY"
    assert calls[0]["model"] == "fast-direct-model"
    assert calls[0]["timeout"] == 6
    assert calls[0]["max_reply_chars"] == 42
    rendered_logs = repr(logs)
    assert "SECRET_PROMPT" not in rendered_logs
    assert "https://direct-chat.example.test" not in rendered_logs
    assert "DIRECT_TEXT_API_KEY" not in rendered_logs
    assert "fast-direct-model" not in rendered_logs
    start = next(item for item in logs if item.get("type") == "text_http_start")
    assert start["timeout_s"] == 6
    assert start["output_cap_chars"] == 42
    assert start["has_model"] is True
    assert start["has_provider"] is True
    assert start["has_base_url"] is True
    assert start["has_api_key_env"] is True


def test_direct_fast_lane_skips_duplicate_fallback_after_provider_normalization(monkeypatch):
    bridge = load_bridge_module()
    bridge.HERMES_BIN = "hermes"
    bridge.HERMES_MODEL = "primary-model"
    bridge.HERMES_PROVIDER = "官方"
    bridge.HERMES_MODEL_BY_GROUP = {}
    bridge.HERMES_PROVIDER_BY_GROUP = {}
    bridge.HERMES_PROVIDER_BASE_URL = ""
    bridge.HERMES_API_KEY_ENV = ""
    bridge.HERMES_FALLBACK_ENABLED = True
    bridge.HERMES_FALLBACK_MODEL = "fast-direct-model"
    bridge.HERMES_FALLBACK_PROVIDER = "deepseek"
    bridge.HERMES_FALLBACK_PROVIDER_BASE_URL = ""
    bridge.HERMES_FALLBACK_API_KEY_ENV = ""
    bridge.HERMES_GROUP_SESSIONS_ENABLED = False
    bridge.DIRECT_FAST_MODEL_ALIAS = "fast-direct-model"
    bridge.DIRECT_STRONG_MODEL_ALIAS = ""
    bridge.DIRECT_CHAT_MODEL_PROVIDER = ""
    bridge.DIRECT_CHAT_MODEL_BASE_URL = ""
    bridge.DIRECT_CHAT_MODEL_API_KEY_ENV = ""
    bridge.DIRECT_MODEL_TIMEOUT_SECONDS = 0
    bridge.DIRECT_MAX_OUTPUT_CHARS = 0
    calls = []

    class FakeFailed:
        returncode = 1
        stdout = ""
        stderr = "down"

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return FakeFailed()

    monkeypatch.setattr(bridge.subprocess, "run", fake_run)

    result = bridge.run_direct_hermes_raw_result("prompt", group_id=781423661)

    assert result["ok"] is False
    assert result["reason"] == "hermes_nonzero"
    assert len(calls) == 1


def test_direct_strong_lane_skips_duplicate_fallback_after_provider_normalization(monkeypatch):
    bridge = load_bridge_module()
    bridge.HERMES_BIN = "hermes"
    bridge.HERMES_MODEL = "primary-model"
    bridge.HERMES_PROVIDER = "官方"
    bridge.HERMES_MODEL_BY_GROUP = {}
    bridge.HERMES_PROVIDER_BY_GROUP = {}
    bridge.HERMES_PROVIDER_BASE_URL = ""
    bridge.HERMES_API_KEY_ENV = ""
    bridge.HERMES_FALLBACK_ENABLED = True
    bridge.HERMES_FALLBACK_MODEL = "strong-direct-model"
    bridge.HERMES_FALLBACK_PROVIDER = "deepseek"
    bridge.HERMES_FALLBACK_PROVIDER_BASE_URL = ""
    bridge.HERMES_FALLBACK_API_KEY_ENV = ""
    bridge.HERMES_GROUP_SESSIONS_ENABLED = False
    bridge.DIRECT_FAST_MODEL_ALIAS = ""
    bridge.DIRECT_STRONG_MODEL_ALIAS = "strong-direct-model"
    bridge.DIRECT_CHAT_MODEL_PROVIDER = ""
    bridge.DIRECT_CHAT_MODEL_BASE_URL = ""
    bridge.DIRECT_CHAT_MODEL_API_KEY_ENV = ""
    bridge.DIRECT_MODEL_TIMEOUT_SECONDS = 0
    bridge.DIRECT_MAX_OUTPUT_CHARS = 0
    calls = []

    class FakeFailed:
        returncode = 1
        stdout = ""
        stderr = "down"

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return FakeFailed()

    monkeypatch.setattr(bridge.subprocess, "run", fake_run)

    result = bridge.run_direct_hermes_raw_result("prompt", group_id=781423661, strong=True)

    assert result["ok"] is False
    assert result["reason"] == "hermes_nonzero"
    assert len(calls) == 1
    assert calls[0][calls[0].index("--model") + 1] == "strong-direct-model"


def test_direct_strong_lane_overrides_model_only_and_preserves_provider(monkeypatch):
    bridge = load_bridge_module()
    bridge.HERMES_BIN = "hermes"
    bridge.HERMES_MODEL = "primary-model"
    bridge.HERMES_PROVIDER = "deepseek"
    bridge.HERMES_PROVIDER_BASE_URL = ""
    bridge.HERMES_API_KEY_ENV = ""
    bridge.HERMES_MODEL_BY_GROUP = {}
    bridge.HERMES_PROVIDER_BY_GROUP = {}
    bridge.HERMES_FALLBACK_ENABLED = False
    bridge.HERMES_GROUP_SESSIONS_ENABLED = False
    bridge.DIRECT_FAST_MODEL_ALIAS = ""
    bridge.DIRECT_STRONG_MODEL_ALIAS = "strong-direct-model"
    bridge.DIRECT_CHAT_MODEL_PROVIDER = ""
    bridge.DIRECT_CHAT_MODEL_BASE_URL = ""
    bridge.DIRECT_CHAT_MODEL_API_KEY_ENV = ""
    bridge.DIRECT_MODEL_TIMEOUT_SECONDS = 0
    bridge.DIRECT_MAX_OUTPUT_CHARS = 0
    calls = []

    class FakeCompleted:
        returncode = 0
        stdout = "strong direct answer"
        stderr = ""

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return FakeCompleted()

    monkeypatch.setattr(bridge.subprocess, "run", fake_run)

    assert bridge.run_direct_hermes_raw("SECRET_PROMPT", group_id=781423661, strong=True) == "strong direct answer"

    assert len(calls) == 1
    cmd = calls[0]
    assert cmd[cmd.index("--model") + 1] == "strong-direct-model"
    assert cmd[cmd.index("--provider") + 1] == "deepseek"


def test_direct_strong_http_lane_preserves_direct_transport_and_logs_safely(monkeypatch):
    bridge = load_bridge_module()
    bridge.HERMES_MODEL_BY_GROUP = {}
    bridge.HERMES_PROVIDER_BY_GROUP = {}
    bridge.HERMES_FALLBACK_ENABLED = False
    bridge.DIRECT_FAST_MODEL_ALIAS = ""
    bridge.DIRECT_STRONG_MODEL_ALIAS = "strong-direct-model"
    bridge.DIRECT_CHAT_MODEL_PROVIDER = "custom"
    bridge.DIRECT_CHAT_MODEL_BASE_URL = "https://direct-chat.example.test/v1"
    bridge.DIRECT_CHAT_MODEL_API_KEY_ENV = "DIRECT_TEXT_API_KEY"
    bridge.DIRECT_MODEL_TIMEOUT_SECONDS = 0
    bridge.DIRECT_MAX_OUTPUT_CHARS = 0
    logs = []
    calls = []

    def fake_http(prompt, **kwargs):
        calls.append({"prompt": prompt, **kwargs})
        return {"ok": True, "text": "strong http answer", "reason": ""}

    monkeypatch.setattr(bridge, "log", lambda event: logs.append(event))
    monkeypatch.setattr(bridge.hermes_runtime, "run_openai_compatible_chat_completion", fake_http)
    monkeypatch.setattr(bridge.subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("CLI should not run")))

    assert bridge.run_direct_hermes_raw("SECRET_PROMPT", group_id=781423661, strong=True) == "strong http answer"

    assert len(calls) == 1
    assert calls[0]["prompt"] == "SECRET_PROMPT"
    assert calls[0]["model"] == "strong-direct-model"
    assert calls[0]["base_url"] == "https://direct-chat.example.test/v1"
    assert calls[0]["api_key_env"] == "DIRECT_TEXT_API_KEY"
    rendered_logs = repr(logs)
    assert "SECRET_PROMPT" not in rendered_logs
    assert "strong-direct-model" not in rendered_logs
    assert "https://direct-chat.example.test" not in rendered_logs
    assert "DIRECT_TEXT_API_KEY" not in rendered_logs


def test_text_http_client_is_reused_for_direct_http_calls(monkeypatch):
    bridge = load_bridge_module()
    bridge.HERMES_TIMEOUT = 5
    bridge.MAX_REPLY_CHARS = 300
    calls = []

    def fake_http(prompt, **kwargs):
        calls.append({"prompt": prompt, **kwargs})
        return {"ok": True, "text": "direct answer", "reason": ""}

    monkeypatch.setattr(bridge.hermes_runtime, "run_openai_compatible_chat_completion", fake_http)

    try:
        first = bridge.run_text_http_result(
            "prompt one",
            config={
                "model": "custom-chat-model",
                "provider": "custom",
                "base_url": "https://chat.example.test/v1",
                "api_key_env": "TEXT_API_KEY",
            },
            group_id=781423661,
            purpose="direct_reply",
        )
        second = bridge.run_text_http_result(
            "prompt two",
            config={
                "model": "custom-chat-model",
                "provider": "custom",
                "base_url": "https://chat.example.test/v1",
                "api_key_env": "TEXT_API_KEY",
            },
            group_id=781423661,
            purpose="direct_reply",
        )
    finally:
        bridge.close_text_http_client()

    assert first["text"] == "direct answer"
    assert second["text"] == "direct answer"
    assert len(calls) == 2
    assert calls[0]["client"] is calls[1]["client"]
    assert calls[0]["client"].is_closed is True


def test_run_hermes_uses_direct_http_fallback_without_group_session(monkeypatch):
    bridge = load_bridge_module()
    bridge.HERMES_BIN = "hermes"
    bridge.HERMES_MODEL = "primary-model"
    bridge.HERMES_PROVIDER = "deepseek"
    bridge.HERMES_PROVIDER_BASE_URL = ""
    bridge.HERMES_API_KEY_ENV = ""
    bridge.HERMES_MODEL_BY_GROUP = {}
    bridge.HERMES_PROVIDER_BY_GROUP = {}
    bridge.HERMES_FALLBACK_ENABLED = True
    bridge.HERMES_FALLBACK_MODEL = "fallback-model"
    bridge.HERMES_FALLBACK_PROVIDER = "custom"
    bridge.HERMES_FALLBACK_PROVIDER_BASE_URL = "https://fallback.example.test/v1"
    bridge.HERMES_FALLBACK_API_KEY_ENV = "FALLBACK_TEXT_API_KEY"
    bridge.HERMES_GROUP_SESSIONS_ENABLED = True
    bridge.HERMES_SESSION_AUTOCOMPACT_ENABLED = False
    cli_calls = []
    http_calls = []

    class FakeFailed:
        returncode = 1
        stdout = ""
        stderr = "down"

    def fake_run(cmd, **kwargs):
        cli_calls.append(cmd)
        return FakeFailed()

    def fake_http(prompt, **kwargs):
        http_calls.append({"prompt": prompt, **kwargs})
        return {"ok": True, "text": "fallback via http", "reason": ""}

    monkeypatch.setattr(bridge.subprocess, "run", fake_run)
    monkeypatch.setattr(bridge.hermes_runtime, "run_openai_compatible_chat_completion", fake_http)

    assert bridge.run_hermes_raw("prompt", group_id=781423661) == "fallback via http"

    assert len(cli_calls) == 1
    assert "--continue" in cli_calls[0]
    assert len(http_calls) == 1
    assert http_calls[0]["base_url"] == "https://fallback.example.test/v1"
    assert http_calls[0]["api_key_env"] == "FALLBACK_TEXT_API_KEY"


def test_run_hermes_skips_fallback_when_same_after_provider_normalization(monkeypatch):
    bridge = load_bridge_module()
    bridge.HERMES_BIN = "hermes"
    bridge.HERMES_MODEL = "deepseekv4flash"
    bridge.HERMES_PROVIDER = "deepseek"
    bridge.HERMES_PROVIDER_BASE_URL = ""
    bridge.HERMES_API_KEY_ENV = ""
    bridge.HERMES_MODEL_BY_GROUP = {}
    bridge.HERMES_PROVIDER_BY_GROUP = {}
    bridge.HERMES_FALLBACK_ENABLED = True
    bridge.HERMES_FALLBACK_MODEL = "deepseekv4flash"
    bridge.HERMES_FALLBACK_PROVIDER = "官方"
    bridge.HERMES_FALLBACK_PROVIDER_BASE_URL = ""
    bridge.HERMES_FALLBACK_API_KEY_ENV = ""
    bridge.HERMES_GROUP_SESSIONS_ENABLED = False
    calls = []

    class FakeCompleted:
        returncode = 1
        stdout = ""
        stderr = "down"

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return FakeCompleted()

    monkeypatch.setattr(bridge.subprocess, "run", fake_run)

    result = bridge.run_hermes_raw_result("prompt", group_id=781423661)

    assert result["ok"] is False
    assert result["reason"] == "hermes_nonzero"
    assert len(calls) == 1
