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


def configure_proactive(bridge):
    bridge.PROACTIVE_ENABLED = True
    bridge.PROACTIVE_TRIGGER_THRESHOLD = 16.0
    bridge.PROACTIVE_TRIGGER_THRESHOLDS_BY_GROUP = {}
    bridge.PROACTIVE_GROUP_COOLDOWN_SECONDS = 900.0
    bridge.PROACTIVE_DAILY_LIMIT_PER_GROUP = 8
    bridge.PROACTIVE_RATE_LIMIT_WINDOW_SECONDS = 60.0
    bridge.PROACTIVE_RATE_LIMIT_MAX_REPLIES = 6
    bridge.PROACTIVE_DECAY_PER_MINUTE = 1.0
    bridge.PROACTIVE_BURST_WINDOW_SECONDS = 120.0
    bridge.PROACTIVE_BURST_MESSAGE_THRESHOLD = 6
    bridge.PROACTIVE_BURST_USER_THRESHOLD = 3
    bridge.PROACTIVE_NAME_TRIGGERS = ["Esti", "estilord", "Estilord", "Esti1ord", "机器人", "bot", "小E"]
    bridge.PROACTIVE_TOPIC_KEYWORDS = ["精神状态", "吃什么", "南航", "中大", "联谊", "实习", "秋招", "保研", "考研", "游戏", "开黑"]
    bridge.PROACTIVE_LIGHT_KEYWORDS = ["笑死", "绷不住", "服了", "寄", "困", "累", "无聊"]
    bridge.PROACTIVE_NIGHT_SCORE_MULTIPLIER = 1.0
    bridge._proactive_state_by_group.clear()
    bridge._recent_activity_by_group.clear()
    if hasattr(bridge, "_processed_event_keys"):
        bridge._processed_event_keys.clear()
    if hasattr(bridge, "_proactive_inflight_groups"):
        bridge._proactive_inflight_groups.clear()
    if hasattr(bridge, "_proactive_reply_times_by_group"):
        bridge._proactive_reply_times_by_group.clear()
    if hasattr(bridge, "_reply_queue_by_group"):
        bridge._reply_queue_by_group.clear()
    if hasattr(bridge, "_reply_workers_by_group"):
        bridge._reply_workers_by_group.clear()


async def run_event_and_drain(bridge, request, group_id=975805598):
    result = await bridge.onebot_event(request)
    await bridge.wait_reply_worker(group_id)
    return result


def test_proactive_score_accumulates_from_topic_burst_question_and_multi_users():
    bridge = load_bridge_module()
    configure_proactive(bridge)

    events = [
        make_event(user_id=1, nickname="甲", text="今天精神状态不太行"),
        make_event(user_id=2, nickname="乙", text="笑死我也"),
        make_event(user_id=3, nickname="丙", text="有没有人救一下"),
        make_event(user_id=4, nickname="丁", text="这群怎么回事"),
    ]
    all_reasons = []
    result = None
    for i, event in enumerate(events):
        result = bridge.update_proactive_score(event, now=1000 + i * 10)
        all_reasons.extend(result["reasons"])

    assert result["score"] >= bridge.PROACTIVE_TRIGGER_THRESHOLD
    assert result["should_trigger"] is True
    assert "topic:精神状态" in all_reasons
    assert "light:笑死" in all_reasons
    assert "open_question" in all_reasons
    assert "multi_user" in all_reasons


def test_proactive_score_decays_over_time_and_is_group_scoped():
    bridge = load_bridge_module()
    configure_proactive(bridge)

    bridge.update_proactive_score(make_event(group_id=975805598, text="精神状态"), now=1000)
    first = bridge.proactive_state_for_group(975805598)["score"]
    bridge.update_proactive_score(make_event(group_id=975805598, text="普通消息"), now=1300)
    later = bridge.proactive_state_for_group(975805598)["score"]

    assert later < first + 1.0
    assert bridge.proactive_state_for_group(781423661)["score"] == 0.0


def test_proactive_trigger_blocked_by_cooldown_only():
    bridge = load_bridge_module()
    configure_proactive(bridge)
    bridge.PROACTIVE_GROUP_COOLDOWN_SECONDS = 20.0
    state = bridge.proactive_state_for_group(975805598)
    state["score"] = 100.0
    state["last_proactive_at"] = 1000.0

    event = make_event(text="机器人怎么不说话")
    result = bridge.update_proactive_score(event, now=1019.0)
    assert result["should_trigger"] is False
    assert result["blocked"] == "group_cooldown"

    result = bridge.update_proactive_score(event, now=1020.1)
    assert result["blocked"] == ""
    assert result["should_trigger"] is True


