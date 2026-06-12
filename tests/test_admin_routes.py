import asyncio
import importlib.util
import json
from collections import deque
from pathlib import Path

import pytest
from fastapi import HTTPException

BRIDGE_PATH = Path(__file__).resolve().parents[1] / "bridge.py"


class FakeClient:
    def __init__(self, host: str):
        self.host = host


class FakeRequest:
    def __init__(self, *, host: str = "127.0.0.1", headers=None):
        self.client = FakeClient(host)
        self.headers = headers or {}


def load_bridge_module():
    spec = importlib.util.spec_from_file_location("bridge_under_test_admin", BRIDGE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_admin_html_endpoint_renders_local_page():
    bridge = load_bridge_module()

    route_paths = {route.path for route in bridge.app.routes}
    response = asyncio.run(bridge.admin_page(FakeRequest()))
    body = response.body.decode("utf-8")

    assert "/admin" in route_paths
    assert "/admin/state" in route_paths
    assert response.media_type == "text/html"
    assert "QQ Hermes 本地数据查看" in body
    assert "fetch('/admin/state'" in body
    assert "<script src=" not in body
    assert "<link rel=" not in body


def test_admin_endpoints_are_local_only_unless_token_authorized():
    bridge = load_bridge_module()
    bridge.BRIDGE_INBOUND_TOKEN = "secret"

    local_response = asyncio.run(bridge.admin_page(FakeRequest(host="::1")))
    assert local_response.media_type == "text/html"

    with pytest.raises(HTTPException) as exc:
        asyncio.run(bridge.admin_state(FakeRequest(host="203.0.113.10")))
    assert exc.value.status_code == 403

    authorized_remote = asyncio.run(
        bridge.admin_state(
            FakeRequest(host="203.0.113.10", headers={"Authorization": "Bearer secret"}),
        )
    )
    assert authorized_remote["ok"] is True

def test_admin_state_json_shape_includes_runtime_model_and_context_overview():
    bridge = load_bridge_module()
    group_id = 123456789
    bridge.ALLOWED_GROUP_IDS = {group_id}
    bridge.TARGET_GROUP_ID = group_id
    bridge.HERMES_MODEL = "gpt-5.4"
    bridge.HERMES_PROVIDER = "官方"
    bridge.HERMES_MODEL_BY_GROUP = {group_id: "deepseekv4flash"}
    bridge.HERMES_PROVIDER_BY_GROUP = {}
    bridge._recent_messages_by_group[group_id] = deque([
        {"user_id": 10001, "name": "群友A", "text": "一条测试消息"},
        {"user_id": "bot", "name": "Esti", "role": "机器人", "text": "一条机器人回复"},
    ])
    bridge._context_summaries_by_group[group_id] = deque(["测试摘要一", "测试摘要二"])

    state = asyncio.run(bridge.admin_state(FakeRequest(), group_id))

    assert state["ok"] is True
    assert state["runtime"]["status"] == "running"
    assert state["runtime"]["target_group_id"] == group_id
    assert state["model_routing"]["primary"]["model"] == "gpt-5.4"
    assert state["model_routing"]["primary"]["provider"] == "官方"
    assert state["model_routing"]["selected_group"]["model"] == "deepseekv4flash"
    assert state["safety"]["raw_chat_hidden"] is True
    assert state["safety"]["prompt_text_hidden"] is True

    group = next(item for item in state["groups"] if item["group_id"] == group_id)
    assert group["context"]["recent_message_count"] == 2
    assert group["context"]["human_message_count"] == 1
    assert group["context"]["bot_message_count"] == 1
    assert group["context"]["summary_count"] == 2

    composition = state["context_composition"]
    assert composition["selected_group_id"] == group_id
    direct_sections = composition["direct"]["sections"]
    proactive_sections = composition["proactive"]["sections"]
    assert {section["key"] for section in direct_sections} >= {"current_message", "recent_context", "persona"}
    assert {section["key"] for section in proactive_sections} >= {"recent_context", "decision_strategy", "persona"}
    assert all("body" not in section for section in direct_sections + proactive_sections)
    assert all("text" not in section for section in direct_sections + proactive_sections)


def test_admin_state_excludes_sensitive_values_and_raw_content():
    bridge = load_bridge_module()
    group_id = 975805598
    raw_chat = "RAW_CHAT_SECRET_DO_NOT_EXPOSE"
    raw_summary = "RAW_SUMMARY_SECRET_DO_NOT_EXPOSE"
    raw_ocr = "RAW_OCR_SECRET_DO_NOT_EXPOSE"
    provider_url = "https://provider-secret.example/v1?token=secret-provider-token"
    image_url = "https://image-secret.example/private.png"
    api_env_name = "PRIMARY_OCR_MODEL_API_KEY_ENV"
    onebot_token = "secret-onebot-token-value"
    user_name = "SensitiveUserName"

    bridge.TARGET_GROUP_ID = group_id
    bridge.ALLOWED_GROUP_IDS = {group_id}
    bridge.HERMES_MODEL = "sk-secret-token-abcdef123456"
    bridge.HERMES_PROVIDER = provider_url
    bridge.HERMES_MODEL_BY_GROUP = {}
    bridge.HERMES_PROVIDER_BY_GROUP = {}
    bridge.OCR_PROVIDER = provider_url
    bridge.OCR_MODEL = "ocr-model"
    bridge.OCR_PROVIDER_BASE_URL = "https://ocr-secret.example/v1"
    bridge.OCR_API_KEY_ENV = api_env_name
    bridge.ONEBOT_ACCESS_TOKEN = onebot_token
    bridge.BRIDGE_INBOUND_TOKEN = "secret-bridge-token"
    bridge._recent_messages_by_group[group_id] = deque([
        {
            "user_id": 998877665544,
            "name": user_name,
            "text": raw_chat,
            "media_refs": [bridge.media.MediaRef(index=0, type="image", url=image_url, summary=raw_ocr)],
        }
    ])
    bridge._context_summaries_by_group[group_id] = deque([raw_summary])

    state = asyncio.run(bridge.admin_state(FakeRequest(), group_id))
    rendered = json.dumps(state, ensure_ascii=False, sort_keys=True)

    assert state["model_routing"]["primary"]["model"] == bridge.admin_view.REDACTED
    assert state["model_routing"]["primary"]["provider"] == bridge.admin_view.REDACTED
    assert state["ocr"]["provider"] == bridge.admin_view.REDACTED
    assert state["safety"]["provider_urls_hidden"] is True
    assert state["safety"]["api_env_hidden"] is True
    assert state["safety"]["ocr_text_hidden"] is True

    for forbidden in [
        raw_chat,
        raw_summary,
        raw_ocr,
        provider_url,
        "provider-secret.example",
        image_url,
        "image-secret.example",
        api_env_name,
        onebot_token,
        "secret-bridge-token",
        user_name,
        "998877665544",
    ]:
        assert forbidden not in rendered
