import asyncio
import importlib.util
import os
from pathlib import Path

BRIDGE_PATH = Path(__file__).resolve().parents[1] / "bridge.py"


def load_bridge_module():
    spec = importlib.util.spec_from_file_location("bridge_under_test", BRIDGE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def make_event(group_id=975805598, user_id=111, nickname="甲", text="你好", self_id=3975680980):
    return {
        "post_type": "message",
        "message_type": "group",
        "group_id": group_id,
        "user_id": user_id,
        "self_id": self_id,
        "sender": {"nickname": nickname},
        "message": [{"type": "text", "data": {"text": text}}],
    }


def test_recent_context_keeps_latest_group_messages_only():
    bridge = load_bridge_module()
    bridge.CONTEXT_MAX_MESSAGES = 3
    bridge._recent_messages.clear()

    bridge.remember_message(make_event(group_id=975805598, user_id=1, nickname="甲", text="第一条"))
    bridge.remember_message(make_event(group_id=425744312, user_id=2, nickname="乙", text="其他群"))
    bridge.remember_message(make_event(group_id=975805598, user_id=3, nickname="丙", text="第二条"))
    bridge.remember_message(make_event(group_id=975805598, user_id=4, nickname="丁", text="第三条"))
    bridge.remember_message(make_event(group_id=975805598, user_id=5, nickname="戊", text="第四条"))

    context = bridge.format_recent_context()

    assert "其他群" not in context
    assert "第一条" not in context
    assert "第二条" in context
    assert "第三条" in context
    assert "第四条" in context


def test_prompt_includes_recent_context_before_current_message():
    bridge = load_bridge_module()
    bridge.CONTEXT_MAX_MESSAGES = 20
    bridge._recent_messages.clear()

    bridge.remember_message(make_event(user_id=1, nickname="甲", text="前文A"))
    bridge.remember_message(make_event(user_id=2, nickname="乙", text="前文B"))
    event = make_event(user_id=3, nickname="丙", text="当前问题")

    prompt = bridge.build_prompt(event, "当前问题")

    assert "群聊近二十条上下文" in prompt
    assert "甲" in prompt and "前文A" in prompt
    assert "乙" in prompt and "前文B" in prompt
    assert "当前被 @ 的消息" in prompt
    assert prompt.index("前文A") < prompt.index("当前问题")


def test_recent_context_labels_each_message_with_sequence_and_speaker_identity():
    bridge = load_bridge_module()
    bridge.CONTEXT_MAX_MESSAGES = 20
    bridge._recent_messages.clear()
    bridge._recent_messages_by_group.clear()

    bridge.remember_message(make_event(user_id=1001, nickname="A", text="我刚跑完步"))
    bridge.remember_message(make_event(user_id=2002, nickname="B", text="笑死我了"))

    context = bridge.format_recent_context()

    assert "[1] 发言人：A（QQ: 1001）" in context
    assert "[1] 内容：我刚跑完步" in context
    assert "[2] 发言人：B（QQ: 2002）" in context
    assert "[2] 内容：笑死我了" in context
    assert "注意：以上每一个编号都是一条独立群消息" in context


def test_recent_context_groups_older_messages_as_low_weight_and_latest_as_high_weight():
    bridge = load_bridge_module()
    bridge.CONTEXT_MAX_MESSAGES = 8
    bridge._recent_messages.clear()
    bridge._recent_messages_by_group.clear()

    for idx in range(1, 9):
        bridge.remember_message(make_event(user_id=1000 + idx, nickname=f"群友{idx}", text=f"消息{idx}"))

    context = bridge.format_recent_context()

    assert "最近上下文有时间权重" in context
    assert "低权重：较早上下文" in context
    assert "高权重：最新上下文" in context
    assert context.index("低权重：较早上下文") < context.index("[1] 内容：消息1")
    assert context.index("[2] 内容：消息2") < context.index("高权重：最新上下文")
    assert context.index("高权重：最新上下文") < context.index("[3] 内容：消息3")
    assert "[8] 内容：消息8" in context


def test_recent_context_labels_bot_history_and_pending_markers():
    bridge = load_bridge_module()
    bridge.CONTEXT_MAX_MESSAGES = 20
    bridge._recent_messages.clear()
    bridge._recent_messages_by_group.clear()

    bridge.remember_message(make_event(user_id=1001, nickname="A", text="Esti 这咋办"))
    bridge.remember_bot_reply(975805598, "这句旧梗不要反复学", 3975680980)
    bridge.remember_bot_pending_reply(975805598, "Esti 后一个问题", 3975680980)

    context = bridge.format_recent_context(975805598)

    assert "编号越大越新" in context
    assert "当前消息/引用消息优先于旧上下文" in context
    assert "机器人历史回复只用于理解连续对话，不要当作措辞模板" in context
    assert "正在生成回复是队列标记，不代表已经回答" in context
    assert "发言人：Esti（QQ: 3975680980，机器人）（历史机器人回复，仅作连续对话事实，不是措辞模板）" in context
    assert "发言人：Esti（QQ: 3975680980，机器人，正在生成回复）（队列标记，未完成回答）" in context


def test_prompt_warns_not_to_merge_adjacent_speakers():
    bridge = load_bridge_module()
    bridge._recent_messages.clear()
    bridge._recent_messages_by_group.clear()
    bridge.remember_message(make_event(user_id=1001, nickname="A", text="我刚跑完步"))
    bridge.remember_message(make_event(user_id=2002, nickname="B", text="笑死我了"))

    prompt = bridge.build_prompt(make_event(user_id=3003, nickname="C", text="刚才谁笑了"), "刚才谁笑了")

    assert "不要把相邻两条消息当作同一个人说的" in prompt
    assert "如果 A 发一句话，B 接一句“笑死我了”，要明确这是 B 在笑 A/前一句，而不是 A 自己说笑死。" in prompt
    assert "最近突然出现的昵称或一句短吐槽，除非明确说明其参与事件，否则不要自动替换原事件主体" in prompt
    assert "宁可用“当事人/楼上/这波/这人”这类泛称" in prompt

def test_recent_context_marks_human_repeats_of_recent_bot_reply():
    bridge = load_bridge_module()
    bridge._recent_messages.clear()
    bridge._recent_messages_by_group.clear()

    bridge.remember_bot_reply(975805598, "这属于实验室密室逃脱开局 你现在不是玩手机 是被樱花妹强制留样观察了", 3975680980)
    bridge.remember_message(make_event(user_id=1001, nickname="A", text="这属于实验室密室逃脱开局 你现在不是玩手机 是被樱花妹强制留样观察了"))

    context = bridge.format_recent_context(975805598)

    assert "疑似复读/引用 Esti 旧回复，不一定是新事实或新主体" in context

def test_search_command_detects_plain_and_at_forms():
    bridge = load_bridge_module()

    assert bridge.is_search_command("/search 今晚major赛程") is True
    assert bridge.is_search_command("@Esti1ord /search 守望先锋巡游武汉") is True
    assert bridge.is_search_command("/searching") is False


def test_extract_search_command_query_strips_command_and_at_prefix():
    bridge = load_bridge_module()

    assert bridge.search_command_query("/search 今晚major赛程") == "今晚major赛程"
    assert bridge.search_command_query("@Esti1ord /search 守望先锋巡游武汉") == "守望先锋巡游武汉"
    assert bridge.search_command_query("请 /search 今晚major赛程") == "今晚major赛程"


def test_onebot_search_command_without_at_replies_directly_and_uses_no_group_session(monkeypatch):
    bridge = load_bridge_module()
    bridge.BOT_QQ = "3975680980"
    bridge.MIN_SECONDS_BETWEEN_REPLIES = 0.0
    bridge.PROACTIVE_ENABLED = False
    sent = []
    searched = []

    async def fake_send(group_id, message):
        sent.append((group_id, message))
        return {"ok": True}

    monkeypatch.setattr(bridge, "send_group_msg", fake_send)
    monkeypatch.setattr(bridge, "run_web_search", lambda query: searched.append(query) or "今晚赛程：A vs B")
    monkeypatch.setattr(bridge, "run_hermes", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("/search must not call normal group-session reply LLM")))
    monkeypatch.setattr(bridge, "enqueue_reply_intent", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("/search must not enter reply queue")))

    class FakeRequest:
        async def json(self):
            return make_event(group_id=781423661, user_id=222, nickname="乙", text="/search 今晚major赛程")

    result = asyncio.run(bridge.onebot_event(FakeRequest()))

    assert result["replied"] is True
    assert result["trigger"] == "search_command"
    assert len(searched) == 1
    assert "今晚major赛程" in searched[0]
    assert "本群知识库" not in searched[0]
    assert sent == [(781423661, "今晚赛程：A vs B")]


