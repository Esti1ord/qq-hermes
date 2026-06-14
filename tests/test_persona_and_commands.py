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


def make_event(text="今天新闻是真的吗", group_id=975805598, user_id=111, self_id=3975680980):
    return {
        "post_type": "message",
        "message_type": "group",
        "group_id": group_id,
        "user_id": user_id,
        "self_id": self_id,
        "sender": {"nickname": "群友"},
        "message": [{"type": "text", "data": {"text": text}}],
    }


def test_persona_is_split_into_base_and_group_prompt(tmp_path):
    bridge = load_bridge_module()
    bridge.BASE_PERSONA_FILE = tmp_path / "base_persona.md"
    bridge.GROUP_CONFIG_DIR = tmp_path / "groups"
    group_dir = bridge.GROUP_CONFIG_DIR / "975805598"
    group_dir.mkdir(parents=True)
    bridge.BASE_PERSONA_FILE.write_text("基础人设：像朋友。", encoding="utf-8")
    (group_dir / "persona.md").write_text("本群提示：足球群。", encoding="utf-8")

    combined = bridge.persona_bundle_for_prompt(975805598)

    assert "基础人设：像朋友。" in combined
    assert "本群提示：足球群。" in combined
    assert combined.index("基础人设") < combined.index("本群提示")


def test_build_prompt_labels_base_and_group_persona(tmp_path):
    bridge = load_bridge_module()
    bridge.BASE_PERSONA_FILE = tmp_path / "base_persona.md"
    bridge.GROUP_CONFIG_DIR = tmp_path / "groups"
    group_dir = bridge.GROUP_CONFIG_DIR / "975805598"
    group_dir.mkdir(parents=True)
    bridge.BASE_PERSONA_FILE.write_text("基础人设：Esti。", encoding="utf-8")
    (group_dir / "persona.md").write_text("本群提示：技术群。", encoding="utf-8")

    prompt = bridge.build_prompt(make_event(text="怎么看这个"), "怎么看这个")

    assert "基础人设" in prompt
    assert "群聊提示词" in prompt
    assert "基础人设：Esti。" in prompt
    assert "本群提示：技术群。" in prompt


def test_group_knowledge_is_not_in_normal_prompts(tmp_path):
    bridge = load_bridge_module()
    bridge.GROUP_CONFIG_DIR = tmp_path / "groups"
    group_dir = bridge.GROUP_CONFIG_DIR / "781423661"
    group_dir.mkdir(parents=True)
    (group_dir / "knowledge.md").write_text("## 热门足球社区\n- 虎扑足球：https://bbs.hupu.com/soccer", encoding="utf-8")

    direct_prompt = bridge.build_prompt(make_event(text="虎扑怎么看", group_id=781423661), "虎扑怎么看")
    proactive_prompt = bridge.build_proactive_prompt(make_event(text="聊足球", group_id=781423661), ["topic:足球"])

    assert "虎扑足球" not in direct_prompt
    assert "虎扑足球" not in proactive_prompt


def test_missing_group_knowledge_uses_safe_fallback(tmp_path):
    bridge = load_bridge_module()
    bridge.GROUP_CONFIG_DIR = tmp_path / "groups"

    prompt = bridge.build_prompt(make_event(text="这个消息是真的吗"), "这个消息是真的吗")

    assert "本群没有配置知识库" not in prompt
    assert "涉及事实请优先依靠联网搜索" not in prompt


def test_reply_prompts_require_low_bot_feeling_without_fake_human_claims():
    bridge = load_bridge_module()

    prompts = [
        bridge.build_prompt(make_event(text="你怎么看"), "你怎么看"),
        bridge.build_proactive_prompt(make_event(text="Esti 评价一下"), ["name:Esti"]),
    ]

    for prompt in prompts:
        assert "尽量别让人一眼看出你是机器人" in prompt
        assert "不要主动自称 AI、机器人、助手或模型" in prompt
        assert "不要编造真人经历" in prompt
        assert "标点按自然表达保留" in prompt
        assert "强行删除句号、逗号、引号或网址里的点号" in prompt
        assert "标点风格强约束" not in prompt
        assert "少用句号和逗号" not in prompt
        assert "不要使用句号和引号" not in prompt


