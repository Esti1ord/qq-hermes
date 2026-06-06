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


def test_group_knowledge_is_search_only_and_not_in_normal_prompts(tmp_path):
    bridge = load_bridge_module()
    bridge.GROUP_CONFIG_DIR = tmp_path / "groups"
    group_dir = bridge.GROUP_CONFIG_DIR / "781423661"
    group_dir.mkdir(parents=True)
    (group_dir / "knowledge.md").write_text("## 热门足球社区\n- 虎扑足球：https://bbs.hupu.com/soccer", encoding="utf-8")

    direct_prompt = bridge.build_prompt(make_event(text="虎扑怎么看", group_id=781423661), "虎扑怎么看")
    proactive_prompt = bridge.build_proactive_prompt(make_event(text="聊足球", group_id=781423661), ["topic:足球"])
    search_prompt = bridge.build_search_command_prompt("虎扑今天有什么足球新闻", 781423661)

    assert "本群知识库" not in direct_prompt
    assert "虎扑足球" not in direct_prompt
    assert "本群知识库" not in proactive_prompt
    assert "虎扑足球" not in proactive_prompt
    assert "本群知识库" in search_prompt
    assert "虎扑足球" in search_prompt


def test_missing_group_knowledge_uses_safe_fallback(tmp_path):
    bridge = load_bridge_module()
    bridge.GROUP_CONFIG_DIR = tmp_path / "groups"

    prompt = bridge.build_prompt(make_event(text="这个消息是真的吗"), "这个消息是真的吗")

    assert "本群没有配置知识库" not in prompt
    assert "涉及事实请优先依靠联网搜索" not in prompt


def test_prompt_requires_low_bot_feeling_without_fake_human_claims():
    bridge = load_bridge_module()

    prompt = bridge.build_prompt(make_event(text="你怎么看"), "你怎么看")

    assert "尽量别让人一眼看出你是机器人" in prompt
    assert "不要主动自称 AI、机器人、助手或模型" in prompt
    assert "不要编造真人经历" in prompt
    assert "标点风格强约束" in prompt
    assert "少用句号和逗号" in prompt
    assert "不要使用句号和引号" in prompt


def test_proactive_prompt_requires_low_bot_feeling_without_fake_human_claims():
    bridge = load_bridge_module()

    prompt = bridge.build_proactive_prompt(make_event(text="Esti 评价一下"), ["name:Esti"])

    assert "尽量别让人一眼看出你是机器人" in prompt
    assert "不要主动自称 AI、机器人、助手或模型" in prompt
    assert "不要编造真人经历" in prompt
    assert "标点风格强约束" in prompt
    assert "少用句号和逗号" in prompt
    assert "不要使用句号和引号" in prompt


def test_finalize_reply_applies_punctuation_style():
    bridge = load_bridge_module()
    bridge.PUNCTUATION_STYLE_ENABLED = True

    assert bridge.finalize_reply('"这个确实可以，不过别急。"') == "这个确实可以 不过别急"
    assert bridge.finalize_reply("A、B、C。") == "A B C"


def test_current_info_question_requires_web_search():
    bridge = load_bridge_module()
    assert bridge.needs_web_search("今晚国足比赛结果是多少") is True
    assert bridge.needs_web_search("这条最新转会新闻是真的吗") is True
    assert bridge.needs_web_search("今天英超积分榜怎么样") is True
    assert bridge.needs_web_search("介绍下今天发生的足球事件") is True
    assert bridge.needs_web_search("今天足坛发生了什么") is True
    assert bridge.needs_web_search("昨晚欧冠谁赢了") is True
    assert bridge.needs_web_search("昨天夜里欧冠谁赢了") is True
    assert bridge.needs_web_search("守望先锋十周年庆线下巡游什么时候到武汉") is True
    assert bridge.needs_web_search("音乐节门票什么时候开售") is True
    assert bridge.needs_web_search("解释一下 Python 的装饰器") is False


def test_realtime_sports_search_query_is_normalized():
    bridge = load_bridge_module()
    q = bridge.normalize_search_query("@Esti1ord 昨晚欧冠谁赢了")
    planned = bridge.plan_search_queries("@Esti1ord 昨晚欧冠谁赢了")

    assert "@Esti" not in q
    assert "欧冠" in q
    assert any("比分" in item or "赛果" in item or "官方" in item or "最新" in item for item in planned)
    assert any(str(year) in " ".join(planned) for year in range(2025, 2028))