def test_deepseek_command_detects_plain_and_at_forms():
    bridge = load_bridge_module()

    assert bridge.is_deepseek_command("/deepseek") is True
    assert bridge.is_deepseek_command("/deepseek 帮我分析") is True
    assert bridge.is_deepseek_command("@Esti1ord /deepseek 帮我分析") is True
    assert bridge.deepseek_command_query("请 /deepseek 帮我分析") == "帮我分析"
    assert bridge.is_deepseek_command("/deepseeking") is False
    assert bridge.deepseek_command_query("@Esti1ord /deepseek 帮我分析") == "帮我分析"


def test_build_deepseek_command_reply_uses_fresh_gpt55_no_group_session_and_search(monkeypatch):
    bridge = load_bridge_module()
    bridge.HERMES_MODEL = "normal-chat-model"
    bridge.HERMES_PROVIDER = "normal-provider"
    bridge.DEEPSEEK_COMMAND_MODEL = "gpt-5.5"
    bridge.DEEPSEEK_COMMAND_PROVIDER = "openai-gpt"
    bridge.MAX_REPLY_CHARS = 80
    calls = []
    monkeypatch.setattr(bridge, "run_web_search", lambda query: calls.append(("search", query)) or "搜索证据：A 和 B")

    class FakeRun:
        returncode = 0
        stdout = "结论：A 更稳。理由：有搜索证据支撑。\n\nsession_id: fresh"
        stderr = ""

    def fake_run(cmd, **kwargs):
        calls.append(("hermes", cmd))
        return FakeRun()

    monkeypatch.setattr(bridge.subprocess, "run", fake_run)

    reply = bridge.build_deepseek_command_reply("A 和 B 怎么选", group_id=975805598)

    assert reply.startswith("结论：A 更稳")
    assert len(reply) <= bridge.MAX_REPLY_CHARS
    assert calls[0] == ("search", "A 和 B 怎么选")
    cmd = calls[1][1]
    assert "--continue" not in cmd
    assert cmd[cmd.index("--model") + 1] == "gpt-5.5"
    assert cmd[cmd.index("--provider") + 1] == "openai-gpt"
    prompt = cmd[3]
    assert "全新的独立对话" in prompt
    assert "不继承任何群聊上下文" in prompt
    assert "搜索证据：A 和 B" in prompt