def test_proactive_group_cooldown_does_not_block_direct_or_commands(monkeypatch):
    bridge = load_bridge_module()
    configure_proactive(bridge)
    bridge.PROACTIVE_GROUP_COOLDOWN_SECONDS = 10.0
    bridge.MIN_SECONDS_BETWEEN_REPLIES = 0.0
    bridge.proactive_state_for_group(975805598)["last_proactive_at"] = 1000.0
    sent = []

    async def fake_send(group_id, message):
        sent.append((group_id, message))
        return {"ok": True, "status": "ok"}

    monkeypatch.setattr(bridge, "send_group_msg", fake_send)
    monkeypatch.setattr(bridge, "run_hermes_raw", lambda *args, **kwargs: "直回不进主动冷却")

    class DirectRequest:
        async def json(self):
            event = make_event(text="[CQ:at,qq=3975680980] 还在吗")
            event["message_id"] = 2026060301
            event["message"] = [
                {"type": "at", "data": {"qq": "3975680980"}},
                {"type": "text", "data": {"text": " 还在吗"}},
            ]
            return event

    result = asyncio.run(run_event_and_drain(bridge, DirectRequest()))

    assert result["queued"] is True
    assert sent == [(975805598, "[CQ:reply,id=2026060301]直回不进主动冷却")]


def test_proactive_prompt_is_separate_and_context_first():
    bridge = load_bridge_module()
    configure_proactive(bridge)
    bridge._recent_messages_by_group.clear()
    bridge._context_summaries_by_group.clear()
    bridge.recent_messages_for_group(975805598).append({"user_id": 1, "name": "甲", "text": "今天群里全员低电量"})
    bridge.context_summaries_for_group(975805598).append("大家刚才在聊精神状态和吃什么。")
    event = make_event(text="有没有人救一下")

    prompt = bridge.build_proactive_prompt(event, ["topic:精神状态", "open_question"])

    assert "主动接一句话" in prompt
    assert "这不是被 @ 回复" in prompt
    assert prompt.index("群聊近况摘要") < prompt.index("群聊上下文") < prompt.index("基础人设与群聊提示词")
    assert "今天群里全员低电量" in prompt
    assert "如果不适合插话或实在没话接就保持沉默" in prompt
    assert "如果不发言，只输出 <SILENT>" in prompt


def test_proactive_prompt_logs_section_diagnostics(monkeypatch):
    bridge = load_bridge_module()
    configure_proactive(bridge)
    bridge._recent_messages_by_group.clear()
    bridge._context_summaries_by_group.clear()
    logs = []

    monkeypatch.setattr(bridge, "log", lambda obj: logs.append(obj))
    monkeypatch.setattr(bridge, "format_context_summaries", lambda group_id=None: "摘" * 1000)
    monkeypatch.setattr(bridge, "normal_chat_persona_bundle_for_prompt", lambda group_id: "人设")

    prompt = bridge.build_proactive_prompt(make_event(text="有没有人救一下"), ["burst"])

    record = next(item for item in logs if item["type"] == "prompt_rendered")
    assert record["kind"] == "proactive"
    assert record["group_id"] == 975805598
    assert record["char_count"] == len(prompt)
    assert record["truncated_sections"] == ["summary_context"]
    summary = next(section for section in record["sections"] if section["key"] == "summary_context")
    recent = next(section for section in record["sections"] if section["key"] == "recent_context")
    assert summary["budget_chars"] == 600
    assert summary["truncated"] is True
    assert recent["priority"] == "critical"
    assert recent["truncated"] is False
    assert "prompt" not in record


