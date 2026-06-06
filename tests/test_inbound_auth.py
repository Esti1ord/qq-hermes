import asyncio
import importlib.util
from pathlib import Path

import pytest
from fastapi import HTTPException

BRIDGE_PATH = Path(__file__).resolve().parents[1] / "bridge.py"


def load_bridge_module():
    spec = importlib.util.spec_from_file_location("bridge_under_test", BRIDGE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeRequest:
    def __init__(self, event=None, headers=None):
        self._event = event or {}
        self.headers = headers or {}

    async def json(self):
        return self._event


def test_onebot_rejects_missing_inbound_token_when_configured():
    bridge = load_bridge_module()
    bridge.BRIDGE_INBOUND_TOKEN = "secret"

    with pytest.raises(HTTPException) as exc:
        asyncio.run(bridge.onebot_event(FakeRequest()))

    assert exc.value.status_code == 401


def test_onebot_allows_valid_inbound_token():
    bridge = load_bridge_module()
    bridge.BRIDGE_INBOUND_TOKEN = "secret"
    event = {"post_type": "notice", "message_type": "group", "group_id": 123}

    result = asyncio.run(bridge.onebot_event(FakeRequest(event, {"Authorization": "Bearer secret"})))

    assert result == {"ok": True, "ignored": "not_group_message"}


def test_test_endpoint_rejects_missing_inbound_token_when_configured():
    bridge = load_bridge_module()
    bridge.BRIDGE_INBOUND_TOKEN = "secret"

    with pytest.raises(HTTPException) as exc:
        asyncio.run(bridge.test(FakeRequest(), bridge.TestRequest()))

    assert exc.value.status_code == 401


def test_test_endpoint_allows_valid_inbound_token(monkeypatch):
    bridge = load_bridge_module()
    bridge.BRIDGE_INBOUND_TOKEN = "secret"
    monkeypatch.setattr(bridge, "run_hermes", lambda prompt: "ok reply")

    result = asyncio.run(bridge.test(FakeRequest(headers={"X-Bridge-Token": "secret"}), bridge.TestRequest(text="hi")))

    assert result == {"ok": True, "reply": "ok reply"}


def test_health_is_minimal_without_auth_and_detailed_with_auth():
    bridge = load_bridge_module()
    bridge.BRIDGE_INBOUND_TOKEN = "secret"

    public = asyncio.run(bridge.health(FakeRequest()))
    detailed = asyncio.run(bridge.health(FakeRequest(headers={"Authorization": "Bearer secret"})))

    assert public == {"ok": True}
    assert detailed["ok"] is True
    assert detailed["target_group_id"] == bridge.TARGET_GROUP_ID
    assert detailed["allowed_group_count"] == len(bridge.ALLOWED_GROUP_IDS)
    assert "allowed_group_ids" not in detailed
    assert "onebot_http_url" not in detailed