def test_deepseek_long_reply_is_rewritten_not_hard_truncated(monkeypatch):
    bridge = load_bridge_module()
    bridge.MAX_REPLY_CHARS = 80
    calls = []
    long_answer = "结论：从零成为 agent 算法工程师要按项目倒推能力。" + "先学 Python 和后端，再学 RAG、工具调用、评测优化。" * 8
    compressed = "结论：按项目倒推，先补 Python/后端，再做 RAG、工具调用和评测优化，别只刷框架教程。"
    monkeypatch.setattr(bridge, "run_web_search", lambda query: "搜索证据：岗位需要工程化、RAG、评测")

    class FakeRun:
        def __init__(self, stdout):
            self.returncode = 0
            self.stdout = stdout
            self.stderr = ""

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        prompt = cmd[3]
        if "把下面 /deepseek 深度回答重写" in prompt:
            return FakeRun(compressed + "\n\nsession_id: compressed")
        return FakeRun(long_answer + "\n\nsession_id: draft")

    monkeypatch.setattr(bridge.subprocess, "run", fake_run)

    reply = bridge.build_deepseek_command_reply("如何从零成为agent算法工程师", group_id=975805598)

    assert reply == bridge.prepare_reply_text(compressed)
    assert len(reply) <= bridge.MAX_REPLY_CHARS
    assert len(calls) == 2
    assert "把下面 /deepseek 深度回答重写" in calls[1][3]