def test_proactive_context_decay_prioritizes_recent_human_messages():
    bridge = load_bridge_module()
    configure_proactive(bridge)
    bridge._recent_messages_by_group.clear()
    group_id = 975805598
    bridge.remember_message(make_event(group_id=group_id, user_id=1, nickname="甲", text="旧话题：精神状态不太行"))
    bridge.remember_bot_reply(group_id, "精神状态这个梗我刚才接过了", 3975680980)
    bridge.remember_message(make_event(group_id=group_id, user_id=2, nickname="乙", text="刚刚开始聊火锅了"))
    bridge.remember_message(make_event(group_id=group_id, user_id=3, nickname="丙", text="毛肚要七上八下"))
    bridge.remember_message(make_event(group_id=group_id, user_id=4, nickname="丁", text="鸳鸯锅还是辣锅"))

    context = bridge.format_proactive_recent_context(group_id)
    prompt = bridge.build_proactive_prompt(make_event(group_id=group_id, text="还有人来吗"), ["open_question"])

    assert "主动发言有上下文权重衰减" in context
    assert "低权重：较早上下文" in context
    assert "毛肚要七上八下" in context
    assert "鸳鸯锅还是辣锅" in context
    assert "精神状态这个梗我刚才接过了" not in context
    assert context.index("高权重：最近群友消息") < context.index("低权重：较早上下文")
    assert "高权重最近群友消息" in prompt
    assert "触发原因只是内部诊断" in prompt
    assert "主体不确定就用“当事人/楼上/这波”泛称" in prompt
    assert "低权重旧消息和近况摘要只作背景" in prompt
    assert "只能重复旧关键词、旧梗或 Esti 之前的说法" in prompt
    assert "<SILENT>" in prompt


def test_mark_proactive_replied_resets_score_and_counts_day():
    bridge = load_bridge_module()
    configure_proactive(bridge)
    state = bridge.proactive_state_for_group(975805598)
    state["score"] = 20.0

    bridge.mark_proactive_replied(975805598, now=1000.0)

    assert state["score"] == 0.0
    assert state["last_proactive_at"] == 1000.0
    assert state["daily_count"] == 1


def test_non_at_group_message_can_trigger_proactive_reply(monkeypatch):
    bridge = load_bridge_module()
    configure_proactive(bridge)
    bridge.PROACTIVE_TRIGGER_THRESHOLD = 1.0
    bridge.MIN_SECONDS_BETWEEN_REPLIES = 0.0
    bridge._recent_messages_by_group.clear()
    sent = []

    monkeypatch.setattr(bridge, "run_hermes_raw", lambda prompt, *args, **kwargs: "这群今天像集体低电量。")

    async def fake_send(group_id, message):
        sent.append((group_id, message))
        return {"ok": True, "status": "ok"}

    monkeypatch.setattr(bridge, "send_group_msg", fake_send)

    class FakeRequest:
        async def json(self):
            return make_event(text="精神状态不太行")

    result = asyncio.run(run_event_and_drain(bridge, FakeRequest()))

    assert result["queued"] is True
    assert sent == [(975805598, "这群今天像集体低电量")]
    context = bridge.format_recent_context(975805598)
    assert "发言人：Esti（QQ: 3975680980，机器人）" in context
    assert "内容：这群今天像集体低电量" in context


def test_duplicate_onebot_events_do_not_send_duplicate_proactive_replies(monkeypatch):
    bridge = load_bridge_module()
    configure_proactive(bridge)
    bridge.PROACTIVE_TRIGGER_THRESHOLD = 1.0
    bridge.MIN_SECONDS_BETWEEN_REPLIES = 0.0
    sent = []
    monkeypatch.setattr(bridge, "run_hermes_raw", lambda prompt, *args, **kwargs: "这群今天像集体低电量。")

    async def fake_send(group_id, message):
        sent.append((group_id, message))
        return {"ok": True}

    monkeypatch.setattr(bridge, "send_group_msg", fake_send)
    duplicate = make_event(text="精神状态不太行")
    duplicate["message_id"] = 424242

    class FakeRequest:
        async def json(self):
            return duplicate

    first = asyncio.run(run_event_and_drain(bridge, FakeRequest()))
    second = asyncio.run(bridge.onebot_event(FakeRequest()))

    assert first["queued"] is True
    assert second["ignored"] == "duplicate_event"
    assert sent == [(975805598, "这群今天像集体低电量")]


