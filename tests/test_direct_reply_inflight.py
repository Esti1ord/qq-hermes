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


def make_at_event(text="Esti 问题", group_id=975805598, user_id=111, nickname="群友", self_id=3975680980, message_id=1):
    return {
        "post_type": "message",
        "message_type": "group",
        "group_id": group_id,
        "user_id": user_id,
        "self_id": self_id,
        "message_id": message_id,
        "sender": {"nickname": nickname},
        "message": [
            {"type": "at", "data": {"qq": str(self_id)}},
            {"type": "text", "data": {"text": text}},
        ],
    }


def configure_bridge(bridge):
    bridge.MIN_SECONDS_BETWEEN_REPLIES = 0.0
    bridge.USER_COOLDOWN_SECONDS = 0.0
    bridge.MAX_PENDING_DIRECT_REPLIES = 20
    bridge.PROACTIVE_RATE_LIMIT_MAX_REPLIES = 6
    bridge._recent_messages_by_group.clear()
    bridge._last_user_reply_at.clear()
    bridge._recent_messages.clear()
    bridge._processed_event_keys.clear()
    bridge._processed_event_key_set.clear()
    bridge._proactive_inflight_groups.clear()
    if hasattr(bridge, "_direct_reply_inflight_groups"):
        bridge._direct_reply_inflight_groups.clear()
    if hasattr(bridge, "_reply_queue_by_group"):
        bridge._reply_queue_by_group.clear()
    if hasattr(bridge, "_reply_workers_by_group"):
        bridge._reply_workers_by_group.clear()
    if hasattr(bridge, "_outbound_inflight_by_group"):
        bridge._outbound_inflight_by_group.clear()


class FakeRequest:
    def __init__(self, event):
        self.event = event

    async def json(self):
        return self.event


def test_same_group_direct_replies_are_queued_and_drained_sequentially(monkeypatch):
    bridge = load_bridge_module()
    configure_bridge(bridge)
    calls = []
    outputs = iter(["第一个回答", "第二个回答", "第三个回答"])
    sent = []

    def fake_run_hermes(prompt, group_id=None, use_group_session=True):
        calls.append(prompt)
        return next(outputs)

    async def fake_send(group_id, message):
        sent.append((group_id, message))
        return {"ok": True}

    monkeypatch.setattr(bridge, "run_hermes_raw", fake_run_hermes)
    monkeypatch.setattr(bridge, "send_group_msg", fake_send)

    async def run_three():
        results = await asyncio.gather(
            bridge.onebot_event(FakeRequest(make_at_event(text="Esti 第一个问题", user_id=1, message_id=101))),
            bridge.onebot_event(FakeRequest(make_at_event(text="Esti 第二个问题", user_id=2, message_id=102))),
            bridge.onebot_event(FakeRequest(make_at_event(text="Esti 第三个问题", user_id=3, message_id=103))),
        )
        await bridge.wait_reply_worker(975805598)
        return results

    results = asyncio.run(run_three())

    assert all(r["queued"] is True for r in results)
    assert len(calls) == 3
    assert sent == [(975805598, "[CQ:reply,id=101]第一个回答"), (975805598, "[CQ:reply,id=102]第二个回答"), (975805598, "[CQ:reply,id=103]第三个回答")]


def test_same_user_burst_is_queued_while_direct_worker_active(monkeypatch):
    bridge = load_bridge_module()
    configure_bridge(bridge)
    bridge.USER_COOLDOWN_SECONDS = 20.0
    calls = []
    release_first = asyncio.Event()
    sent = []

    def fake_run_hermes_raw(prompt, group_id=None, use_group_session=True):
        calls.append(prompt)
        if len(calls) == 1:
            import time
            deadline = time.time() + 1.0
            while not release_first.is_set() and time.time() < deadline:
                time.sleep(0.01)
            return "第一个回答"
        return "第二个回答"

    async def fake_send(group_id, message):
        sent.append((group_id, message))
        return {"ok": True}

    monkeypatch.setattr(bridge, "run_hermes_raw", fake_run_hermes_raw)
    monkeypatch.setattr(bridge, "send_group_msg", fake_send)

    async def run_two():
        first_task = asyncio.create_task(bridge.onebot_event(FakeRequest(make_at_event(text="Esti 第一个问题", user_id=1, message_id=801))))
        await asyncio.sleep(0.05)
        second = await bridge.onebot_event(FakeRequest(make_at_event(text="Esti 第二个问题", user_id=1, message_id=802)))
        release_first.set()
        first = await first_task
        await bridge.wait_reply_worker(975805598)
        return first, second

    first, second = asyncio.run(run_two())

    assert first["queued"] is True
    assert second["queued"] is True
    assert len(calls) == 2
    assert sent == [(975805598, "[CQ:reply,id=801]第一个回答"), (975805598, "[CQ:reply,id=802]第二个回答")]


