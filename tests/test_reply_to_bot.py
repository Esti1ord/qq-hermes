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


def make_reply_event(reply_data, text="确实，那怎么办", user_id=111, group_id=975805598, self_id=3975680980):
    return {
        "post_type": "message",
        "message_type": "group",
        "group_id": group_id,
        "user_id": user_id,
        "self_id": self_id,
        "sender": {"nickname": "群友"},
        "message": [
            {"type": "reply", "data": reply_data},
            {"type": "text", "data": {"text": text}},
        ],
    }


def test_reply_to_bot_message_counts_as_trigger():
    bridge = load_bridge_module()
    bridge.BOT_QQ = "3975680980"
    event = make_reply_event({"qq": "3975680980", "text": "这群今天像集体低电量。"})

    assert bridge.is_reply_to_me(event) is True
    assert bridge.should_trigger_direct_reply(event) is True


def test_reply_to_other_user_does_not_count_as_trigger():
    bridge = load_bridge_module()
    bridge.BOT_QQ = "3975680980"
    event = make_reply_event({"qq": "123456", "text": "别人的话"})

    assert bridge.is_reply_to_me(event) is False
    assert bridge.should_trigger_direct_reply(event) is False


def test_reply_context_marks_reply_to_bot_as_high_priority():
    bridge = load_bridge_module()
    bridge.BOT_QQ = "3975680980"
    event = make_reply_event({"qq": "3975680980", "text": "这群今天像集体低电量。"}, text="哈哈那我充不动了")

    context = bridge.reply_context_from_event(event)

    assert "正在回复机器人上一条发言" in context
    assert "这群今天像集体低电量。" in context
    assert "用户这条消息是在接机器人上一条回答" in context


def test_prompt_prioritizes_user_reply_to_bot_answer():
    bridge = load_bridge_module()
    bridge.BOT_QQ = "3975680980"
    event = make_reply_event({"qq": "3975680980", "text": "这群今天像集体低电量。"}, text="哈哈那我充不动了")

    prompt = bridge.build_prompt(event, "哈哈那我充不动了")

    assert "用户正在回复机器人上一条发言" in prompt
    assert "把它视作连续对话" in prompt
    assert prompt.index("被回复/引用的消息") < prompt.index("当前被 @ 的消息")


def test_onebot_replies_when_user_replies_to_bot_without_at(monkeypatch):
    bridge = load_bridge_module()
    bridge.BOT_QQ = "3975680980"
    bridge.MIN_SECONDS_BETWEEN_REPLIES = 0.0
    bridge.PROACTIVE_ENABLED = False
    sent = []

    monkeypatch.setattr(bridge, "run_hermes_raw", lambda prompt, *args, **kwargs: "还能抢救一下")

    async def fake_send(group_id, message):
        sent.append((group_id, message))
        return {"ok": True}

    monkeypatch.setattr(bridge, "send_group_msg", fake_send)

    class FakeRequest:
        async def json(self):
            event = make_reply_event({"qq": "3975680980", "text": "这群今天像集体低电量。"}, text="哈哈那我充不动了")
            event["message_id"] = 606
            return event

    async def run_event():
        result = await bridge.onebot_event(FakeRequest())
        await bridge.wait_reply_worker(975805598)
        return result

    result = asyncio.run(run_event())

    assert result["queued"] is True
    assert sent == [(975805598, "[CQ:reply,id=606]还能抢救一下")]

def test_reply_context_falls_back_to_recent_message_id_when_reply_segment_has_no_text():
    bridge = load_bridge_module()
    bridge.BOT_QQ = "3975680980"
    bridge._recent_messages_by_group.clear()
    bridge.remember_message_item(975805598, {
        "user_id": 2563576347,
        "name": "狂扁小日本",
        "text": "我们都轮流坐的，刁哥不想下来了咋办",
        "message_id": "abc123",
    })
    event = make_reply_event({"qq": "2563576347", "message_id": "abc123"}, text="@Esti1ord")

    context = bridge.reply_context_from_event(event)

    assert "引用消息：狂扁小日本：我们都轮流坐的" in context
    assert "未取到原文" not in context


def test_reply_to_missing_text_does_not_ask_user_to_resend(monkeypatch):
    bridge = load_bridge_module()
    bridge.BOT_QQ = "3975680980"
    event = make_reply_event({"qq": "2563576347", "message_id": "missing"}, text="@Esti1ord 怎么办")
    monkeypatch.setattr(bridge, "run_hermes", lambda prompt, *args, **kwargs: prompt)

    prompt = bridge.build_prompt(event, "怎么办")

    assert "未取到原文" not in prompt
    assert "再发一遍" not in prompt
    assert "引用消息ID: missing" in prompt

