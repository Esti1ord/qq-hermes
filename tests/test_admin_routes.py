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


class FakeTask:
    def __init__(self, *, done: bool):
        self._done = done

    def done(self):
        return self._done


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
    assert "/admin/memory" in route_paths
    assert "/admin/memory/add" in route_paths
    assert "/admin/memory/delete" in route_paths
    assert "/admin/memory/strengthen" in route_paths
    assert response.media_type == "text/html"
    assert "QQ Hermes 本地数据查看" in body
    assert "输入给机器人的提示词组成概览" in body
    assert "实时连接状态" in body
    assert "成功刷新次数" in body
    assert "查看群" in body
    assert "id=\"group-select\"" in body
    assert "/admin/state?${query}" in body
    assert "指标趋势" in body
    assert "回复错误原因" in body
    assert "id=\"reply-error-reasons\"" in body
    assert "暂无回复错误" in body
    assert "renderReplyErrorReasons(state)" in body
    assert "REPLY_ERROR_REASONS" not in body
    assert "记忆 / 自学习管理" in body
    assert "/admin/memory?${query}" in body
    assert "/admin/memory/add" in body
    assert "/admin/memory/delete" in body
    assert "/admin/memory/strengthen" in body
    assert "memory-add-form" in body
    assert "当前 /admin/state JSON（只读）" in body
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

    with pytest.raises(HTTPException) as exc:
        asyncio.run(bridge.admin_memory_list(FakeRequest(host="203.0.113.10")))
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
    bridge._ocr_inflight.clear()
    bridge._ocr_inflight["active-image"] = FakeTask(done=False)
    bridge._ocr_inflight["finished-image"] = FakeTask(done=True)
    bridge._ocr_context_tasks.clear()
    bridge._ocr_context_tasks.add(FakeTask(done=False))
    bridge._ocr_context_tasks.add(FakeTask(done=True))
    bridge._runtime_counters.clear()
    bridge._runtime_counters.update({
        "direct_generation_failures": "2",
        "direct_send_errors": 3,
        "send_errors": 5,
        "command_errors": 7,
        "hermes_errors": 11,
        "unrelated_errors": 100,
    })

    state = asyncio.run(bridge.admin_state(FakeRequest(), group_id))

    assert state["ok"] is True
    assert state["runtime"]["status"] == "running"
    assert state["selected_group_id"] == group_id
    assert state["runtime"]["target_group_id"] == group_id
    assert state["model_routing"]["primary"]["model"] == "gpt-5.4"
    assert state["model_routing"]["primary"]["provider"] == "官方"
    assert state["model_routing"]["selected_group"]["model"] == "deepseekv4flash"
    assert state["safety"]["raw_chat_hidden"] is True
    assert state["safety"]["prompt_text_hidden"] is True
    assert state["prompt_composition"] == state["context_composition"]
    assert state["ocr"]["status"]["inflight_count"] == 1
    assert state["ocr"]["status"]["context_task_count"] == 1
    assert "cache_entries" in state["ocr"]["status"]
    assert state["runtime"]["counters"]["unrelated_errors"] == 100
    assert state["reply_errors"]["total"] == 28
    assert state["reply_errors"]["reasons"] == [
        {"key": "direct_generation_failures", "label": "直接回复生成失败", "count": 2},
        {"key": "direct_send_errors", "label": "直接回复发送失败", "count": 3},
        {"key": "send_errors", "label": "群消息发送失败", "count": 5},
        {"key": "command_errors", "label": "命令处理错误", "count": 7},
        {"key": "hermes_errors", "label": "Hermes 模型调用错误", "count": 11},
    ]

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
    allowed_section_keys = {"key", "title", "source", "priority", "budget_chars", "summary", "metrics", "content_hidden"}
    assert all(set(section) <= allowed_section_keys for section in direct_sections + proactive_sections)
    assert all(section["content_hidden"] is True for section in direct_sections + proactive_sections)
    assert all("body" not in section for section in direct_sections + proactive_sections)
    assert all("text" not in section for section in direct_sections + proactive_sections)
    assert all(len(section["summary"]) <= 90 for section in direct_sections + proactive_sections)


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
    bridge.HERMES_FALLBACK_MODEL = "PRIMARY_OCR_MODEL_API_KEY"
    bridge.HERMES_FALLBACK_PROVIDER = "gateway.example"
    bridge.HERMES_PROVIDER_BY_GROUP = {group_id: "127.0.0.1:11434"}
    bridge.HERMES_MODEL_BY_GROUP = {}
    bridge.OCR_PROVIDER = provider_url
    bridge.OCR_MODEL = "ocr-model"
    bridge.OCR_FALLBACK_PROVIDER = "ocr-gateway.example"
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
        "PRIMARY_OCR_MODEL_API_KEY",
        "gateway.example",
        "ocr-gateway.example",
        "127.0.0.1:11434",
        user_name,
        "998877665544",
    ]:
        assert forbidden not in rendered