def test_same_user_sequential_direct_questions_are_not_cooldown_suppressed(monkeypatch):
    bridge = load_bridge_module()
    configure_bridge(bridge)
    bridge.USER_COOLDOWN_SECONDS = 60.0
    calls = []
    outputs = iter(["第一次回答", "第二次回答"])
    sent = []

    def fake_run_hermes_raw(prompt, group_id=None, use_group_session=True):
        calls.append(prompt)
        return next(outputs)

    async def fake_send(group_id, message):
        sent.append((group_id, message))
        return {"ok": True}

    monkeypatch.setattr(bridge, "run_hermes_raw", fake_run_hermes_raw)
    monkeypatch.setattr(bridge, "send_group_msg", fake_send)

    async def run_two():
        first = await bridge.onebot_event(FakeRequest(make_at_event(text="Esti 第一次", user_id=1, message_id=9011)))
        await bridge.wait_reply_worker(975805598)
        second = await bridge.onebot_event(FakeRequest(make_at_event(text="Esti 第二次", user_id=1, message_id=9012)))
        await bridge.wait_reply_worker(975805598)
        return first, second

    first, second = asyncio.run(run_two())

    assert first["queued"] is True
    assert second["queued"] is True
    assert len(calls) == 2
    assert sent == [(975805598, "[CQ:reply,id=9011]第一次回答"), (975805598, "[CQ:reply,id=9012]第二次回答")]


def test_process_direct_reply_intent_can_run_without_queue_wrapper(monkeypatch):
    bridge = load_bridge_module()
    configure_bridge(bridge)
    sent = []

    monkeypatch.setattr(bridge, "run_hermes_raw", lambda prompt, group_id=None, use_group_session=True, purpose="unknown": "直接回答")

    async def fake_send(group_id, message):
        sent.append((group_id, message))
        return {"ok": True}

    monkeypatch.setattr(bridge, "send_group_msg", fake_send)
    event = make_at_event(text="Esti 单独处理", user_id=3, message_id=501)

    result = asyncio.run(bridge.process_direct_reply_intent(975805598, {"kind": "direct", "event": event, "user_text": "Esti 单独处理", "trigger": "at"}))

    assert result["replied"] is True
    assert result["trigger"] == "at"
    assert sent == [(975805598, "[CQ:reply,id=501]直接回答")]


def test_direct_reply_empty_hermes_output_sends_visible_failure_notice(monkeypatch):
    bridge = load_bridge_module()
    configure_bridge(bridge)
    sent = []

    monkeypatch.setattr(bridge, "run_hermes_raw", lambda prompt, group_id=None, use_group_session=True: "")

    async def fake_send(group_id, message):
        sent.append((group_id, message))
        return {"ok": True}

    monkeypatch.setattr(bridge, "send_group_msg", fake_send)
    event = make_at_event(text="Esti 空输出问题", user_id=1, message_id=301)

    result = asyncio.run(bridge.process_direct_reply_intent(975805598, {"kind": "direct", "event": event, "user_text": "Esti 空输出问题", "trigger": "at"}))

    assert result["replied"] is False
    assert result["generation_failed"] is True
    assert result["failure_notice_sent"] is True
    assert result["error"] == "direct_hermes_empty"
    assert sent == [(975805598, "[CQ:reply,id=301][CQ:at,qq=1] 稍后重试一下")]
    assert "机器人，正在生成回复" not in bridge.format_recent_context(975805598)