def test_curl_search_filters_rate_limit_and_access_error_pages():
    bridge = load_bridge_module()

    error_pages = [
        '{"data":null,"retryAfter":20,"code":429,"name":"Function","message":"Per IP rate limit exceeded","readableMessage":"RateLimitTriggeredError"}',
        "Warning: Target URL returned error 429: Too Many Requests Warning: This page maybe requiring CAPTCHA",
        "Access Denied\nYou don't have permission to access this resource",
    ]

    for page in error_pages:
        assert bridge.usable_search_output(page) is False



def test_search_query_for_short_reference_uses_reply_and_recent_context(monkeypatch):
    bridge = load_bridge_module()
    group_id = 975805598
    bridge._recent_messages_by_group.clear()
    bridge.remember_message(make_event(text="HLTV Major 今天赛程好像出来了", group_id=group_id, user_id=222))
    event = make_event(text="这个消息是真的吗", group_id=group_id, user_id=111)
    event["message"] = [
        {"type": "reply", "data": {"text": "HLTV Major 今天赛程好像出来了", "qq": "222"}},
        {"type": "text", "data": {"text": "这个消息是真的吗"}},
    ]

    query = bridge.build_search_query("这个消息是真的吗", event=event, group_id=group_id)

    assert "这个消息是真的吗" in query
    assert "HLTV Major 今天赛程好像出来了" in query
    assert "群聊近期上下文" in query
    assert "被回复/引用消息" in query



def test_current_date_context_is_injected_into_search_and_reply_prompts(monkeypatch):
    bridge = load_bridge_module()
    monkeypatch.setattr(bridge, "run_web_search", lambda query: "没查到可靠结果")

    ctx = bridge.web_search_context_for_text("昨晚欧冠谁赢了")
    direct_prompt = bridge.build_prompt(make_event(text="昨晚欧冠谁赢了"), "昨晚欧冠谁赢了")
    proactive_prompt = bridge.build_proactive_prompt(make_event(text="昨晚欧冠谁赢了"), ["topic:足球"])

    assert "当前日期" in ctx
    assert "今天=" in ctx
    assert "昨天=" in ctx
    assert "不要用去年" in ctx or "不要把去年" in ctx
    for text in [direct_prompt, proactive_prompt]:
        assert "当前日期" in text
        assert "今天=" in text
        assert "昨天=" in text
        assert "联网搜索结果" not in text
        assert "不要用去年" not in text


def test_curl_search_stops_after_enough_successful_fetches(monkeypatch):
    bridge = load_bridge_module()
    bridge.WEB_SEARCH_HTTP_TIMEOUT = 1
    calls = []

    class FakeCurl:
        returncode = 0
        stdout = "可靠搜索摘录：官方确认今天有比赛。"
        stderr = ""

    class FakeVerify:
        returncode = 0
        stdout = "官方确认今天有比赛\n\nsession_id: fake"
        stderr = ""

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd and cmd[0] == "curl":
            return FakeCurl()
        return FakeVerify()

    monkeypatch.setattr(bridge.subprocess, "run", fake_run)

    result = bridge.run_curl_search("今天足球发生了什么")

    curl_cmds = [cmd for cmd in calls if cmd and cmd[0] == "curl"]
    assert len(curl_cmds) <= 3
    assert result == "官方确认今天有比赛"