def test_deepseek_compression_fallback_keeps_complete_clause(monkeypatch):
    bridge = load_bridge_module()
    bridge.MAX_REPLY_CHARS = 20
    monkeypatch.setattr(bridge, "compress_deepseek_reply", lambda *args, **kwargs: "")

    reply = bridge.finalize_deepseek_command_reply("第一句完整。第二句会很长很长很长很长很长很长很长很长。第三句也很长很长很长。", "问题", "搜索", 975805598)

    assert reply == "第一句完整。"
    assert len(reply) <= bridge.MAX_REPLY_CHARS
    assert not reply.endswith("很")


def test_prepare_reply_text_does_not_truncate_but_finalize_still_does():
    bridge = load_bridge_module()
    bridge.MAX_REPLY_CHARS = 10
    text = "这是一段明显超过十个字的回复"

    assert len(bridge.prepare_reply_text(text)) > bridge.MAX_REPLY_CHARS
    assert len(bridge.finalize_reply(text)) == bridge.MAX_REPLY_CHARS


def test_onebot_deepseek_command_without_at_replies_directly_and_bypasses_queue(monkeypatch):
    bridge = load_bridge_module()
    bridge.BOT_QQ = "3975680980"
    bridge.MIN_SECONDS_BETWEEN_REPLIES = 0.0
    bridge.PROACTIVE_ENABLED = False
    sent = []

    async def fake_send(group_id, message):
        sent.append((group_id, message))
        return {"ok": True}

    monkeypatch.setattr(bridge, "send_group_msg", fake_send)
    monkeypatch.setattr(bridge, "build_deepseek_command_reply", lambda query, group_id=None: f"深度回答：{query}")
    monkeypatch.setattr(bridge, "run_hermes", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("/deepseek must not call normal group-session reply LLM")))
    monkeypatch.setattr(bridge, "enqueue_reply_intent", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("/deepseek must not enter reply queue")))

    class FakeRequest:
        async def json(self):
            return make_event(group_id=781423661, user_id=222, nickname="乙", text="/deepseek 分析一下AI新闻")

    result = asyncio.run(bridge.onebot_event(FakeRequest()))

    assert result["replied"] is True
    assert result["trigger"] == "deepseek_command"
    assert sent == [(781423661, "深度回答：分析一下AI新闻")]



def test_context_command_detects_plain_and_at_forms():
    bridge = load_bridge_module()

    assert bridge.is_context_command("/context") is True
    assert bridge.is_context_command("/context 看我现在记住了哪些前情") is True
    assert bridge.is_context_command("@Esti1ord /context 看我现在记住了哪些前情") is True
    assert bridge.is_context_command("/contextual") is False


