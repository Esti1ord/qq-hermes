import os

from qq_hermes_bridge import config as bridge_config, config_utils


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


def test_env_first_returns_first_nonempty_value(monkeypatch):
    monkeypatch.setenv("SECOND", "two")
    monkeypatch.setenv("THIRD", "three")
    monkeypatch.setenv("FIRST", "   ")

    assert config_utils.env_first("FIRST", "SECOND", "THIRD", default="fallback") == "two"
    assert config_utils.env_first("MISSING", default="fallback") == "fallback"


def test_env_name_if_set_returns_the_first_nonempty_env_name(monkeypatch):
    monkeypatch.setenv("SECOND_NAME", "secret-two")
    monkeypatch.setenv("FIRST_NAME", "")

    assert config_utils.env_name_if_set("FIRST_NAME", "SECOND_NAME") == "SECOND_NAME"
    assert config_utils.env_name_if_set("MISSING_NAME") == ""


def test_parse_group_float_map_accepts_colon_and_equals_and_ignores_bad_items():
    assert config_utils.parse_group_float_map("1=2.5，2:3,bad,qq=x") == {1: 2.5, 2: 3.0}


def test_parse_group_str_map_accepts_colon_and_equals_and_ignores_bad_items():
    assert config_utils.parse_group_str_map("1=deepseek-v4-flash，2:openai-gpt,bad,qq=x,3=") == {1: "deepseek-v4-flash", 2: "openai-gpt"}


def test_load_config_includes_prometheus_flags(tmp_path, monkeypatch):
    monkeypatch.setenv("GROUP_IDS", "975805598")
    monkeypatch.delenv("PROMETHEUS_ENABLED", raising=False)
    monkeypatch.delenv("PROMETHEUS_INCLUDE_GROUP_ID_LABEL", raising=False)

    loaded = bridge_config.load_config(tmp_path)

    assert loaded.prometheus_enabled is True
    assert loaded.prometheus_include_group_id_label is False

    monkeypatch.setenv("PROMETHEUS_ENABLED", "false")
    monkeypatch.setenv("PROMETHEUS_INCLUDE_GROUP_ID_LABEL", "true")

    loaded = bridge_config.load_config(tmp_path)

    assert loaded.prometheus_enabled is False
    assert loaded.prometheus_include_group_id_label is True


def test_load_config_disables_punctuation_style_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("GROUP_IDS", "975805598")
    monkeypatch.delenv("PUNCTUATION_STYLE_ENABLED", raising=False)

    loaded = bridge_config.load_config(tmp_path)

    assert loaded.punctuation_style_enabled is False

    monkeypatch.setenv("PUNCTUATION_STYLE_ENABLED", "true")

    loaded = bridge_config.load_config(tmp_path)

    assert loaded.punctuation_style_enabled is True


def test_load_config_prefers_primary_and_vice_aliases_over_legacy_envs(tmp_path, monkeypatch):
    monkeypatch.setenv("GROUP_IDS", "975805598")
    monkeypatch.setenv("PRIMARY_CHAT_MODEL", "alias-primary-text")
    monkeypatch.setenv("PRIMARY_CHAT_MODEL_PROVIDER", "deepseek")
    monkeypatch.setenv("VICE_CHAT_MODEL", "alias-fallback-text")
    monkeypatch.setenv("VICE_CHAT_MODEL_PROVIDER", "openai-gpt")
    monkeypatch.setenv("HERMES_MODEL", "legacy-primary-text")
    monkeypatch.setenv("HERMES_PROVIDER", "legacy-primary-provider")
    monkeypatch.setenv("HERMES_FALLBACK_MODEL", "legacy-fallback-text")
    monkeypatch.setenv("HERMES_FALLBACK_PROVIDER", "legacy-fallback-provider")
    monkeypatch.setenv("PRIMARY_OCR_MODEL_PROVIDER", "custom")
    monkeypatch.setenv("PRIMARY_OCR_MODEL", "alias-primary-vision")
    monkeypatch.setenv("PRIMARY_OCR_MODEL_URL", "https://api.example.test/v1")
    monkeypatch.setenv("PRIMARY_OCR_MODEL_API", "dummy-primary-value")
    monkeypatch.setenv("OCR_PROVIDER", "legacy-ocr-provider")
    monkeypatch.setenv("OCR_MODEL", "legacy-ocr-model")
    monkeypatch.setenv("OCR_PROVIDER_BASE_URL", "https://legacy.example.test/v1")
    monkeypatch.setenv("OCR_API_KEY_ENV", "LEGACY_VISION_KEY")
    monkeypatch.setenv("VICE_OCR_MODEL_PROVIDER", "SiliconFlow")
    monkeypatch.setenv("VICE_OCR_MODEL", "alias-fallback-vision")
    monkeypatch.setenv("VICE_OCR_MODEL_URL", "https://fallback.example.test/v1")
    monkeypatch.setenv("VICE_OCR_MODEL_API", "dummy-fallback-value")
    monkeypatch.setenv("OCR_FALLBACK_PROVIDER", "legacy-fallback-ocr-provider")
    monkeypatch.setenv("OCR_FALLBACK_MODEL", "legacy-fallback-ocr-model")
    monkeypatch.setenv("OCR_FALLBACK_PROVIDER_BASE_URL", "https://legacy-fallback.example.test/v1")
    monkeypatch.setenv("OCR_FALLBACK_API_KEY_ENV", "LEGACY_FALLBACK_VISION_KEY")

    loaded = bridge_config.load_config(tmp_path)

    assert loaded.hermes_model == "alias-primary-text"
    assert loaded.hermes_provider == "deepseek"
    assert loaded.hermes_fallback_model == "alias-fallback-text"
    assert loaded.hermes_fallback_provider == "openai-gpt"
    assert loaded.ocr_provider == "custom"
    assert loaded.ocr_model == "alias-primary-vision"
    assert loaded.ocr_provider_base_url == "https://api.example.test/v1"
    assert loaded.ocr_api_key_env == "PRIMARY_OCR_MODEL_API"
    assert loaded.ocr_fallback_provider == "SiliconFlow"
    assert loaded.ocr_fallback_model == "alias-fallback-vision"
    assert loaded.ocr_fallback_provider_base_url == "https://fallback.example.test/v1"
    assert loaded.ocr_fallback_api_key_env == "VICE_OCR_MODEL_API"


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


