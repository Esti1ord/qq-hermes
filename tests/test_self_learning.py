import json
from pathlib import Path

from qq_hermes_bridge import self_learning


def make_config(**overrides):
    values = {
        "enabled": True,
        "collect_enabled": True,
        "inject_enabled": True,
        "allowed_group_ids": {123},
        "min_message_chars": 2,
        "max_message_chars": 80,
        "max_samples_per_group": 10,
        "retention_days": 30,
        "max_prompt_chars": 300,
        "min_count_for_prompt": 2,
        "data_filename": "self_learning.json",
    }
    values.update(overrides)
    return self_learning.SelfLearningConfig(**values)


def test_disabled_config_does_not_collect_or_create_file(tmp_path):
    config = make_config(enabled=False, collect_enabled=False, inject_enabled=False)

    collected = self_learning.collect_learning_sample(
        123,
        "笑死 这个太离谱了",
        group_config_dir=tmp_path,
        config=config,
        now=1000,
    )

    assert collected is False
    assert not (tmp_path / "123" / "self_learning.json").exists()
    assert self_learning.learning_context_for_prompt(
        123,
        target_group_id=123,
        group_config_dir=tmp_path,
        config=config,
        now=1000,
    ) == self_learning.DEFAULT_LEARNING_CONTEXT


def test_learning_sample_filter_rejects_unsafe_or_unwanted_messages():
    config = make_config(max_message_chars=10)

    assert self_learning.should_ignore_learning_sample("普通消息", config=config, group_id=999)
    assert self_learning.should_ignore_learning_sample("机器人消息", config=config, group_id=123, is_bot=True)
    assert self_learning.should_ignore_learning_sample("/context", config=config, group_id=123)
    assert self_learning.should_ignore_learning_sample("jrrp", config=config, group_id=123)
    assert self_learning.should_ignore_learning_sample("[CQ:image,file=a.png]", config=config, group_id=123)
    assert self_learning.should_ignore_learning_sample("https://example.test/a.png", config=config, group_id=123)
    assert self_learning.should_ignore_learning_sample("这句话超过最大长度限制", config=config, group_id=123)
    assert self_learning.should_ignore_learning_sample("api key 泄露", config=config, group_id=123)
    assert not self_learning.should_ignore_learning_sample("笑死", config=config, group_id=123)


def test_collects_group_samples_and_formats_low_weight_context(tmp_path):
    config = make_config(min_count_for_prompt=2)

    assert self_learning.collect_learning_sample(123, "笑死 这也太离谱了", group_config_dir=tmp_path, config=config, now=1000)
    assert self_learning.collect_learning_sample(123, "笑死 真的很离谱", group_config_dir=tmp_path, config=config, now=1001)
    assert self_learning.collect_learning_sample(123, "好耶 今天也离谱", group_config_dir=tmp_path, config=config, now=1002)

    context = self_learning.learning_context_for_prompt(
        123,
        target_group_id=999,
        group_config_dir=tmp_path,
        config=config,
        now=1003,
    )

    assert "低权重风格线索" in context
    assert "不是事实来源" in context
    assert "不是必须提到的话题" in context
    assert "常见表达" in context
    assert "笑死" in context
    assert "离谱" in context
    assert "风格信号" in context
    assert "self_learning.json" not in context


def test_retention_and_max_sample_count_are_enforced(tmp_path):
    config = make_config(max_samples_per_group=2, retention_days=1, min_count_for_prompt=1)

    self_learning.collect_learning_sample(123, "旧消息", group_config_dir=tmp_path, config=config, now=0)
    self_learning.collect_learning_sample(123, "新消息一", group_config_dir=tmp_path, config=config, now=100000)
    self_learning.collect_learning_sample(123, "新消息二", group_config_dir=tmp_path, config=config, now=100001)
    self_learning.collect_learning_sample(123, "新消息三", group_config_dir=tmp_path, config=config, now=100002)

    data = json.loads((tmp_path / "123" / "self_learning.json").read_text(encoding="utf-8"))
    texts = [sample["text"] for sample in data["samples"]]

    assert texts == ["新消息二", "新消息三"]
    assert "旧消息" not in texts


def test_prompt_context_uses_target_group_when_group_id_is_none(tmp_path):
    config = make_config(allowed_group_ids={456}, min_count_for_prompt=1)
    self_learning.collect_learning_sample(456, "本群口头禅", group_config_dir=tmp_path, config=config, now=1000)

    context = self_learning.learning_context_for_prompt(
        None,
        target_group_id=456,
        group_config_dir=tmp_path,
        config=config,
        now=1001,
    )

    assert "本群口头禅" in context


def test_collect_errors_are_swallowed_and_reported(tmp_path):
    blocker = tmp_path / "groups-as-file"
    blocker.write_text("not a directory", encoding="utf-8")
    config = make_config()
    errors = []

    collected = self_learning.collect_learning_sample(
        123,
        "笑死 报错也不影响聊天",
        group_config_dir=blocker,
        config=config,
        now=1000,
        on_error=errors.append,
    )

    assert collected is False
    assert errors