def test_build_context_command_reply_includes_group_summaries_and_recent_messages():
    bridge = load_bridge_module()
    bridge.CONTEXT_MAX_MESSAGES = 20
    bridge._recent_messages.clear()
    bridge._recent_messages_by_group.clear()
    bridge._context_summaries_by_group.clear()
    bridge.context_summaries_for_group(975805598).append("群友刚才在讨论轮流坐和刁哥不想下来")
    bridge.remember_message(make_event(group_id=975805598, user_id=2563576347, nickname="狂扁小日本", text="我们都轮流坐的，刁哥不想下来了咋办"))
    bridge.remember_message(make_event(group_id=975805598, user_id=2544866989, nickname="曲", text="@Esti1ord 怎么办"))

    reply = bridge.build_context_command_reply(975805598)

    assert "我现在记住的前情" in reply
    assert "群友刚才在讨论轮流坐" in reply
    assert "狂扁小日本：我们都轮流坐的" in reply
    assert "曲：@Esti1ord 怎么办" in reply
    assert "975805598" not in reply


def test_context_command_reply_is_group_scoped():
    bridge = load_bridge_module()
    bridge._recent_messages.clear()
    bridge._recent_messages_by_group.clear()
    bridge._context_summaries_by_group.clear()
    bridge.context_summaries_for_group(975805598).append("本群摘要")
    bridge.context_summaries_for_group(781423661).append("别群摘要")
    bridge.remember_message(make_event(group_id=975805598, nickname="本群", text="本群消息"))
    bridge.remember_message(make_event(group_id=781423661, nickname="别群", text="别群消息"))

    reply = bridge.build_context_command_reply(975805598)

    assert "本群摘要" in reply
    assert "本群：本群消息" in reply
    assert "别群摘要" not in reply
    assert "别群消息" not in reply

def test_onebot_context_command_without_at_replies_directly(monkeypatch):
    bridge = load_bridge_module()
    bridge.BOT_QQ = "3975680980"
    bridge.MIN_SECONDS_BETWEEN_REPLIES = 0.0
    bridge.PROACTIVE_ENABLED = False
    bridge._recent_messages_by_group.clear()
    bridge._context_summaries_by_group.clear()
    bridge.context_summaries_for_group(975805598).append("测试摘要")
    bridge.remember_message(make_event(group_id=975805598, nickname="甲", text="前情消息"))
    sent = []

    async def fake_send(group_id, message):
        sent.append((group_id, message))
        return {"ok": True}

    monkeypatch.setattr(bridge, "send_group_msg", fake_send)
    monkeypatch.setattr(bridge, "run_hermes", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("/context must not call LLM")))

    class FakeRequest:
        async def json(self):
            return make_event(group_id=975805598, user_id=222, nickname="乙", text="/context 看我现在记住了哪些前情")

    result = asyncio.run(bridge.onebot_event(FakeRequest()))

    assert result["replied"] is True
    assert result["trigger"] == "context_command"
    assert sent
    assert sent[0][0] == 975805598
    assert "我现在记住的前情" in sent[0][1]
    assert "测试摘要" in sent[0][1]
    assert "前情消息" in sent[0][1]

def test_context_command_reply_dedupes_and_filters_low_value_summaries():
    bridge = load_bridge_module()
    bridge.MAX_REPLY_CHARS = 2000
    bridge._recent_messages_by_group.clear()
    bridge._context_summaries_by_group.clear()
    summaries = bridge.context_summaries_for_group(975805598)
    summaries.append("多名群友反复说精神状态不太行 Esti三次回复说今天集体低电量 随后群友问Esti在吗Esti回应 群友回哈哈那充不动了")
    summaries.append("多名群友反复说精神状态不太行 Esti三次说集体低电量 群友问Esti在吗Esti回应 对方回哈哈那充不动了")
    summaries.append("摘要模型跑偏产生的元评论，并不是群聊中真实出现过的聊天语句")
    summaries.append("我这边暂时处理失败了，稍后再试一下。")
    summaries.append("群友讨论某人一直毕设答辩，天生自豪东问毕设答辩能否挂人")

    reply = bridge.build_context_command_reply(975805598)

    assert reply.count("精神状态") <= 1
    assert "处理失败" not in reply
    assert "并不是我们聊天的内容" not in reply
    assert "毕设答辩" in reply