def test_direct_reply_empty_first_output_retries_without_group_session(monkeypatch):
    bridge = load_bridge_module()
    configure_bridge(bridge)
    calls = []
    outputs = iter(["", "重试后回答"])
    sent = []

    def fake_run_hermes_raw(prompt, group_id=None, use_group_session=True, purpose="unknown"):
        calls.append({"prompt": prompt, "group_id": group_id, "use_group_session": use_group_session, "purpose": purpose})
        return next(outputs)

    async def fake_send(group_id, message):
        sent.append((group_id, message))
        return {"ok": True}

    monkeypatch.setattr(bridge, "run_hermes_raw", fake_run_hermes_raw)
    monkeypatch.setattr(bridge, "send_group_msg", fake_send)
    event = make_at_event(text="Esti 空输出后重试", user_id=1, message_id=304)

    result = asyncio.run(bridge.process_direct_reply_intent(975805598, {"kind": "direct", "event": event, "user_text": "Esti 空输出后重试", "trigger": "at"}))

    assert result["replied"] is True
    assert result.get("generation_failed") is not True
    assert len(calls) == 2
    assert calls[0]["purpose"] == "direct_reply"
    assert calls[0]["use_group_session"] is True
    assert calls[1]["purpose"] == "direct_reply_retry"
    assert calls[1]["use_group_session"] is False
    assert "必须输出一条" in calls[1]["prompt"]
    assert sent == [(975805598, "[CQ:reply,id=304]重试后回答")]


def test_direct_reply_fallback_like_successful_output_is_not_suppressed(monkeypatch):
    bridge = load_bridge_module()
    configure_bridge(bridge)
    sent = []

    monkeypatch.setattr(bridge, "run_hermes_raw", lambda prompt, group_id=None, use_group_session=True: "这下没处理好 先缓一下")

    async def fake_send(group_id, message):
        sent.append((group_id, message))
        return {"ok": True}

    monkeypatch.setattr(bridge, "send_group_msg", fake_send)
    event = make_at_event(text="Esti fallback 问题", user_id=1, message_id=302)

    result = asyncio.run(bridge.process_direct_reply_intent(975805598, {"kind": "direct", "event": event, "user_text": "Esti fallback 问题", "trigger": "at"}))

    assert result["replied"] is True
    assert sent == [(975805598, "[CQ:reply,id=302]这下没处理好 先缓一下")]


def test_direct_reply_same_as_recent_bot_wording_is_not_suppressed(monkeypatch):
    bridge = load_bridge_module()
    configure_bridge(bridge)
    sent = []

    bridge.remember_bot_reply(975805598, "这群今天像集体低电量", 3975680980)
    monkeypatch.setattr(bridge, "run_hermes_raw", lambda prompt, group_id=None, use_group_session=True: "这群今天像集体低电量")

    async def fake_send(group_id, message):
        sent.append((group_id, message))
        return {"ok": True}

    monkeypatch.setattr(bridge, "send_group_msg", fake_send)
    event = make_at_event(text="Esti 刚才那句再说一下", user_id=1, message_id=303)

    result = asyncio.run(bridge.process_direct_reply_intent(975805598, {"kind": "direct", "event": event, "user_text": "Esti 刚才那句再说一下", "trigger": "at"}))

    assert result["replied"] is True
    assert sent == [(975805598, "[CQ:reply,id=303]这群今天像集体低电量")]


def test_failed_direct_reply_generation_drains_next_queued_reply(monkeypatch):
    bridge = load_bridge_module()
    configure_bridge(bridge)
    outputs = iter(["", "", "恢复后的回答"])
    calls = []
    sent = []

    def fake_run_hermes_raw(prompt, group_id=None, use_group_session=True, purpose="unknown"):
        calls.append({"prompt": prompt, "use_group_session": use_group_session, "purpose": purpose})
        return next(outputs)

    async def fake_send(group_id, message):
        sent.append((group_id, message))
        return {"ok": True}

    monkeypatch.setattr(bridge, "run_hermes_raw", fake_run_hermes_raw)
    monkeypatch.setattr(bridge, "send_group_msg", fake_send)

    async def run_two():
        first = await bridge.onebot_event(FakeRequest(make_at_event(text="Esti 会空的问题", user_id=1, message_id=811)))
        second = await bridge.onebot_event(FakeRequest(make_at_event(text="Esti 后续问题", user_id=2, message_id=812)))
        await bridge.wait_reply_worker(975805598)
        return first, second

    first, second = asyncio.run(run_two())

    assert first["queued"] is True
    assert second["queued"] is True
    assert len(calls) == 3
    assert calls[0]["purpose"] == "direct_reply"
    assert calls[1]["purpose"] == "direct_reply_retry"
    assert calls[1]["use_group_session"] is False
    assert calls[2]["purpose"] == "direct_reply"
    assert sent == [(975805598, "[CQ:reply,id=811][CQ:at,qq=1] 稍后重试一下"), (975805598, "[CQ:reply,id=812]恢复后的回答")]


