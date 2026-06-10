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


class FakeRequest:
    def __init__(self, event):
        self.event = event

    async def json(self):
        return self.event


def make_event(text="普通消息", *, at=False, group_id=975805598, user_id=111, message_id=1):
    message = []
    if at:
        message.append({"type": "at", "data": {"qq": "3975680980"}})
    message.append({"type": "text", "data": {"text": text}})
    return {
        "post_type": "message",
        "message_type": "group",
        "group_id": group_id,
        "user_id": user_id,
        "self_id": 3975680980,
        "message_id": message_id,
        "sender": {"nickname": "群友"},
        "message": message,
    }


def configure_bridge(bridge):
    bridge.MIN_SECONDS_BETWEEN_REPLIES = 0.0
    bridge.USER_COOLDOWN_SECONDS = 0.0
    bridge.PROACTIVE_ENABLED = False
    bridge.CONTENT_ANALYSIS_LOG_ENABLED = True
    bridge.CONTENT_ANALYSIS_ALLOWED_GROUP_IDS = set()
    bridge._recent_messages_by_group.clear()
    bridge._context_summaries_by_group.clear()
    bridge._recent_messages.clear()
    bridge._processed_event_keys.clear()
    bridge._processed_event_key_set.clear()
    bridge._reply_queue_by_group.clear()
    bridge._reply_workers_by_group.clear()
    bridge._recent_outbound_by_group.clear()
    bridge._outbound_inflight_by_group.clear()


def test_allowed_inbound_message_emits_content_analysis_record(monkeypatch):
    bridge = load_bridge_module()
    configure_bridge(bridge)
    records = []
    monkeypatch.setattr(bridge, "content_analysis_log", lambda kind, group_id, **fields: records.append({"kind": kind, "group_id": group_id, **fields}))

    result = asyncio.run(bridge.onebot_event(FakeRequest(make_event("今天聊火锅 token=secret", at=False, message_id=701))))

    assert result["ignored"] == "not_at_me"
    inbound = [r for r in records if r["kind"] == "inbound_message"]
    assert len(inbound) == 1
    assert inbound[0]["message"]["text"] == "今天聊火锅 [REDACTED]"
    assert inbound[0]["segment_types"] == {"text": 1}
    assert "raw_event" not in repr(inbound[0])


def test_direct_reply_analysis_records_user_context_and_final_reply(monkeypatch):
    bridge = load_bridge_module()
    configure_bridge(bridge)
    records = []
    sent = []

    monkeypatch.setattr(bridge, "content_analysis_log", lambda kind, group_id, **fields: records.append({"kind": kind, "group_id": group_id, **fields}))
    monkeypatch.setattr(bridge, "run_hermes_raw", lambda *args, **kwargs: "可以，先看最近一句。")

    async def fake_send(group_id, message):
        sent.append((group_id, message))
        return {"ok": True}

    monkeypatch.setattr(bridge, "send_group_msg", fake_send)
    event = make_event("Esti 你怎么看 Cookie: p_skey=secret", at=True, message_id=702)

    result = asyncio.run(bridge.process_direct_reply_intent(975805598, {"kind": "direct", "event": event, "user_text": "Esti 你怎么看 Cookie: p_skey=secret", "trigger": "at"}))

    assert result["replied"] is True
    assert sent == [(975805598, "[CQ:reply,id=702]可以，先看最近一句。")]
    kinds = [r["kind"] for r in records]
    assert "direct_generation_start" in kinds
    assert "direct_reply_sent" in kinds
    start = next(r for r in records if r["kind"] == "direct_generation_start")
    sent_record = next(r for r in records if r["kind"] == "direct_reply_sent")
    assert "p_skey" not in start["user_text"]["text"]
    assert sent_record["reply"]["text"] == "可以，先看最近一句。"
    rendered = repr(records)
    assert "prompt" not in rendered
    assert "stdout" not in rendered
    assert "stderr" not in rendered