def test_finalize_reply_preserves_punctuation_by_default():
    bridge = load_bridge_module()

    assert bridge.PUNCTUATION_STYLE_ENABLED is False
    assert bridge.finalize_reply('"这个确实可以，不过别急。"') == '"这个确实可以，不过别急。"'
    assert bridge.finalize_reply("来源：https://code.claude.com/docs/en/fast-mode。") == "来源：https://code.claude.com/docs/en/fast-mode。"


def test_finalize_reply_applies_punctuation_style_when_enabled():
    bridge = load_bridge_module()
    bridge.PUNCTUATION_STYLE_ENABLED = True

    assert bridge.finalize_reply('"这个确实可以，不过别急。"') == "这个确实可以 不过别急"
    assert bridge.finalize_reply("A、B、C。") == "A B C"


def test_current_date_context_is_injected_into_reply_prompts():
    bridge = load_bridge_module()

    direct_prompt = bridge.build_prompt(make_event(text="昨晚欧冠谁赢了"), "昨晚欧冠谁赢了")
    proactive_prompt = bridge.build_proactive_prompt(make_event(text="昨晚欧冠谁赢了"), ["topic:足球"])

    for text in [direct_prompt, proactive_prompt]:
        assert "当前日期" in text
        assert "今天=" in text
        assert "昨天=" in text
        assert "联网搜索结果" not in text
        assert "不要用去年" not in text


def test_normal_reply_prompts_do_not_inject_search_context():
    bridge = load_bridge_module()

    prompt = bridge.build_prompt(make_event(text="这条最新比赛延期消息是真的吗"), "这条最新比赛延期消息是真的吗")

    assert "联网搜索结果" not in prompt
    assert "官方确认比赛延期" not in prompt



def test_proactive_prompt_does_not_inject_search_context():
    bridge = load_bridge_module()

    prompt = bridge.build_proactive_prompt(make_event(text="这个最新转会瓜好像很真"), ["topic:足球"])

    assert "联网搜索结果" not in prompt
    assert "转会还未官宣" not in prompt


def test_jrrp_keyword_sends_deterministic_once_per_day_without_llm(monkeypatch, tmp_path):
    bridge = load_bridge_module()
    bridge.JRRP_STATE_FILE = tmp_path / "jrrp_state.json"
    bridge.JRRP_RESULTS_FILE = tmp_path / "jrrp_results.json"
    bridge.JRRP_RESULTS_FILE.write_text("""
{
  "levels": [
    {"name": "天选之人", "min": 100, "max": 100, "faces": ["✧*｡٩(ˊᗜˋ*)و✧*｡"], "comments": ["今日运势突破上限，随机数都在偏爱你。"]},
    {"name": "小吉", "min": 60, "max": 74, "faces": ["(・ω・)ノ"], "comments": ["小有好运，适合做点轻松的事。"]}
  ]
}
""".strip(), encoding="utf-8")
    bridge.MIN_SECONDS_BETWEEN_REPLIES = 0.0
    bridge._last_reply_at = 0.0
    sent = []
    hermes_calls = []

    monkeypatch.setattr(bridge, "run_hermes", lambda *args, **kwargs: hermes_calls.append(args) or "不该调用")
    monkeypatch.setattr(bridge, "run_hermes_raw", lambda *args, **kwargs: hermes_calls.append(args) or "不该调用")

    class FixedDateTime(bridge.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 6, 2, 21, 5, 25, tzinfo=tz)

    monkeypatch.setattr(bridge, "datetime", FixedDateTime)

    async def fake_send(group_id, message):
        sent.append((group_id, message))
        return {"ok": True}

    monkeypatch.setattr(bridge, "send_group_msg", fake_send)

    class FakeRequest:
        def __init__(self, text):
            self.text = text
        async def json(self):
            event = make_event(text=self.text, user_id=44866989)
            event["sender"] = {"nickname": "曲"}
            event["message_id"] = self.text + "-" + str(id(self))
            return event

    first = asyncio.run(bridge.onebot_event(FakeRequest("jrrp")))
    second = asyncio.run(bridge.onebot_event(FakeRequest("jrrp")))

    assert first["trigger"] == "jrrp"
    assert first["replied"] is True
    assert second["trigger"] == "jrrp"
    assert second["replied"] is True
    assert sent[0][1].startswith("@曲 今日人品：")
    assert "/100" in sent[0][1]
    assert "判定：" in sent[0][1]
    assert "种子" not in sent[0][1]
    assert "2026060221052544866989" not in sent[0][1]
    assert sent[1][1] == "你今日已经抽过了"
    assert hermes_calls == []