def test_curl_search_ignores_jina_error_pages_and_continues(monkeypatch):
    bridge = load_bridge_module()
    bridge.WEB_SEARCH_HTTP_TIMEOUT = 1
    calls = []

    class FakeError:
        returncode = 0
        stdout = '{"data":null,"code":451,"name":"SecurityCompromiseError","message":"blocked"}'
        stderr = ""

    class FakeGood:
        returncode = 0
        stdout = "搜索结果：官方消息显示今晚比赛延期。"
        stderr = ""

    class FakeVerify:
        returncode = 0
        stdout = "官方消息显示今晚比赛延期\n\nsession_id: fake"
        stderr = ""

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd and cmd[0] == "curl":
            curl_count = sum(1 for c in calls if c and c[0] == "curl")
            return FakeError() if curl_count == 1 else FakeGood()
        return FakeVerify()

    monkeypatch.setattr(bridge.subprocess, "run", fake_run)

    result = bridge.run_curl_search("今晚比赛延期消息是真的吗")

    verify_prompt = next(cmd[3] for cmd in calls if cmd[:3] == [bridge.HERMES_BIN, "chat", "-q"])
    assert "SecurityCompromiseError" not in verify_prompt
    assert "blocked" not in verify_prompt
    assert "官方消息显示今晚比赛延期" in verify_prompt
    assert result == "官方消息显示今晚比赛延期"


def test_curl_search_filters_google_429_warning_pages():
    bridge = load_bridge_module()
    page = """Title: https://www.google.com/search?q=北京天气
Warning: Target URL returned error 429: Too Many Requests
Warning: This page maybe requiring CAPTCHA, please make sure you are authorized."""

    assert bridge.usable_search_output(page) is False


def test_search_command_curl_uses_clean_query_not_internal_prompt(monkeypatch):
    bridge = load_bridge_module()
    bridge.WEB_SEARCH_BACKEND = "curl"
    seen = []

    def fake_run_web_search(query):
        seen.append(query)
        return "北京今天多云转阴 午后有雷阵雨"

    monkeypatch.setattr(bridge, "run_web_search", fake_run_web_search)

    reply = bridge.build_search_command_reply("今天北京天气", group_id=975805598)

    assert reply == "北京今天多云转阴 午后有雷阵雨"
    assert seen == ["今天北京天气"]


def test_search_verifier_only_applies_sports_match_rule_to_sports_queries(monkeypatch):
    bridge = load_bridge_module()
    bridge.WEB_SEARCH_HTTP_TIMEOUT = 1
    calls = []

    class FakeCurl:
        returncode = 0
        stdout = "北京天气预报：今天多云转阴，午后有雷阵雨，最高29℃。"
        stderr = ""

    class FakeVerify:
        returncode = 0
        stdout = "北京今天多云转阴，午后有雷阵雨，最高29℃\n\nsession_id: fake"
        stderr = ""

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd and cmd[0] == "curl":
            return FakeCurl()
        return FakeVerify()

    monkeypatch.setattr(bridge.subprocess, "run", fake_run)

    result = bridge.run_curl_search("今天北京天气")

    verify_prompt = next(cmd[3] for cmd in calls if cmd[:3] == [bridge.HERMES_BIN, "chat", "-q"])
    assert "不要套用体育/赛事校验" in verify_prompt
    assert "如果问欧冠" not in verify_prompt
    assert result == "北京今天多云转阴，午后有雷阵雨，最高29℃"


def test_football_digest_search_uses_multiple_queries_and_no_timeout_leak(monkeypatch):
    bridge = load_bridge_module()
    bridge.WEB_SEARCH_HTTP_TIMEOUT = 1
    bridge.WEB_SEARCH_MAX_SUCCESSFUL_FETCHES = 99
    calls = []

    class FakeCurl:
        returncode = 0
        stdout = "今日足球新闻：某队官宣转会，某比赛结束。"
        stderr = ""

    class FakeVerify:
        returncode = 0
        stdout = "今天足坛主要有转会官宣和一场比赛结束\n\nsession_id: fake"
        stderr = ""

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd and cmd[0] == "curl":
            return FakeCurl()
        return FakeVerify()

    monkeypatch.setattr(bridge.subprocess, "run", fake_run)

    result = bridge.run_curl_search("介绍下今天发生的足球事件")

    curl_cmds = [cmd for cmd in calls if cmd and cmd[0] == "curl"]
    assert len(curl_cmds) >= 14
    urls = [cmd[-1] for cmd in curl_cmds]
    assert any("www.baidu.com/s" in url for url in urls)
    assert any("cn.bing.com/search" in url for url in urls)
    assert any("www.sogou.com/web" in url for url in urls)
    assert any("www.so.com/s" in url for url in urls)
    assert any("www.google.com/search" in url for url in urls)
    assert any("%E5%AE%98%E6%96%B9" in url or "%E6%9C%80%E6%96%B0" in url for url in urls)
    assert all("--noproxy" not in cmd for cmd in curl_cmds)
    assert result == "今天足坛主要有转会官宣和一场比赛结束"
    assert bridge.finalize_reply("⏱ Timeout — denying command\n今天没查准") == "今天没查准"