def test_parallel_proactive_triggers_are_queued_not_dropped(monkeypatch):
    bridge = load_bridge_module()
    configure_proactive(bridge)
    bridge.PROACTIVE_TRIGGER_THRESHOLD = 1.0
    bridge.PROACTIVE_GROUP_COOLDOWN_SECONDS = 0.0
    bridge.MIN_SECONDS_BETWEEN_REPLIES = 0.0
    sent = []

    def slow_reply(event, reasons):
        import time
        time.sleep(0.05)
        return f"这群今天像集体低电量 {event.get('user_id')}"

    monkeypatch.setattr(bridge, "run_proactive_reply", slow_reply)

    async def fake_send(group_id, message):
        sent.append((group_id, message))
        return {"ok": True}

    monkeypatch.setattr(bridge, "send_group_msg", fake_send)

    class FakeRequest:
        def __init__(self, event):
            self.event = event
        async def json(self):
            return self.event

    async def run_two():
        results = await asyncio.gather(
            bridge.onebot_event(FakeRequest(make_event(user_id=1, text="精神状态不太行"))),
            bridge.onebot_event(FakeRequest(make_event(user_id=2, text="有没有人救一下"))),
        )
        await bridge.wait_reply_worker(975805598)
        return results

    results = asyncio.run(run_two())

    assert all(r.get("queued") for r in results)
    assert len(sent) == 2


def test_parallel_identical_proactive_replies_suppress_duplicate_send(monkeypatch):
    bridge = load_bridge_module()
    configure_proactive(bridge)
    bridge.PROACTIVE_TRIGGER_THRESHOLD = 1.0
    bridge.PROACTIVE_GROUP_COOLDOWN_SECONDS = 0.0
    bridge.MIN_SECONDS_BETWEEN_REPLIES = 0.0
    sent = []

    monkeypatch.setattr(bridge, "run_proactive_reply", lambda event, reasons: "气溶质上听着像把姓氏学做成了化学题")

    async def fake_send(group_id, message):
        sent.append((group_id, message))
        return {"ok": True}

    monkeypatch.setattr(bridge, "send_group_msg", fake_send)

    class FakeRequest:
        def __init__(self, event):
            self.event = event
        async def json(self):
            return self.event

    async def run_two():
        results = await asyncio.gather(
            bridge.onebot_event(FakeRequest(make_event(user_id=1, text="气溶质上"))),
            bridge.onebot_event(FakeRequest(make_event(user_id=2, text="气溶质上"))),
        )
        await bridge.wait_reply_worker(975805598)
        return results

    results = asyncio.run(run_two())

    assert all(r.get("queued") for r in results)
    assert sent == [(975805598, "气溶质上听着像把姓氏学做成了化学题")]


def test_proactive_reply_does_not_trigger_web_search_or_notice(monkeypatch):
    bridge = load_bridge_module()
    configure_proactive(bridge)
    bridge.PROACTIVE_TRIGGER_THRESHOLD = 1.0
    bridge.PROACTIVE_GROUP_COOLDOWN_SECONDS = 0.0
    bridge.MIN_SECONDS_BETWEEN_REPLIES = 0.0
    bridge.WEB_SEARCH_ENABLED = True
    sent = []

    monkeypatch.setattr(bridge, "run_web_search", lambda query: (_ for _ in ()).throw(AssertionError("proactive replies must not search")))
    monkeypatch.setattr(bridge, "run_hermes_raw", lambda prompt, *args, **kwargs: "还没官宣 先别急")

    async def fake_send(group_id, message):
        sent.append((group_id, message))
        return {"ok": True}

    monkeypatch.setattr(bridge, "send_group_msg", fake_send)

    class FakeRequest:
        async def json(self):
            return make_event(text="这个最新转会瓜好像很真")

    result = asyncio.run(run_event_and_drain(bridge, FakeRequest()))

    assert result["queued"] is True
    assert result["worker"] in {"scheduled", "already_running"}
    assert sent == [(975805598, "还没官宣 先别急")]


def test_proactive_rate_limit_allows_at_most_six_replies_per_minute():
    bridge = load_bridge_module()
    configure_proactive(bridge)
    bridge.PROACTIVE_GROUP_COOLDOWN_SECONDS = 0.0
    state = bridge.proactive_state_for_group(975805598)
    for i in range(6):
        assert bridge.can_send_proactive_now(975805598, now=1000.0 + i * 5) == ""
        bridge.mark_proactive_replied(975805598, now=1000.0 + i * 5)
        state["score"] = 100.0

    result = bridge.update_proactive_score(make_event(text="精神状态"), now=1030.0)
    assert result["should_trigger"] is False
    assert result["blocked"] == "rate_limit"

    result = bridge.update_proactive_score(make_event(text="精神状态"), now=1061.0)
    assert result["blocked"] == ""
    assert result["should_trigger"] is True