def test_admin_memory_mutation_endpoints_require_admin_access():
    bridge = load_bridge_module()
    bridge.BRIDGE_INBOUND_TOKEN = "secret"
    remote = FakeRequest(host="203.0.113.10")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(bridge.admin_memory_add(
            remote,
            bridge.AdminMemoryAddRequest(group_id=975805598, entry_type="memory", text="本地测试记忆"),
        ))
    assert exc.value.status_code == 403

    with pytest.raises(HTTPException) as exc:
        asyncio.run(bridge.admin_memory_delete(
            remote,
            bridge.AdminMemoryDeleteRequest(group_id=975805598, entry_id="manual:not-present", mode="disable"),
        ))
    assert exc.value.status_code == 403

    with pytest.raises(HTTPException) as exc:
        asyncio.run(bridge.admin_memory_strengthen(
            remote,
            bridge.AdminMemoryStrengthenRequest(group_id=975805598, entry_id="manual:not-present", amount=1),
        ))
    assert exc.value.status_code == 403


def configure_memory_admin_bridge(bridge, tmp_path, group_id=975805598):
    bridge.TARGET_GROUP_ID = group_id
    bridge.ALLOWED_GROUP_IDS = {group_id}
    bridge.GROUP_CONFIG_DIR = tmp_path
    bridge.SELF_LEARNING_CONFIG = bridge.self_learning.SelfLearningConfig(
        enabled=True,
        collect_enabled=True,
        inject_enabled=True,
        allowed_group_ids={group_id},
        min_message_chars=2,
        max_message_chars=120,
        max_samples_per_group=20,
        retention_days=30,
        max_prompt_chars=500,
        min_count_for_prompt=1,
        data_filename="self_learning.json",
    )


def test_admin_memory_list_uses_safe_serialization(tmp_path):
    bridge = load_bridge_module()
    group_id = 975805598
    configure_memory_admin_bridge(bridge, tmp_path, group_id)
    bridge.self_learning.collect_learning_sample(
        group_id,
        "笑死 这个梗可以保留",
        group_config_dir=tmp_path,
        config=bridge.SELF_LEARNING_CONFIG,
        now=1000,
    )

    state = asyncio.run(bridge.admin_memory_list(FakeRequest(), group_id))
    rendered = json.dumps(state, ensure_ascii=False, sort_keys=True)

    assert state["ok"] is True
    assert state["summary"]["total"] == 1
    entry = state["entries"][0]
    assert entry["id"].startswith("sample:")
    assert entry["type"] == "self_learning"
    assert entry["source"] == "self_learning"
    assert entry["status"] == "active"
    assert entry["preview"] == "笑死 这个梗可以保留"
    assert entry["operations"]["delete"] is True
    assert entry["operations"]["disable"] is True
    assert entry["operations"]["strengthen"] is True
    assert "998877665544" not in rendered
    assert "PRIMARY_CHAT_MODEL_API_KEY" not in rendered
    assert "https://" not in rendered


def test_admin_memory_list_redacts_raw_identifier_previews(tmp_path):
    bridge = load_bridge_module()
    group_id = 975805598
    configure_memory_admin_bridge(bridge, tmp_path, group_id)
    bridge.self_learning.save_learning_data_for_group(
        group_id,
        {
            "samples": [
                {"ts": 1000, "text": "群友 998877665544 的口头禅"},
            ],
            "manual_entries": [],
        },
        group_config_dir=tmp_path,
        config=bridge.SELF_LEARNING_CONFIG,
        now=1001,
    )

    state = asyncio.run(bridge.admin_memory_list(FakeRequest(), group_id))
    rendered = json.dumps(state, ensure_ascii=False, sort_keys=True)

    assert state["summary"]["total"] == 1
    assert state["entries"][0]["redacted"] is True
    assert state["entries"][0]["preview"] == bridge.admin_view.REDACTED
    assert "998877665544" not in rendered

    with pytest.raises(HTTPException) as exc:
        asyncio.run(bridge.admin_memory_strengthen(
            FakeRequest(),
            bridge.AdminMemoryStrengthenRequest(group_id=group_id, entry_id=state["entries"][0]["id"], amount=1),
        ))
    assert exc.value.status_code == 400
    assert "sensitive" in str(exc.value.detail)