def test_curl_search_verification_prompt_requires_event_match(monkeypatch):
    bridge = load_bridge_module()
    bridge.WEB_SEARCH_HTTP_TIMEOUT = 1
    calls = []

    class FakeCurl:
        returncode = 0
        stdout = "NBA 西决 雷霆赢了"
        stderr = ""

    class FakeVerify:
        returncode = 0
        stdout = "没查到可靠结果\n\nsession_id: fake"
        stderr = ""

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd and cmd[0] == "curl":
            return FakeCurl()
        return FakeVerify()

    monkeypatch.setattr(bridge.subprocess, "run", fake_run)

    result = bridge.run_curl_search("昨晚欧冠谁赢了")

    assert result == "没查到可靠结果"
    verify_prompt = next(cmd[3] for cmd in calls if cmd[:3] == [bridge.HERMES_BIN, "chat", "-q"])
    assert "当前日期" in verify_prompt
    assert "今天=" in verify_prompt
    assert "昨天=" in verify_prompt
    assert "不要默认成去年" in verify_prompt
    assert "不要把 NBA、其他足球比赛或旧比赛当成欧冠" in verify_prompt
    assert "如果问欧冠，只回答欧冠/UEFA Champions League" in verify_prompt
    assert "昨晚欧冠谁赢了" in verify_prompt


def test_search_query_planner_builds_generic_variants_for_names_dates_and_context():
    bridge = load_bridge_module()
    query = "原问题：查下今晚major赛程，简单评价一下\n群聊近期上下文：群友：刚才说的是HLTV Major"

    planned = bridge.plan_search_queries(query)

    assert planned[0].startswith("原问题：查下今晚major赛程")
    assert any("HLTV" in q and "Major" in q for q in planned)
    assert any("2026" in q for q in planned)
    assert len(planned) >= 3
    assert len(planned) == len(dict.fromkeys(planned))



def test_search_urls_include_generic_candidate_urls_from_query():
    bridge = load_bridge_module()
    urls = bridge.search_urls_for_query("今晚比赛 https://example.com/news/a hltv.org/matches")

    assert "https://r.jina.ai/https://example.com/news/a" in urls
    assert "https://r.jina.ai/http://hltv.org/matches" in urls
    assert any("www.baidu.com/s" in url for url in urls)



def test_search_urls_include_domestic_and_international_engines():
    bridge = load_bridge_module()
    urls = bridge.search_urls_for_query("中超 今天 比赛 赛果")

    assert any("www.baidu.com/s" in url for url in urls)
    assert any("www.bing.com/search" in url for url in urls)
    assert any("cn.bing.com/search" in url for url in urls)
    assert any("www.sogou.com/web" in url for url in urls)
    assert any("www.so.com/s" in url for url in urls)
    assert any("www.google.com/search" in url for url in urls)
    assert any("duckduckgo.com/html" in url for url in urls)


def test_normal_reply_prompts_do_not_inject_search_context(monkeypatch):
    bridge = load_bridge_module()
    monkeypatch.setattr(bridge, "run_web_search", lambda query: (_ for _ in ()).throw(AssertionError("normal prompt must not search")))

    prompt = bridge.build_prompt(make_event(text="这条最新比赛延期消息是真的吗"), "这条最新比赛延期消息是真的吗")

    assert "联网搜索结果" not in prompt
    assert "官方确认比赛延期" not in prompt



def test_proactive_prompt_does_not_inject_search_context(monkeypatch):
    bridge = load_bridge_module()
    monkeypatch.setattr(bridge, "run_web_search", lambda query: (_ for _ in ()).throw(AssertionError("proactive prompt must not search")))

    prompt = bridge.build_proactive_prompt(make_event(text="这个最新转会瓜好像很真"), ["topic:足球"])

    assert "联网搜索结果" not in prompt
    assert "转会还未官宣" not in prompt