def test_name_trigger_is_case_insensitive_but_does_not_bypass_heat_threshold():
    bridge = load_bridge_module()
    configure_proactive(bridge)
    bridge.PROACTIVE_TRIGGER_THRESHOLD = 999.0

    for text in ["esti 在吗", "Esti 怎么不说话", "estilord 出来一下", "ESTILORD 看看"]:
        result = bridge.update_proactive_score(make_event(text=text), now=1000.0)
        assert result["should_trigger"] is False, text
        assert result["direct_name_trigger"] is True, text
        assert any(r.startswith("name:") for r in result["reasons"]), text
        bridge._proactive_state_by_group.clear()
        bridge._recent_activity_by_group.clear()


def test_non_at_estilord_message_sends_direct_qq_reply(monkeypatch):
    bridge = load_bridge_module()
    configure_proactive(bridge)
    bridge.PROACTIVE_TRIGGER_THRESHOLD = 999.0
    bridge.PROACTIVE_GROUP_COOLDOWN_SECONDS = 0.0
    bridge.MIN_SECONDS_BETWEEN_REPLIES = 0.0
    sent = []
    monkeypatch.setattr(bridge, "run_hermes_raw", lambda *args, **kwargs: "我在，怎么了")
    monkeypatch.setattr(bridge, "run_proactive_reply", lambda event, reasons: (_ for _ in ()).throw(AssertionError("name mentions should route as direct replies")))

    async def fake_send(group_id, message):
        sent.append((group_id, message))
        return {"ok": True}

    monkeypatch.setattr(bridge, "send_group_msg", fake_send)

    class FakeRequest:
        async def json(self):
            event = make_event(text="estilord 在吗")
            event["message_id"] = 987654
            return event

    result = asyncio.run(run_event_and_drain(bridge, FakeRequest()))

    assert result["queued"] is True
    assert sent == [(975805598, "[CQ:reply,id=987654]我在 怎么了")]


def test_name_trigger_records_metadata_but_keeps_rate_limit():
    bridge = load_bridge_module()
    configure_proactive(bridge)
    bridge.PROACTIVE_TRIGGER_THRESHOLD = 999.0
    result = bridge.update_proactive_score(make_event(text="Esti 怎么不说话了"), now=1000.0)

    assert result["should_trigger"] is False
    assert result["direct_name_trigger"] is True
    assert any(r.startswith("name:") for r in result["reasons"])

    for i in range(bridge.PROACTIVE_RATE_LIMIT_MAX_REPLIES):
        bridge.mark_proactive_replied(975805598, now=1000.0 + i)
    result = bridge.update_proactive_score(make_event(text="bot 出来一下"), now=1030.0)
    assert result["should_trigger"] is False
    assert result["blocked"] == "rate_limit"


def test_proactive_daily_limit_blocks_even_after_high_score_or_name_trigger():
    bridge = load_bridge_module()
    configure_proactive(bridge)
    bridge.PROACTIVE_TRIGGER_THRESHOLD = 1.0
    bridge.PROACTIVE_DAILY_LIMIT_PER_GROUP = 1
    state = bridge.proactive_state_for_group(975805598)
    state["daily_count"] = 1
    state["score"] = 100.0

    result = bridge.update_proactive_score(make_event(text="Esti 精神状态"), now=1000.0)

    assert result["blocked"] == "daily_limit"
    assert result["should_trigger"] is False
    assert result["direct_name_trigger"] is True


def test_proactive_daily_limit_zero_disables_cap():
    bridge = load_bridge_module()
    configure_proactive(bridge)
    bridge.PROACTIVE_TRIGGER_THRESHOLD = 1.0
    bridge.PROACTIVE_DAILY_LIMIT_PER_GROUP = 0
    state = bridge.proactive_state_for_group(975805598)
    state["daily_count"] = 999
    state["score"] = 100.0

    result = bridge.update_proactive_score(make_event(text="精神状态"), now=1000.0)

    assert result["blocked"] == ""
    assert result["should_trigger"] is True


