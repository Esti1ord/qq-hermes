import os
from pathlib import Path

from qq_hermes_bridge import config_utils


def test_parse_bool_accepts_true_values_and_false_values():
    assert config_utils.parse_bool("true") is True
    assert config_utils.parse_bool("1") is True
    assert config_utils.parse_bool("yes") is True
    assert config_utils.parse_bool("false") is False
    assert config_utils.parse_bool("0") is False
    assert config_utils.parse_bool("no") is False


def test_env_list_splits_ascii_and_chinese_commas(monkeypatch):
    monkeypatch.setenv("EXAMPLE_LIST", "a,b， c ,, d")

    assert config_utils.env_list("EXAMPLE_LIST", "") == ["a", "b", "c", "d"]


def test_parse_group_float_map_accepts_colon_and_equals_and_ignores_bad_items():
    assert config_utils.parse_group_float_map("1=2.5，2:3,bad,qq=x") == {1: 2.5, 2: 3.0}


def test_parse_group_str_map_accepts_colon_and_equals_and_ignores_bad_items():
    assert config_utils.parse_group_str_map("1=deepseek-v4-flash，2:openai-gpt,bad,qq=x,3=") == {1: "deepseek-v4-flash", 2: "openai-gpt"}


def test_load_dotenv_sets_missing_values_without_overwriting_existing(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("A=one\nB='two'\nC=\"three\"\n# ignored\nBAD\n", encoding="utf-8")
    monkeypatch.setenv("A", "existing")
    monkeypatch.delenv("B", raising=False)
    monkeypatch.delenv("C", raising=False)

    config_utils.load_dotenv(env_file)

    assert os.environ["A"] == "existing"
    assert os.environ["B"] == "two"
    assert os.environ["C"] == "three"