def test_obviously_non_current_messages_do_not_search_even_with_time_words(monkeypatch):
    bridge = load_bridge_module()
    searched = []
    monkeypatch.setattr(bridge, "run_web_search", lambda query: searched.append(query) or "不该搜索")

    examples = [
        "今天好累啊",
        "今晚吃什么",
        "现在有点困",
        "刚才笑死我了",
        "目前这个代码怎么写",
        "结果我还是没懂 Python 装饰器",
        "这个梗是什么意思",
    ]
    for text in examples:
        assert bridge.needs_web_search(text) is False
        bridge.web_search_context_for_text(text)

    assert searched == []


def test_search_command_uses_search_model_and_search_only_knowledge(monkeypatch, tmp_path):
    bridge = load_bridge_module()
    bridge.GROUP_CONFIG_DIR = tmp_path / "groups"
    group_id = 781423661
    group_dir = bridge.GROUP_CONFIG_DIR / str(group_id)
    group_dir.mkdir(parents=True)
    (group_dir / "knowledge.md").write_text("## 搜索专用源\n- HLTV：https://www.hltv.org", encoding="utf-8")
    bridge.WEB_SEARCH_BACKEND = "llm"
    bridge.HERMES_MODEL = "ordinary-chat-model"
    bridge.HERMES_PROVIDER = "ordinary-chat-provider"
    bridge.WEB_SEARCH_MODEL = "search-model"
    bridge.WEB_SEARCH_PROVIDER = "search-provider"
    calls = []

    class FakeRun:
        returncode = 0
        stdout = "HLTV 显示今晚有比赛\n\nsession_id: fake"
        stderr = ""

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return FakeRun()

    monkeypatch.setattr(bridge.subprocess, "run", fake_run)

    reply = bridge.build_search_command_reply("今晚major赛程", group_id=group_id)

    assert "HLTV 显示今晚有比赛" in reply
    cmd = calls[0]
    assert "--model" in cmd
    assert cmd[cmd.index("--model") + 1] == "search-model"
    assert "--provider" in cmd
    assert cmd[cmd.index("--provider") + 1] == "search-provider"
    assert "--continue" not in cmd
    prompt = cmd[3]
    assert "本群知识库" in prompt
    assert "HLTV" in prompt


def test_search_command_short_blessing_fallback_is_not_sports_no_match(monkeypatch):
    bridge = load_bridge_module()
    monkeypatch.setattr(bridge, "run_web_search", lambda query: bridge.REPLY_TEMPLATES["web_search_no_match"][0])

    reply = bridge.build_search_command_reply("高考加油", group_id=975805598)

    assert "高考加油" in reply
    assert "赛事" not in reply
    assert "比赛" not in reply
    assert "别拿" not in reply


def test_search_no_match_templates_are_generic_not_sports_specific():
    bridge = load_bridge_module()

    for template in bridge.REPLY_TEMPLATES["web_search_no_match"]:
        assert "赛事" not in template
        assert "比赛" not in template
        assert "旧赛季" not in template


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


def test_jrrp_command_requires_exact_message():
    bridge = load_bridge_module()

    assert bridge.is_jrrp_command("jrrp") is True
    assert bridge.is_jrrp_command("JRRP") is True
    assert bridge.is_jrrp_command(" jrrp ") is True
    assert bridge.is_jrrp_command("今天jrrp") is False
    assert bridge.is_jrrp_command("jrrp一下") is False
    assert bridge.is_jrrp_command("我的 jrrp 怎么样") is False
    assert bridge.is_jrrp_command("@Esti jrrp") is False


def test_search_still_triggers_for_explicit_current_facts(monkeypatch):
    bridge = load_bridge_module()
    searched = []
    monkeypatch.setattr(bridge, "run_web_search", lambda query: searched.append(query) or "搜索结果：官方消息。")

    examples = [
        "今晚国足比赛结果是多少",
        "这条最新转会新闻是真的吗",
        "今天英超积分榜怎么样",
        "明天天气怎么样",
        "现在黄金价格多少",
    ]
    for text in examples:
        assert bridge.needs_web_search(text) is True
        bridge.web_search_context_for_text(text)

    assert searched == examples