def test_proactive_reply_treats_silent_marker_as_silent_and_uses_no_session(monkeypatch):
    bridge = load_bridge_module()
    configure_proactive(bridge)
    calls = []

    def fake_run(prompt, group_id=None, use_group_session=True, purpose="unknown"):
        calls.append({"prompt": prompt, "group_id": group_id, "use_group_session": use_group_session, "purpose": purpose})
        return "<SILENT>"

    monkeypatch.setattr(bridge, "run_hermes_raw", fake_run)

    reply = bridge.run_proactive_reply(make_event(text="普通热闹消息"), ["burst"])

    assert reply == ""
    assert calls[0]["group_id"] == 975805598
    assert calls[0]["use_group_session"] is False
    assert calls[0]["purpose"] == "proactive_reply"


def test_proactive_reply_treats_output_silent_instruction_as_silent(monkeypatch):
    bridge = load_bridge_module()
    configure_proactive(bridge)
    monkeypatch.setattr(bridge, "run_hermes_raw", lambda *args, **kwargs: "输出 <SILENT>")

    reply = bridge.run_proactive_reply(make_event(text="普通热闹消息"), ["burst"])

    assert reply == ""


def test_proactive_reply_treats_fallback_templates_as_silent(monkeypatch):
    bridge = load_bridge_module()
    configure_proactive(bridge)
    monkeypatch.setattr(bridge, "run_hermes_raw", lambda *args, **kwargs: "我有点卡住了 等会再说")

    reply = bridge.run_proactive_reply(make_event(text="普通热闹消息"), ["burst"])

    assert reply == ""


def test_proactive_reply_treats_silence_rationale_as_silent(monkeypatch):
    bridge = load_bridge_module()
    configure_proactive(bridge)
    leaked = "空的输出是正确的——这个主动发言判断的结果就是当前话题已经是持续讨论 群友之间在不断回应，所以没有新的接话点不需要再输出什么了"
    monkeypatch.setattr(bridge, "run_hermes_raw", lambda *args, **kwargs: leaked)

    reply = bridge.run_proactive_reply(make_event(text="普通热闹消息"), ["burst"])

    assert reply == ""


def test_proactive_reply_repeated_recent_bot_wording_is_silent(monkeypatch):
    bridge = load_bridge_module()
    configure_proactive(bridge)
    bridge._recent_messages_by_group.clear()
    bridge.remember_bot_reply(975805598, "这群今天像集体低电量", 3975680980)
    monkeypatch.setattr(bridge, "run_hermes_raw", lambda *args, **kwargs: "这群今天像集体低电量。")

    reply = bridge.run_proactive_reply(make_event(text="又开始热闹了"), ["burst"])

    assert reply == ""


def test_proactive_trigger_with_repeated_bot_wording_does_not_send(monkeypatch):
    bridge = load_bridge_module()
    configure_proactive(bridge)
    bridge.PROACTIVE_TRIGGER_THRESHOLD = 1.0
    bridge.PROACTIVE_GROUP_COOLDOWN_SECONDS = 0.0
    bridge.MIN_SECONDS_BETWEEN_REPLIES = 0.0
    bridge._recent_messages_by_group.clear()
    bridge.remember_bot_reply(975805598, "这群今天像集体低电量", 3975680980)
    sent = []
    monkeypatch.setattr(bridge, "run_hermes_raw", lambda *args, **kwargs: "这群今天像集体低电量。")

    async def fake_send(group_id, message):
        sent.append((group_id, message))
        return {"ok": True, "status": "ok"}

    monkeypatch.setattr(bridge, "send_group_msg", fake_send)

    class FakeRequest:
        async def json(self):
            event = make_event(text="精神状态不太行")
            event["message_id"] = 22334455
            return event

    result = asyncio.run(run_event_and_drain(bridge, FakeRequest()))

    assert result["queued"] is True
    assert sent == []


def test_distinct_proactive_reply_after_bot_history_still_sends(monkeypatch):
    bridge = load_bridge_module()
    configure_proactive(bridge)
    bridge.PROACTIVE_TRIGGER_THRESHOLD = 1.0
    bridge.PROACTIVE_GROUP_COOLDOWN_SECONDS = 0.0
    bridge.MIN_SECONDS_BETWEEN_REPLIES = 0.0
    bridge._recent_messages_by_group.clear()
    bridge.remember_bot_reply(975805598, "这群今天像集体低电量", 3975680980)
    sent = []
    monkeypatch.setattr(bridge, "run_hermes_raw", lambda *args, **kwargs: "那还是先看晚上吃什么")

    async def fake_send(group_id, message):
        sent.append((group_id, message))
        return {"ok": True, "status": "ok"}

    monkeypatch.setattr(bridge, "send_group_msg", fake_send)

    class FakeRequest:
        async def json(self):
            event = make_event(text="晚上吃啥")
            event["message_id"] = 22334456
            return event

    result = asyncio.run(run_event_and_drain(bridge, FakeRequest()))

    assert result["queued"] is True
    assert sent == [(975805598, "那还是先看晚上吃什么")]