def test_repeated_direct_generation_failures_are_not_duplicate_suppressed(monkeypatch):
    bridge = load_bridge_module()
    configure_bridge(bridge)
    sent = []

    monkeypatch.setattr(bridge, "run_hermes_raw", lambda *args, **kwargs: "")

    async def fake_send(group_id, message):
        sent.append((group_id, message))
        return {"ok": True}

    monkeypatch.setattr(bridge, "send_group_msg", fake_send)

    async def run_two():
        await asyncio.gather(
            bridge.onebot_event(FakeRequest(make_at_event(text="Esti 第一个失败", user_id=1, message_id=901))),
            bridge.onebot_event(FakeRequest(make_at_event(text="Esti 第二个失败", user_id=2, message_id=902))),
        )
        await bridge.wait_reply_worker(975805598)

    asyncio.run(run_two())

    assert sent == [
        (975805598, "[CQ:reply,id=901][CQ:at,qq=1] 稍后重试一下"),
        (975805598, "[CQ:reply,id=902][CQ:at,qq=2] 稍后重试一下"),
    ]


def test_direct_priority_drains_before_proactive_backlog(monkeypatch):
    bridge = load_bridge_module()
    configure_bridge(bridge)
    sent = []

    monkeypatch.setattr(bridge, "run_hermes_raw", lambda *args, **kwargs: "直接回答")
    monkeypatch.setattr(bridge, "run_proactive_reply", lambda event, reasons: f"主动回答 {event.get('user_id')}")

    async def fake_send(group_id, message):
        sent.append((group_id, message))
        return {"ok": True}

    monkeypatch.setattr(bridge, "send_group_msg", fake_send)
    bridge.enqueue_reply_intent(975805598, {"kind": "proactive", "event": make_at_event(user_id=10, message_id=10), "proactive": {"score": 20, "reasons": ["hot"]}})
    bridge.enqueue_reply_intent(975805598, {"kind": "direct", "event": make_at_event(user_id=1, message_id=11), "user_text": "Esti 直接问题", "trigger": "at"})

    asyncio.run(bridge.process_reply_intent(975805598, {"kind": "direct"}))
    asyncio.run(bridge.process_reply_intent(975805598, {"kind": "proactive"}))

    assert sent == [(975805598, "[CQ:reply,id=11]直接回答"), (975805598, "主动回答 10")]