def test_load_config_includes_text_and_ocr_fallback_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("GROUP_IDS", "975805598")
    for name in (
        "HERMES_FALLBACK_ENABLED",
        "VICE_CHAT_MODEL",
        "VICE_CHAT_MODEL_PROVIDER",
        "HERMES_FALLBACK_MODEL",
        "HERMES_FALLBACK_PROVIDER",
        "OCR_FALLBACK_ENABLED",
        "VICE_OCR_MODEL_PROVIDER",
        "VICE_OCR_MODEL",
        "VICE_OCR_MODEL_BASE_URL",
        "VICE_OCR_MODEL_URL",
        "VICE_OCR_MODEL_API_KEY_ENV",
        "VICE_OCR_MODEL_API_KEY",
        "VICE_OCR_MODEL_API",
        "OCR_FALLBACK_PROVIDER",
        "OCR_FALLBACK_MODEL",
        "OCR_FALLBACK_PROVIDER_BASE_URL",
        "OCR_FALLBACK_API_KEY_ENV",
    ):
        monkeypatch.delenv(name, raising=False)

    loaded = bridge_config.load_config(tmp_path)

    assert loaded.hermes_fallback_enabled is True
    assert loaded.hermes_fallback_model == "deepseekv4flash"
    assert loaded.hermes_fallback_provider == "官方"
    assert loaded.ocr_fallback_enabled is True
    assert loaded.ocr_fallback_provider == "model"
    assert loaded.ocr_fallback_model == "gpt-5.4"
    assert loaded.ocr_fallback_provider_base_url == ""
    assert loaded.ocr_fallback_api_key_env == ""

    monkeypatch.setenv("HERMES_FALLBACK_ENABLED", "false")
    monkeypatch.setenv("HERMES_FALLBACK_MODEL", "other-text")
    monkeypatch.setenv("HERMES_FALLBACK_PROVIDER", "other-provider")
    monkeypatch.setenv("OCR_FALLBACK_ENABLED", "false")
    monkeypatch.setenv("OCR_FALLBACK_PROVIDER", "openai_compatible")
    monkeypatch.setenv("OCR_FALLBACK_MODEL", "other-vision")
    monkeypatch.setenv("OCR_FALLBACK_PROVIDER_BASE_URL", "https://fallback.example.test/v1")
    monkeypatch.setenv("OCR_FALLBACK_API_KEY_ENV", "VISION_FALLBACK_API_KEY")

    loaded = bridge_config.load_config(tmp_path)

    assert loaded.hermes_fallback_enabled is False
    assert loaded.hermes_fallback_model == "other-text"
    assert loaded.hermes_fallback_provider == "other-provider"
    assert loaded.ocr_fallback_enabled is False
    assert loaded.ocr_fallback_provider == "openai_compatible"
    assert loaded.ocr_fallback_model == "other-vision"
    assert loaded.ocr_fallback_provider_base_url == "https://fallback.example.test/v1"
    assert loaded.ocr_fallback_api_key_env == "VISION_FALLBACK_API_KEY"