def test_queued_proactive_revalidates_cooldown_before_generation(monkeypatch):
    bridge = load_bridge_module()
    configure_proactive(bridge)
    bridge.PROACTIVE_GROUP_COOLDOWN_SECONDS = 20.0
    bridge.MIN_SECONDS_BETWEEN_REPLIES = 0.0
    bridge.proactive_state_for_group(975805598)["last_proactive_at"] = 1000.0
    monkeypatch.setattr(bridge.time, "time", lambda: 1005.0)
    monkeypatch.setattr(bridge, "run_proactive_reply", lambda event, reasons: (_ for _ in ()).throw(AssertionError("blocked proactive intent must not generate")))

    result = asyncio.run(bridge.process_proactive_reply_intent(
        975805598,
        {"kind": "proactive", "event": make_event(text="普通热闹消息"), "proactive": {"score": 20.0, "reasons": ["burst"]}},
    ))

    assert result["ignored"] == "proactive_revalidated_blocked"
    assert result["blocked"] == "group_cooldown"


def test_proactive_trigger_with_fallback_output_does_not_send(monkeypatch):
    bridge = load_bridge_module()
    configure_proactive(bridge)
    bridge.PROACTIVE_TRIGGER_THRESHOLD = 1.0
    bridge.PROACTIVE_GROUP_COOLDOWN_SECONDS = 0.0
    bridge.MIN_SECONDS_BETWEEN_REPLIES = 0.0
    sent = []
    monkeypatch.setattr(bridge, "run_hermes_raw", lambda *args, **kwargs: "我还没组织好")

    async def fake_send(group_id, message):
        sent.append((group_id, message))
        return {"ok": True, "status": "ok"}

    monkeypatch.setattr(bridge, "send_group_msg", fake_send)

    class FakeRequest:
        async def json(self):
            event = make_event(text="精神状态不太行")
            event["message_id"] = 123456789
            return event

    result = asyncio.run(run_event_and_drain(bridge, FakeRequest()))

    assert result["queued"] is True
    assert sent == []


def test_proactive_prompt_allows_silence_or_natural_new_topic_not_fallback():
    bridge = load_bridge_module()
    configure_proactive(bridge)

    prompt = bridge.build_proactive_prompt(make_event(text="无敌了icbm"), ["burst"])

    assert "<SILENT>" in prompt
    assert prompt.count("<SILENT>") == 1
    assert "空输出是正确的" not in prompt
    assert "不要解释沉默原因或输出规则" in prompt
    assert "可以自然开一个很轻的小话题" in prompt

def test_group_specific_proactive_threshold_overrides_global_threshold():
    bridge = load_bridge_module()
    configure_proactive(bridge)
    bridge.PROACTIVE_TRIGGER_THRESHOLD = 16.0
    bridge.PROACTIVE_TRIGGER_THRESHOLDS_BY_GROUP = {781423661: 999.0, 975805598: 16.0}
    bridge.PROACTIVE_GROUP_COOLDOWN_SECONDS = 0.0

    low_score = 20.0
    bridge.proactive_state_for_group(781423661)["score"] = low_score
    hang = bridge.update_proactive_score(make_event(group_id=781423661, text="普通消息"), now=1000.0)
    assert hang["score"] < 999.0
    assert hang["should_trigger"] is False

    bridge.proactive_state_for_group(975805598)["score"] = low_score
    ning = bridge.update_proactive_score(make_event(group_id=975805598, text="普通消息"), now=1000.0)
    assert ning["score"] >= 16.0
    assert ning["should_trigger"] is True


def test_parse_group_thresholds_env_format():
    bridge = load_bridge_module()

    parsed = bridge.parse_group_float_map("781423661=999,975805598:16, bad, 123=oops")

    assert parsed == {781423661: 999.0, 975805598: 16.0}

