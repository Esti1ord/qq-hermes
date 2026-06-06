import asyncio
import importlib.util
from pathlib import Path

BRIDGE_PATH = Path(__file__).resolve().parents[1] / "bridge.py"


def load_bridge_module():
    spec = importlib.util.spec_from_file_location("bridge_under_test", BRIDGE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def make_event(group_id=975805598, user_id=111, nickname="群友", text="消息", self_id=3975680980):
    return {
        "post_type": "message",
        "message_type": "group",
        "group_id": group_id,
        "user_id": user_id,
        "self_id": self_id,
        "sender": {"nickname": nickname},
        "message": [{"type": "text", "data": {"text": text}}],
    }


def configure_bridge(bridge):
    bridge.PROACTIVE_ENABLED = True
    bridge.PROACTIVE_TRIGGER_THRESHOLD = 1.0
    bridge.PROACTIVE_TRIGGER_THRESHOLDS_BY_GROUP = {}
    bridge.PROACTIVE_GROUP_COOLDOWN_SECONDS = 0.0
    bridge.MIN_SECONDS_BETWEEN_REPLIES = 0.0
    bridge.PROACTIVE_NAME_TRIGGERS = ["Esti", "estilord", "Estilord", "Esti1ord", "机器人", "bot", "小E"]
    bridge._recent_messages_by_group.clear()
    bridge._recent_messages.clear()
    if hasattr(bridge, "_processed_event_keys"):
        bridge._processed_event_keys.clear()
    if hasattr(bridge, "_processed_event_key_set"):
        bridge._processed_event_key_set.clear()
    if hasattr(bridge, "_proactive_inflight_groups"):
        bridge._proactive_inflight_groups.clear()
    if hasattr(bridge, "_proactive_reply_times_by_group"):
        bridge._proactive_reply_times_by_group.clear()
    if hasattr(bridge, "_reply_queue_by_group"):
        bridge._reply_queue_by_group.clear()
    if hasattr(bridge, "_reply_workers_by_group"):
        bridge._reply_workers_by_group.clear()
    bridge._proactive_state_by_group.clear()
    bridge._recent_activity_by_group.clear()


async def run_event_and_drain(bridge, request, group_id=975805598):
    result = await bridge.onebot_event(request)
    await bridge.wait_reply_worker(group_id)
    return result


def test_proactive_reply_is_recorded_as_bot_context(monkeypatch):
    bridge = load_bridge_module()
    configure_bridge(bridge)
    sent = []
    monkeypatch.setattr(bridge, "run_hermes_raw", lambda prompt, *args, **kwargs: "这群今天像集体低电量。")

    async def fake_send(group_id, message):
        sent.append((group_id, message))
        return {"ok": True, "status": "ok"}

    monkeypatch.setattr(bridge, "send_group_msg", fake_send)

    class FakeRequest:
        async def json(self):
            event = make_event(text="精神状态不太行")
            event["message_id"] = 5001
            return event

    result = asyncio.run(run_event_and_drain(bridge, FakeRequest()))

    assert result["queued"] is True
    assert sent == [(975805598, "这群今天像集体低电量")]
    context = bridge.format_recent_context(975805598)
    assert "发言人：Esti（QQ: 3975680980，机器人）" in context
    assert "内容：这群今天像集体低电量" in context


def test_direct_reply_is_recorded_as_bot_context(monkeypatch):
    bridge = load_bridge_module()
    configure_bridge(bridge)
    sent = []
    monkeypatch.setattr(bridge, "run_hermes_raw", lambda prompt, *args, **kwargs: "能 已经正常说话了")

    async def fake_send(group_id, message):
        sent.append((group_id, message))
        return {"ok": True, "status": "ok"}

    monkeypatch.setattr(bridge, "send_group_msg", fake_send)

    class FakeRequest:
        async def json(self):
            event = make_event(user_id=1001, nickname="A", text="Esti 能不能正常说话了")
            event["message_id"] = 5002
            event["message"] = [
                {"type": "at", "data": {"qq": str(event["self_id"])}},
                {"type": "text", "data": {"text": "Esti 能不能正常说话了"}},
            ]
            return event

    result = asyncio.run(run_event_and_drain(bridge, FakeRequest()))

    assert result["queued"] is True
    assert sent == [(975805598, "[CQ:reply,id=5002]能 已经正常说话了")]
    context = bridge.format_recent_context(975805598)
    assert "发言人：A（QQ: 1001）" in context
    assert "内容：Esti 能不能正常说话了" in context
    assert "发言人：Esti（QQ: 3975680980，机器人）" in context
    assert "内容：能 已经正常说话了" in context