def test_finalize_summary_rejects_error_and_meta_summaries():
    bridge = load_bridge_module()

    assert bridge.finalize_summary("我这边暂时处理失败了，稍后再试一下。") == ""
    assert bridge.finalize_summary("摘要模型跑偏产生的元评论，并不是群聊中真实出现过的聊天语句") == ""
    assert bridge.finalize_summary("摘要：群友讨论毕设答辩是否会挂人") == "群友讨论毕设答辩是否会挂人"

def test_context_command_reply_excludes_previous_context_command_bot_output():
    bridge = load_bridge_module()
    bridge.MAX_REPLY_CHARS = 2000
    bridge.REPLY_PREFIX = "[bot] "
    bridge._recent_messages_by_group.clear()
    bridge._context_summaries_by_group.clear()
    bridge.remember_message(make_event(group_id=975805598, nickname="甲", text="真实前情"))
    bridge.remember_bot_reply(975805598, "[bot] 我现在记住的前情：\n近况摘要：\n- 旧输出", 3975680980)

    reply = bridge.build_context_command_reply(975805598)

    assert "真实前情" in reply
    assert "旧输出" not in reply
    assert reply.count("我现在记住的前情") == 1

def test_context_command_reply_is_short_and_not_cut_mid_section():
    bridge = load_bridge_module()
    bridge.MAX_REPLY_CHARS = 450
    bridge._recent_messages_by_group.clear()
    bridge._context_summaries_by_group.clear()
    summaries = bridge.context_summaries_for_group(975805598)
    for idx in range(8):
        summaries.append(f"第{idx}条很长的上下文摘要，群友围绕一个话题连续讨论了很多细节，机器人也做了很多回应，这里模拟超长摘要内容")
    for idx in range(8):
        bridge.remember_message(make_event(group_id=975805598, nickname=f"群友{idx}", text=f"第{idx}条最近消息，也是一段很长很长的内容，用来模拟输出超限后被硬截断的情况"))

    reply = bridge.build_context_command_reply(975805598)

    assert len(reply) <= 450
    assert reply.count("- ") <= 5
    assert "最近消息：" in reply
    assert not reply.endswith("最近")
    assert not reply.endswith("||")
    assert not reply.endswith("：")

def test_default_real_context_cache_is_not_overwritten_during_pytest(monkeypatch):
    bridge = load_bridge_module()
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "dummy")
    bridge.CONTEXT_CACHE_FILE = bridge.BASE_DIR / "logs" / "recent_context.jsonl"
    bridge.CONTEXT_PERSIST_ENABLED = True
    bridge._recent_messages_by_group.clear()
    bridge._context_summaries_by_group.clear()
    bridge.context_summaries_for_group(975805598).append("测试摘要不应落盘")

    before = bridge.CONTEXT_CACHE_FILE.read_text(encoding="utf-8") if bridge.CONTEXT_CACHE_FILE.exists() else ""
    bridge.save_context_cache()
    after = bridge.CONTEXT_CACHE_FILE.read_text(encoding="utf-8") if bridge.CONTEXT_CACHE_FILE.exists() else ""

    assert after == before
    assert "测试摘要不应落盘" not in after


def test_send_group_msg_reports_failed_status_for_context_command(monkeypatch):
    bridge = load_bridge_module()
    bridge.BOT_QQ = "3975680980"
    bridge.MIN_SECONDS_BETWEEN_REPLIES = 0.0
    bridge.PROACTIVE_ENABLED = False
    bridge._recent_messages_by_group.clear()
    bridge._context_summaries_by_group.clear()

    async def fake_send(group_id, message):
        return {"status": "failed", "retcode": 200, "message": "Timeout"}

    monkeypatch.setattr(bridge, "send_group_msg", fake_send)

    class FakeRequest:
        async def json(self):
            return make_event(group_id=781423661, user_id=222, nickname="乙", text="/context")

    result = asyncio.run(bridge.onebot_event(FakeRequest()))

    assert result["ok"] is False
    assert result["replied"] is False
    assert result["error"] == "send_failed"
    assert result["trigger"] == "context_command"