def test_direct_only_knobs_do_not_affect_jrrp_command(monkeypatch, tmp_path):
    bridge = load_bridge_module()
    bridge.JRRP_STATE_FILE = tmp_path / "jrrp_state.json"
    bridge.JRRP_RESULTS_FILE = tmp_path / "jrrp_results.json"
    bridge.JRRP_RESULTS_FILE.write_text("""
{
  "levels": [
    {"name": "天选之人", "min": 100, "max": 100, "faces": ["✧*｡٩(ˊᗜˋ*)و✧*｡"], "comments": ["今日运势突破上限，随机数都在偏爱你。"]},
    {"name": "小吉", "min": 60, "max": 74, "faces": ["(・ω・)ノ"], "comments": ["小有好运，适合做点轻松的事。"]}
  ]
}
""".strip(), encoding="utf-8")
    bridge.MIN_SECONDS_BETWEEN_REPLIES = 0.0
    bridge._last_reply_at = 0.0
    bridge.DIRECT_FAST_MODEL_ALIAS = "direct-fast-test"
    bridge.DIRECT_STRONG_MODEL_ALIAS = "direct-strong-test"
    bridge.DIRECT_CHAT_MODEL_PROVIDER = "custom"
    bridge.DIRECT_CHAT_MODEL_BASE_URL = "configured-direct-base-url"
    bridge.DIRECT_CHAT_MODEL_API_KEY_ENV = "DIRECT_TEST_KEY"
    bridge.DIRECT_MODEL_TIMEOUT_SECONDS = 3
    bridge.DIRECT_MAX_OUTPUT_CHARS = 24
    sent = []
    hermes_calls = []

    monkeypatch.setattr(bridge, "run_hermes", lambda *args, **kwargs: hermes_calls.append(("hermes", args, kwargs)) or "不该调用")
    monkeypatch.setattr(bridge, "run_hermes_raw", lambda *args, **kwargs: hermes_calls.append(("raw", args, kwargs)) or "不该调用")
    monkeypatch.setattr(bridge, "run_direct_hermes_raw", lambda *args, **kwargs: hermes_calls.append(("direct", args, kwargs)) or "不该调用")

    async def fake_send(group_id, message):
        sent.append((group_id, message))
        return {"ok": True}

    monkeypatch.setattr(bridge, "send_group_msg", fake_send)

    class FakeRequest:
        async def json(self):
            event = make_event(text="jrrp", user_id=44866989)
            event["sender"] = {"nickname": "曲"}
            event["message_id"] = "direct-knobs-jrrp"
            return event

    result = asyncio.run(bridge.onebot_event(FakeRequest()))

    assert result["trigger"] == "jrrp"
    assert result["replied"] is True
    assert sent[0][1].startswith("@曲 今日人品：")
    assert hermes_calls == []

def test_jrrp_command_requires_exact_message():
    bridge = load_bridge_module()

    assert bridge.is_jrrp_command("jrrp") is True
    assert bridge.is_jrrp_command("JRRP") is True
    assert bridge.is_jrrp_command(" jrrp ") is True
    assert bridge.is_jrrp_command("今天jrrp") is False
    assert bridge.is_jrrp_command("jrrp一下") is False
    assert bridge.is_jrrp_command("我的 jrrp 怎么样") is False
    assert bridge.is_jrrp_command("@Esti jrrp") is False
