import asyncio
import importlib.util
from pathlib import Path

import pytest
from fastapi import HTTPException

from qq_hermes_bridge import metrics

BRIDGE_PATH = Path(__file__).resolve().parents[1] / "bridge.py"


def load_bridge_module():
    spec = importlib.util.spec_from_file_location("bridge_under_test_metrics", BRIDGE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def setup_function():
    metrics.reset()
    metrics.configure(enabled=True, include_group_id_label=False)


def test_metrics_export_prometheus_text_and_omit_group_id_by_default():
    metrics.observe_runtime_stat("route_decision", {"route": "direct", "group_id": 975805598, "queued": True})
    metrics.observe_runtime_stat("direct_reply_result", {"ok": True, "replied": True, "e2e_ms": 2500, "group_id": 975805598})
    metrics.record_queue_size(975805598, "direct", 2)

    rendered = metrics.generate_latest()

    assert "# TYPE qq_hermes_messages_total counter" in rendered
    assert 'qq_hermes_messages_total{result="queued",route="direct"} 1' in rendered
    assert 'qq_hermes_replies_total{status="sent",type="direct"} 1' in rendered
    assert "qq_hermes_reply_duration_seconds_bucket" in rendered
    assert 'qq_hermes_queue_size{type="direct"} 2' in rendered
    assert "group_id" not in rendered


def test_metrics_include_group_id_only_when_enabled():
    metrics.configure(enabled=True, include_group_id_label=True)

    metrics.observe_runtime_stat("route_decision", {"route": "ignored", "group_id": 12345, "reason": "not_at_me"})

    rendered = metrics.generate_latest()

    assert 'group_id="12345"' in rendered
    assert 'result="not_at_me"' in rendered


def test_metrics_drop_unsafe_or_high_cardinality_labels_and_values():
    metrics._registry.counter(  # noqa: SLF001 - focused safety regression for the lightweight exporter
        "messages_total",
        "Message routing decisions by route and result.",
        1,
        route="direct",
        result="queued",
        user_hash="abc123",
        token="secret-token",
        url="https://secret.example/path",
    )
    metrics._registry.counter(  # noqa: SLF001
        "errors_total",
        "Errors observed by bridge component.",
        1,
        component="onebot",
        error_type="https://secret.example/path?token=abc",
    )

    rendered = metrics.generate_latest()

    assert "abc123" not in rendered
    assert "secret-token" not in rendered
    assert "secret.example" not in rendered
    assert "token" not in rendered
    assert 'error_type="unknown"' in rendered


def test_bridge_metrics_endpoint_returns_plaintext():
    bridge = load_bridge_module()
    bridge.metrics.reset()
    bridge.metrics.configure(enabled=True, include_group_id_label=False)
    bridge.PROMETHEUS_ENABLED = True
    bridge.runtime_route_decision("direct", group_id=975805598, queued=True)

    response = asyncio.run(bridge.prometheus_metrics())
    body = response.body.decode("utf-8")

    assert response.media_type.startswith("text/plain")
    assert "qq_hermes_messages_total" in body
    assert "group_id" not in body


def test_bridge_metrics_endpoint_can_be_disabled():
    bridge = load_bridge_module()
    bridge.PROMETHEUS_ENABLED = False

    with pytest.raises(HTTPException) as exc:
        asyncio.run(bridge.prometheus_metrics())

    assert exc.value.status_code == 404
