import importlib.util
import json
from pathlib import Path

from qq_hermes_bridge import self_learning

BRIDGE_PATH = Path(__file__).resolve().parents[1] / "bridge.py"


def load_bridge_module():
    spec = importlib.util.spec_from_file_location("bridge_under_test_self_learning", BRIDGE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def make_config(**overrides):
    values = {
        "enabled": True,
        "collect_enabled": True,
        "inject_enabled": True,
        "allowed_group_ids": {975805598},
        "min_message_chars": 2,
        "max_message_chars": 120,
        "max_samples_per_group": 20,
        "retention_days": 30,
        "max_prompt_chars": 300,
        "min_count_for_prompt": 1,
        "data_filename": "self_learning.json",
    }
    values.update(overrides)
    return self_learning.SelfLearningConfig(**values)


def configure_bridge(bridge, tmp_path, **config_overrides):
    bridge.TARGET_GROUP_ID = 975805598
    bridge.ALLOWED_GROUP_IDS = {975805598}
    bridge.GROUP_CONFIG_DIR = tmp_path
    bridge.CONTEXT_PERSIST_ENABLED = False
    bridge.OCR_MAX_IMAGES_PER_MESSAGE = 2
    bridge.SELF_LEARNING_CONFIG = make_config(**config_overrides)
    bridge._recent_messages_by_group.clear()
    bridge._recent_messages.clear()
    bridge._context_summaries_by_group.clear()
    bridge._processed_event_keys.clear()
    bridge._processed_event_key_set.clear()
    bridge._reply_queue_by_group.clear()
    bridge._reply_workers_by_group.clear()
    bridge._outbound_inflight_by_group.clear()


def make_group_event(text="笑死 这也太离谱了", *, group_id=975805598, user_id=111, message_id=2001):
    return {
        "post_type": "message",
        "message_type": "group",
        "group_id": group_id,
        "user_id": user_id,
        "self_id": 3975680980,
        "message_id": message_id,
        "sender": {"nickname": "群友"},
        "message": [{"type": "text", "data": {"text": text}}],
    }


def learning_file(tmp_path, group_id=975805598):
    return tmp_path / str(group_id) / "self_learning.json"


def sample_texts(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    return [sample["text"] for sample in data["samples"]]


def test_remember_message_collects_allowed_group_user_sample(tmp_path):
    bridge = load_bridge_module()
    configure_bridge(bridge, tmp_path)

    item = bridge.remember_message(make_group_event())

    assert item is not None
    path = learning_file(tmp_path)
    assert path.exists()
    assert sample_texts(path) == ["笑死 这也太离谱了"]


def test_remember_bot_reply_does_not_collect_self_learning_sample(tmp_path):
    bridge = load_bridge_module()
    configure_bridge(bridge, tmp_path)

    bridge.remember_bot_reply(975805598, "笑死 我是机器人回复")

    assert not learning_file(tmp_path).exists()
    recent = list(bridge.recent_messages_for_group(975805598))
    assert recent
    assert "机器人" in recent[0]["role"]


def test_build_prompt_includes_group_self_learning_context(monkeypatch, tmp_path):
    bridge = load_bridge_module()
    configure_bridge(bridge, tmp_path)
    bridge.remember_message(make_group_event("笑死 这也太离谱了", message_id=2001))
    bridge.remember_message(make_group_event("笑死 真的很离谱", message_id=2002))

    monkeypatch.setattr(bridge, "current_date_context", lambda: "今天")
    monkeypatch.setattr(bridge, "format_context_summaries", lambda group_id=None: "摘要")
    monkeypatch.setattr(bridge, "format_recent_context", lambda group_id=None: "最近")
    monkeypatch.setattr(bridge, "reply_context_from_event", lambda event: "引用")
    monkeypatch.setattr(bridge, "is_reply_to_me", lambda event: False)
    monkeypatch.setattr(bridge, "mentioned_people_labels", lambda event: [])
    monkeypatch.setattr(bridge, "group_people_file_for_prompt", lambda group_id: None)
    monkeypatch.setattr(bridge, "normal_chat_persona_bundle_for_prompt", lambda group_id: "人设")
    monkeypatch.setattr(bridge, "style_hint_for", lambda event: "短句")

    prompt = bridge.build_prompt(make_group_event("Esti 怎么看", user_id=222, message_id=2003), "Esti 怎么看")

    assert "群内用语与说话风格学习提示" in prompt
    assert "常见表达" in prompt
    assert "笑死" in prompt
    assert "离谱" in prompt


def test_remember_message_uses_text_without_ocr_for_learning(tmp_path):
    bridge = load_bridge_module()
    configure_bridge(bridge, tmp_path)

    bridge.remember_message(
        make_group_event("群里发图[图片]", message_id=2004),
        text_override="群里发图[图片]\n- 图片1：文字：私密OCR内容",
        text_without_ocr="群里发图[图片]",
        ocr_text_nonpersistent=True,
    )

    texts = sample_texts(learning_file(tmp_path))
    assert texts == ["群里发图[图片]"]
    assert "私密OCR内容" not in json.dumps(texts, ensure_ascii=False)
    human = list(bridge.recent_messages_for_group(975805598))[0]
    assert "私密OCR内容" in human["text"]
    assert human["text_without_ocr"] == "群里发图[图片]"


def test_self_learning_collect_error_does_not_break_remember_message(tmp_path):
    bridge = load_bridge_module()
    blocker = tmp_path / "groups-as-file"
    blocker.write_text("not a directory", encoding="utf-8")
    configure_bridge(bridge, blocker)

    item = bridge.remember_message(make_group_event("笑死 报错也不影响聊天", message_id=2005))

    assert item is not None
    assert item["text"] == "笑死 报错也不影响聊天"
    assert list(bridge.recent_messages_for_group(975805598))
