import asyncio
import importlib.util
from pathlib import Path

from qq_hermes_bridge import media, media_fetch, vision

BRIDGE_PATH = Path(__file__).resolve().parents[1] / "bridge.py"


def load_bridge_module():
    spec = importlib.util.spec_from_file_location("bridge_under_test_ocr", BRIDGE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def configure_bridge(bridge):
    bridge.MIN_SECONDS_BETWEEN_REPLIES = 0.0
    bridge.USER_COOLDOWN_SECONDS = 0.0
    bridge.MAX_PENDING_DIRECT_REPLIES = 20
    bridge.OCR_ENABLED = True
    bridge.OCR_EXTERNAL_PROVIDER_ALLOWED = True
    bridge.OCR_PROVIDER = "mock"
    bridge.OCR_INCLUDE_IN_PROMPT = True
    bridge.OCR_INCLUDE_IN_CONTEXT = True
    bridge.OCR_PERSIST_TEXT_IN_CONTEXT = False
    bridge.OCR_MAX_IMAGES_PER_MESSAGE = 1
    bridge.OCR_MAX_RESULT_CHARS = 500
    bridge.OCR_TRIGGER_MODE = "direct_only"
    bridge.OCR_CONTEXT_GROUP_IDS = set()
    bridge.OCR_MAX_CONCURRENT_TASKS = 2
    bridge.OCR_CACHE_TTL_SECONDS = 3600
    bridge.OCR_CACHE_MAX_ENTRIES = 512
    bridge._ocr_result_cache.clear()
    bridge._ocr_inflight.clear()
    bridge._ocr_context_tasks.clear()
    bridge._ocr_semaphore = None
    bridge.CONTEXT_PERSIST_ENABLED = False
    bridge._recent_messages_by_group.clear()
    bridge._last_user_reply_at.clear()
    bridge._recent_messages.clear()
    bridge._processed_event_keys.clear()
    bridge._processed_event_key_set.clear()
    bridge._reply_queue_by_group.clear()
    bridge._reply_workers_by_group.clear()
    bridge._outbound_inflight_by_group.clear()


class FakeRequest:
    def __init__(self, event):
        self.event = event

    async def json(self):
        return self.event


def make_image_at_event(message_id=901):
    return {
        "post_type": "message",
        "message_type": "group",
        "group_id": 975805598,
        "user_id": 111,
        "self_id": 3975680980,
        "message_id": message_id,
        "sender": {"nickname": "群友"},
        "message": [
            {"type": "at", "data": {"qq": "3975680980", "name": "Esti"}},
            {"type": "text", "data": {"text": " 看下这张图"}},
            {"type": "image", "data": {"file": "diet.png", "url": "https://cdn.example.test/diet.png"}},
        ],
    }


def test_direct_image_message_adds_ocr_to_prompt_and_context(monkeypatch):
    bridge = load_bridge_module()
    configure_bridge(bridge)
    prompts = []
    sent = []

    async def fake_fetch(ref, **kwargs):
        return media_fetch.MediaFetchResult(
            ref=ref,
            status="ok",
            content=b"image",
            content_type="image/png",
            source_host="cdn.example.test",
            status_code=200,
        )

    monkeypatch.setattr(bridge.media_fetch, "fetch_onebot_image", fake_fetch)
    monkeypatch.setattr(bridge, "build_ocr_provider", lambda: vision.MockVisionProvider(text="午饭米饭250g 面包75g 饮食建议", description="GPT饮食健康对话截图"))

    def fake_run_hermes_raw(prompt, group_id=None, use_group_session=True):
        prompts.append(prompt)
        return "识图回复"

    async def fake_send(group_id, message):
        sent.append((group_id, message))
        return {"ok": True}

    monkeypatch.setattr(bridge, "run_hermes_raw", fake_run_hermes_raw)
    monkeypatch.setattr(bridge, "send_group_msg", fake_send)

    async def run():
        result = await bridge.onebot_event(FakeRequest(make_image_at_event()))
        await bridge.wait_reply_worker(975805598)
        return result

    result = asyncio.run(run())

    assert result["queued"] is True
    assert sent == [(975805598, "[CQ:reply,id=901]识图回复")]
    assert "当前消息或被回复/引用消息的图片识别结果" in prompts[0]
    assert "午饭米饭250g" in prompts[0]
    recent = list(bridge.recent_messages_for_group(975805598))
    human = recent[0]
    assert "[图片]" in human["text"]
    assert "午饭米饭250g" in human["text"]
    assert human["text_without_ocr"] == "看下这张图[图片]"
    assert human["ocr_text_nonpersistent"] is True


def test_direct_image_message_emits_ocr_performance_stats(monkeypatch):
    bridge = load_bridge_module()
    configure_bridge(bridge)
    bridge.RUNTIME_STATS_ENABLED = True
    bridge.PERF_OBS_ENABLED = True
    stats = []

    monkeypatch.setattr(bridge, "runtime_stat", lambda stat, **fields: stats.append({"stat": stat, **fields}))

    async def fake_fetch(ref, **kwargs):
        return media_fetch.MediaFetchResult(
            ref=ref,
            status="ok",
            content=b"image",
            content_type="image/png",
            source_host="cdn.example.test",
            status_code=200,
        )

    monkeypatch.setattr(bridge.media_fetch, "fetch_onebot_image", fake_fetch)
    monkeypatch.setattr(bridge, "build_ocr_provider", lambda: vision.MockVisionProvider(text="SECRET_OCR_TEXT_123", description="SECRET_DESCRIPTION_123"))

    async def run_once():
        result = await bridge.recognize_media_for_event(make_image_at_event(), route="direct")
        return result

    result = asyncio.run(run_once())

    assert result["results"][0].status == "ok"
    names = {item["stat"] for item in stats}
    assert "ocr_fetch_result" in names
    assert "ocr_provider_result" in names
    assert "ocr_cache_event" in names
    assert "ocr_route_result" in names
    rendered = repr(stats)
    assert "SECRET_OCR_TEXT_123" not in rendered
    assert "SECRET_DESCRIPTION_123" not in rendered
    assert "cdn.example.test" not in rendered
    route = next(item for item in stats if item["stat"] == "ocr_route_result")
    assert route["media_count"] == 1
    assert route["ok_count"] == 1


def test_ocr_context_persistence_strips_nonpersistent_text(monkeypatch, tmp_path):
    bridge = load_bridge_module()
    configure_bridge(bridge)
    bridge.CONTEXT_PERSIST_ENABLED = True
    bridge.CONTEXT_CACHE_FILE = tmp_path / "recent_context.jsonl"

    item = {
        "user_id": 1,
        "name": "群友",
        "text": "[图片]\n- 图片1：文字：私密OCR",
        "text_without_ocr": "[图片]",
        "ocr_text_nonpersistent": True,
    }

    bridge.remember_message_item(975805598, item)

    saved = bridge.CONTEXT_CACHE_FILE.read_text(encoding="utf-8")
    assert "私密OCR" not in saved
    assert "text_without_ocr" not in saved
    assert "ocr_text_nonpersistent" not in saved
    assert "[图片]" in saved
def make_image_context_event(message_id=1001, group_id=975805598, url="https://cdn.example.test/context.png", text="群里发图"):
    return {
        "post_type": "message",
        "message_type": "group",
        "group_id": group_id,
        "user_id": 222,
        "self_id": 3975680980,
        "message_id": message_id,
        "sender": {"nickname": "群友"},
        "message": [
            {"type": "text", "data": {"text": text}},
            {"type": "image", "data": {"file": "context.png", "url": url}},
        ],
    }


def make_reply_to_image_name_event(message_id=1002, reply_to=1001, text="Esti 帮我看下这张图"):
    return {
        "post_type": "message",
        "message_type": "group",
        "group_id": 975805598,
        "user_id": 333,
        "self_id": 3975680980,
        "message_id": message_id,
        "sender": {"nickname": "提问者"},
        "message": [
            {"type": "reply", "data": {"message_id": str(reply_to)}},
            {"type": "text", "data": {"text": text}},
        ],
    }


def make_embedded_reply_image_event(message_id=1003):
    return {
        "post_type": "message",
        "message_type": "group",
        "group_id": 975805598,
        "user_id": 333,
        "self_id": 3975680980,
        "message_id": message_id,
        "sender": {"nickname": "提问者"},
        "message": [
            {
                "type": "reply",
                "data": {
                    "message_id": "quoted-1",
                    "message": [
                        {"type": "image", "data": {"file": "quoted.png", "url": "https://cdn.example.test/quoted.png"}}
                    ],
                },
            },
            {"type": "text", "data": {"text": "小E 看看"}},
        ],
    }


def test_name_reply_to_cached_image_triggers_direct_ocr(monkeypatch):
    bridge = load_bridge_module()
    configure_bridge(bridge)
    prompts = []
    sent = []
    calls = []

    async def fake_fetch(ref, **kwargs):
        calls.append(ref)
        return media_fetch.MediaFetchResult(
            ref=ref,
            status="ok",
            content=b"image",
            content_type="image/png",
            source_host="cdn.example.test",
            status_code=200,
        )

    monkeypatch.setattr(bridge.media_fetch, "fetch_onebot_image", fake_fetch)
    monkeypatch.setattr(bridge, "build_ocr_provider", lambda: vision.MockVisionProvider(text="被回复图片OCR", description="被回复图片描述"))

    def fake_run_hermes_raw(prompt, group_id=None, use_group_session=True):
        prompts.append(prompt)
        return "引用识图回复"

    async def fake_send(group_id, message):
        sent.append((group_id, message))
        return {"ok": True}

    monkeypatch.setattr(bridge, "run_hermes_raw", fake_run_hermes_raw)
    monkeypatch.setattr(bridge, "send_group_msg", fake_send)

    async def run():
        first = await bridge.onebot_event(FakeRequest(make_image_context_event(message_id=1001, url="https://cdn.example.test/cached.png")))
        second = await bridge.onebot_event(FakeRequest(make_reply_to_image_name_event(message_id=1002, reply_to=1001)))
        await bridge.wait_reply_worker(975805598)
        return first, second

    first, second = asyncio.run(run())

    assert first["ignored"] == "not_at_me"
    assert second["queued"] is True
    assert len(calls) == 1
    assert calls[0].url == "https://cdn.example.test/cached.png"
    assert "被回复图片OCR" in prompts[0]
    assert sent == [(975805598, "[CQ:reply,id=1002]引用识图回复")]
    recent = list(bridge.recent_messages_for_group(975805598))
    assert "media_refs" in recent[0]
    assert "被回复图片OCR" in recent[-2]["text"]


def test_direct_ocr_reads_embedded_reply_image_without_recent_cache(monkeypatch):
    bridge = load_bridge_module()
    configure_bridge(bridge)
    calls = []

    async def fake_fetch(ref, **kwargs):
        calls.append(ref)
        return media_fetch.MediaFetchResult(ref=ref, status="ok", content=b"image", content_type="image/png")

    monkeypatch.setattr(bridge.media_fetch, "fetch_onebot_image", fake_fetch)
    monkeypatch.setattr(bridge, "build_ocr_provider", lambda: vision.MockVisionProvider(text="内嵌引用OCR"))

    result = asyncio.run(bridge.recognize_media_for_event(make_embedded_reply_image_event(), route="direct"))

    assert len(calls) == 1
    assert calls[0].url == "https://cdn.example.test/quoted.png"
    assert result["results"][0].status == "ok"
    assert "内嵌引用OCR" in result["media_context"]


def test_non_direct_reply_to_image_does_not_ocr_quoted_image(monkeypatch):
    bridge = load_bridge_module()
    configure_bridge(bridge)
    calls = []

    async def fake_fetch(ref, **kwargs):
        calls.append(ref)
        return media_fetch.MediaFetchResult(ref=ref, status="ok", content=b"image", content_type="image/png")

    monkeypatch.setattr(bridge.media_fetch, "fetch_onebot_image", fake_fetch)
    monkeypatch.setattr(bridge, "build_ocr_provider", lambda: vision.MockVisionProvider(text="不应出现"))

    async def run():
        await bridge.onebot_event(FakeRequest(make_image_context_event(message_id=1101, url="https://cdn.example.test/non-direct.png")))
        result = await bridge.onebot_event(FakeRequest(make_reply_to_image_name_event(message_id=1102, reply_to=1101, text="看看这张")))
        await bridge.wait_ocr_context_tasks(975805598)
        return result

    result = asyncio.run(run())

    assert result["ignored"] == "not_at_me"
    assert calls == []


def test_context_persistence_strips_runtime_media_refs(tmp_path):
    bridge = load_bridge_module()
    configure_bridge(bridge)
    bridge.CONTEXT_PERSIST_ENABLED = True
    bridge.CONTEXT_CACHE_FILE = tmp_path / "recent_context.jsonl"

    bridge.remember_message(make_image_context_event(message_id=1201, url="https://cdn.example.test/private.png"))

    human = list(bridge.recent_messages_for_group(975805598))[0]
    assert human["media_refs"][0].url == "https://cdn.example.test/private.png"
    saved = bridge.CONTEXT_CACHE_FILE.read_text(encoding="utf-8")
    assert "media_refs" not in saved
    assert "https://cdn.example.test/private.png" not in saved
    assert "context.png" not in saved


def test_non_direct_image_message_adds_ocr_to_group_context_async(monkeypatch):
    bridge = load_bridge_module()
    configure_bridge(bridge)
    bridge.OCR_TRIGGER_MODE = "direct_and_context"

    async def fake_fetch(ref, **kwargs):
        return media_fetch.MediaFetchResult(
            ref=ref,
            status="ok",
            content=b"image",
            content_type="image/png",
            source_host="cdn.example.test",
            status_code=200,
        )

    monkeypatch.setattr(bridge.media_fetch, "fetch_onebot_image", fake_fetch)
    monkeypatch.setattr(bridge, "build_ocr_provider", lambda: vision.MockVisionProvider(text="普通群图OCR", description="群聊截图描述"))

    async def run():
        result = await bridge.onebot_event(FakeRequest(make_image_context_event()))
        await bridge.wait_ocr_context_tasks(975805598)
        return result

    result = asyncio.run(run())

    assert result["ignored"] == "not_at_me"
    recent = list(bridge.recent_messages_for_group(975805598))
    human = recent[0]
    assert "群里发图[图片]" in human["text"]
    assert "普通群图OCR" in human["text"]
    assert human["text_without_ocr"] == "群里发图[图片]"
    assert human["ocr_text_nonpersistent"] is True


def test_direct_only_does_not_ocr_non_direct_context_image(monkeypatch):
    bridge = load_bridge_module()
    configure_bridge(bridge)
    calls = []

    async def fake_fetch(ref, **kwargs):
        calls.append(ref)
        return media_fetch.MediaFetchResult(ref=ref, status="ok", content=b"image", content_type="image/png")

    monkeypatch.setattr(bridge.media_fetch, "fetch_onebot_image", fake_fetch)
    monkeypatch.setattr(bridge, "build_ocr_provider", lambda: vision.MockVisionProvider(text="不应出现"))

    async def run():
        result = await bridge.onebot_event(FakeRequest(make_image_context_event()))
        await bridge.wait_ocr_context_tasks(975805598)
        return result

    result = asyncio.run(run())

    assert result["ignored"] == "not_at_me"
    assert calls == []
    human = list(bridge.recent_messages_for_group(975805598))[0]
    assert human["text"] == "群里发图[图片]"
    assert "text_without_ocr" not in human


def test_unauthorized_group_image_does_not_fetch_ocr(monkeypatch):
    bridge = load_bridge_module()
    configure_bridge(bridge)
    bridge.OCR_TRIGGER_MODE = "direct_and_context"
    calls = []

    async def fake_fetch(ref, **kwargs):
        calls.append(ref)
        return media_fetch.MediaFetchResult(ref=ref, status="ok", content=b"image", content_type="image/png")

    monkeypatch.setattr(bridge.media_fetch, "fetch_onebot_image", fake_fetch)

    async def run():
        result = await bridge.onebot_event(FakeRequest(make_image_context_event(group_id=123456)))
        await bridge.wait_ocr_context_tasks(123456)
        return result

    result = asyncio.run(run())

    assert result["ignored"] == "other_group"
    assert calls == []
    assert list(bridge.recent_messages_for_group(123456)) == []


def test_context_ocr_persistence_strips_nonpersistent_text_after_async_update(monkeypatch, tmp_path):
    bridge = load_bridge_module()
    configure_bridge(bridge)
    bridge.OCR_TRIGGER_MODE = "direct_and_context"
    bridge.CONTEXT_PERSIST_ENABLED = True
    bridge.CONTEXT_CACHE_FILE = tmp_path / "recent_context.jsonl"

    async def fake_fetch(ref, **kwargs):
        return media_fetch.MediaFetchResult(ref=ref, status="ok", content=b"image", content_type="image/png")

    monkeypatch.setattr(bridge.media_fetch, "fetch_onebot_image", fake_fetch)
    monkeypatch.setattr(bridge, "build_ocr_provider", lambda: vision.MockVisionProvider(text="私密异步OCR", description="私密图描述"))

    async def run():
        await bridge.onebot_event(FakeRequest(make_image_context_event()))
        await bridge.wait_ocr_context_tasks(975805598)

    asyncio.run(run())

    human = list(bridge.recent_messages_for_group(975805598))[0]
    assert "私密异步OCR" in human["text"]
    saved = bridge.CONTEXT_CACHE_FILE.read_text(encoding="utf-8")
    assert "私密异步OCR" not in saved
    assert "私密图描述" not in saved
    assert "text_without_ocr" not in saved
    assert "ocr_text_nonpersistent" not in saved
    assert "群里发图[图片]" in saved


def test_context_ocr_cache_reuses_same_image_for_multiple_messages(monkeypatch):
    bridge = load_bridge_module()
    configure_bridge(bridge)
    bridge.OCR_TRIGGER_MODE = "direct_and_context"
    calls = []

    async def fake_fetch(ref, **kwargs):
        calls.append(ref)
        await asyncio.sleep(0)
        return media_fetch.MediaFetchResult(ref=ref, status="ok", content=b"image", content_type="image/png")

    monkeypatch.setattr(bridge.media_fetch, "fetch_onebot_image", fake_fetch)
    monkeypatch.setattr(bridge, "build_ocr_provider", lambda: vision.MockVisionProvider(text="缓存OCR", description="同一张图"))

    async def run():
        await bridge.onebot_event(FakeRequest(make_image_context_event(message_id=2001, url="https://cdn.example.test/same.png")))
        await bridge.onebot_event(FakeRequest(make_image_context_event(message_id=2002, url="https://cdn.example.test/same.png")))
        await bridge.wait_ocr_context_tasks(975805598)

    asyncio.run(run())

    assert len(calls) == 1
    recent = list(bridge.recent_messages_for_group(975805598))
    assert len(recent) == 2
    assert all("缓存OCR" in item["text"] for item in recent)


def test_context_ocr_failure_leaves_base_image_context(monkeypatch):
    bridge = load_bridge_module()
    configure_bridge(bridge)
    bridge.OCR_TRIGGER_MODE = "direct_and_context"

    async def fake_fetch(ref, **kwargs):
        return media_fetch.MediaFetchResult(ref=ref, status="error", error="timeout")

    monkeypatch.setattr(bridge.media_fetch, "fetch_onebot_image", fake_fetch)
    monkeypatch.setattr(bridge, "build_ocr_provider", lambda: vision.MockVisionProvider(text="不应出现"))

    async def run():
        await bridge.onebot_event(FakeRequest(make_image_context_event()))
        await bridge.wait_ocr_context_tasks(975805598)

    asyncio.run(run())

    human = list(bridge.recent_messages_for_group(975805598))[0]
    assert human["text"] == "群里发图[图片]"
    assert "text_without_ocr" not in human