def test_send_group_msg_rate_limited_serializes_concurrent_sends(monkeypatch):
    bridge = load_bridge_module()
    configure_bridge(bridge)
    bridge.MIN_SECONDS_BETWEEN_REPLIES = 2.0
    bridge._last_reply_at = 100.0
    now = {"value": 101.0}
    sleeps = []
    sent = []

    monkeypatch.setattr(bridge.time, "time", lambda: now["value"])

    async def fake_sleep(delay):
        sleeps.append(delay)
        now["value"] += delay

    async def fake_send(group_id, message):
        sent.append((group_id, message, now["value"]))
        return {"status": "ok", "retcode": 0}

    monkeypatch.setattr(bridge.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(bridge, "send_group_msg", fake_send)

    async def run_two():
        return await asyncio.gather(
            bridge.send_group_msg_rate_limited(1, "one"),
            bridge.send_group_msg_rate_limited(2, "two"),
        )

    results = asyncio.run(run_two())

    assert results == [({"status": "ok", "retcode": 0}, False), ({"status": "ok", "retcode": 0}, False)]
    assert sleeps == [1.0, 2.0]
    assert sent == [(1, "one", 102.0), (2, "two", 104.0)]




def test_direct_reply_emits_content_safe_performance_stats(monkeypatch):
    bridge = load_bridge_module()
    configure_bridge(bridge)
    bridge.RUNTIME_STATS_ENABLED = True
    bridge.PERF_OBS_ENABLED = True
    stats = []
    sent = []

    monkeypatch.setattr(bridge, "runtime_stat", lambda stat, **fields: stats.append({"stat": stat, **fields}))
    monkeypatch.setattr(bridge, "run_hermes_raw", lambda *args, **kwargs: "性能观测回答")

    async def fake_send(group_id, message):
        sent.append((group_id, message))
        return {"ok": True}

    monkeypatch.setattr(bridge, "send_group_msg", fake_send)

    async def run_once():
        result = await bridge.onebot_event(FakeRequest(make_at_event(text="Esti SECRET_CHAT_TEXT_123", user_id=77, message_id=777)))
        await bridge.wait_reply_worker(975805598)
        return result

    result = asyncio.run(run_once())

    assert result["queued"] is True
    assert sent == [(975805598, "[CQ:reply,id=777]性能观测回答")]
    names = {item["stat"] for item in stats}
    assert "interaction_received" in names
    assert "route_decision" in names
    assert "queue_event" in names
    assert "reply_intent_dequeued" in names
    assert "send_group_msg_rate_limited" in names
    assert "direct_reply_result" in names
    rendered = repr(stats)
    assert "SECRET_CHAT_TEXT_123" not in rendered
    direct_result = next(item for item in stats if item["stat"] == "direct_reply_result")
    assert direct_result["interaction_id"]
    assert direct_result["queue_wait_ms"] >= 0
    assert direct_result["e2e_ms"] >= 0


def test_send_group_msg_once_suppresses_concurrent_duplicate_inflight(monkeypatch):
    bridge = load_bridge_module()
    configure_bridge(bridge)
    release = asyncio.Event()
    sent = []

    async def fake_send(group_id, message):
        sent.append((group_id, message))
        await release.wait()
        return {"status": "ok", "retcode": 0}

    monkeypatch.setattr(bridge, "send_group_msg", fake_send)

    async def run_two():
        first_task = asyncio.create_task(bridge.send_group_msg_once(1, "重复消息"))
        await asyncio.sleep(0)
        second_task = asyncio.create_task(bridge.send_group_msg_once(1, "重复 消息"))
        await asyncio.sleep(0)
        release.set()
        return await asyncio.gather(first_task, second_task)

    first, second = asyncio.run(run_two())

    assert first == ({"status": "ok", "retcode": 0}, False)
    assert second == ({"ok": True, "suppressed": "duplicate_outbound"}, True)
    assert sent == [(1, "重复消息")]


def test_execute_route_action_schedules_reply_worker(monkeypatch):
    bridge = load_bridge_module()
    calls = []

    monkeypatch.setattr(bridge, "ensure_reply_worker", lambda group_id: calls.append(group_id) or {"ok": True, "queued": True, "worker": "scheduled"})

    result = asyncio.run(bridge.execute_route_action({"kind": "process_reply_intent", "group_id": 123, "intent": {"kind": "direct"}}))

    assert result == {"ok": True, "queued": True, "worker": "scheduled"}
    assert calls == [123]


def test_execute_route_action_returns_non_process_action_unchanged():
    bridge = load_bridge_module()
    action = {"ok": True, "ignored": "not_at_me"}

    assert asyncio.run(bridge.execute_route_action(action)) is action


def test_pending_bot_reply_context_is_replaced_after_success():
    bridge = load_bridge_module()
    configure_bridge(bridge)

    bridge.remember_message(make_at_event(text="Esti 第一个问题", user_id=1, message_id=301))
    bridge.remember_bot_pending_reply(975805598, "Esti 第一个问题", 3975680980)
    pending_context = bridge.format_recent_context(975805598)

    assert "机器人，正在生成回复" in pending_context
    assert "正在处理：Esti 第一个问题" in pending_context

    bridge.replace_last_bot_pending_reply(975805598, "第一个回答", 3975680980)
    final_context = bridge.format_recent_context(975805598)

    assert "机器人，正在生成回复" not in final_context
    assert "正在处理：Esti 第一个问题" not in final_context
    assert "发言人：Esti（QQ: 3975680980，机器人）" in final_context
    assert "内容：第一个回答" in final_context