def test_admin_memory_disable_preserves_generated_id_for_legacy_sample(tmp_path):
    bridge = load_bridge_module()
    group_id = 975805598
    configure_memory_admin_bridge(bridge, tmp_path, group_id)
    store = tmp_path / str(group_id) / "self_learning.json"
    store.parent.mkdir(parents=True)
    store.write_text(
        json.dumps({"version": 1, "group_id": group_id, "samples": [{"ts": 1000, "text": "  遗留  样例  "}]}),
        encoding="utf-8",
    )
    state = asyncio.run(bridge.admin_memory_list(FakeRequest(), group_id))
    entry_id = state["entries"][0]["id"]

    disabled = asyncio.run(bridge.admin_memory_delete(
        FakeRequest(),
        bridge.AdminMemoryDeleteRequest(group_id=group_id, entry_id=entry_id, mode="disable"),
    ))

    assert disabled["ok"] is True
    assert disabled["entry"]["id"] == entry_id
    assert disabled["entry"]["status"] == "disabled"


def test_admin_memory_add_disable_delete_and_strengthen(tmp_path):
    bridge = load_bridge_module()
    group_id = 975805598
    configure_memory_admin_bridge(bridge, tmp_path, group_id)

    add = asyncio.run(bridge.admin_memory_add(
        FakeRequest(),
        bridge.AdminMemoryAddRequest(
            group_id=group_id,
            entry_type="prompt_guidance",
            text="遇到求助先给结论 再给一句理由",
            weight=2.0,
        ),
    ))
    assert add["ok"] is True
    entry = add["entry"]
    assert entry["id"].startswith("manual:")
    assert entry["type"] == "prompt_guidance"
    assert entry["status"] == "active"
    assert entry["weight"] == 2.0

    strengthened = asyncio.run(bridge.admin_memory_strengthen(
        FakeRequest(),
        bridge.AdminMemoryStrengthenRequest(group_id=group_id, entry_id=entry["id"], amount=3),
    ))
    assert strengthened["ok"] is True
    assert strengthened["entry"]["reinforcement"] == 3
    assert strengthened["entry"]["weight"] == 5.0

    disabled = asyncio.run(bridge.admin_memory_delete(
        FakeRequest(),
        bridge.AdminMemoryDeleteRequest(group_id=group_id, entry_id=entry["id"], mode="disable"),
    ))
    assert disabled["ok"] is True
    assert disabled["action"] == "disabled"
    assert disabled["entry"]["status"] == "disabled"

    deleted = asyncio.run(bridge.admin_memory_delete(
        FakeRequest(),
        bridge.AdminMemoryDeleteRequest(group_id=group_id, entry_id=entry["id"], mode="delete"),
    ))
    assert deleted["ok"] is True
    assert deleted["action"] == "deleted"
    assert deleted["summary"]["total"] == 0


def test_admin_memory_rejects_sensitive_manual_input(tmp_path):
    bridge = load_bridge_module()
    group_id = 975805598
    configure_memory_admin_bridge(bridge, tmp_path, group_id)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(bridge.admin_memory_add(
            FakeRequest(),
            bridge.AdminMemoryAddRequest(
                group_id=group_id,
                entry_type="memory",
                text="保存 token sk-secret-token-abcdef123456",
            ),
        ))

    assert exc.value.status_code == 400
    assert "sensitive" in str(exc.value.detail)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(bridge.admin_memory_add(
            FakeRequest(),
            bridge.AdminMemoryAddRequest(
                group_id=group_id,
                entry_type="memory",
                text="群友 998877665544 的口头禅",
            ),
        ))

    assert exc.value.status_code == 400
    assert "raw identifier" in str(exc.value.detail)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(bridge.admin_memory_add(
            FakeRequest(),
            bridge.AdminMemoryAddRequest(
                group_id=group_id,
                entry_type="memory",
                text="普通本地记忆",
                weight=float("nan"),
            ),
        ))

    assert exc.value.status_code == 400
    assert "invalid weight" in str(exc.value.detail)


def test_admin_strengthened_sample_is_injected_but_disabled_sample_is_not(tmp_path):
    bridge = load_bridge_module()
    group_id = 975805598
    configure_memory_admin_bridge(bridge, tmp_path, group_id)
    bridge.self_learning.collect_learning_sample(
        group_id,
        "可强化的群内梗",
        group_config_dir=tmp_path,
        config=bridge.SELF_LEARNING_CONFIG,
        now=bridge.time.time(),
    )
    state = asyncio.run(bridge.admin_memory_list(FakeRequest(), group_id))
    sample_id = state["entries"][0]["id"]

    asyncio.run(bridge.admin_memory_strengthen(
        FakeRequest(),
        bridge.AdminMemoryStrengthenRequest(group_id=group_id, entry_id=sample_id, amount=1),
    ))
    context = bridge.self_learning_context_for_prompt(group_id)
    assert "可强化的群内梗" in context

    asyncio.run(bridge.admin_memory_delete(
        FakeRequest(),
        bridge.AdminMemoryDeleteRequest(group_id=group_id, entry_id=sample_id, mode="disable"),
    ))
    context = bridge.self_learning_context_for_prompt(group_id)
    assert "可强化的群内梗" not in context
