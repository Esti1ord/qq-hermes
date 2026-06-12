"""Typed configuration loader for the QQ/Hermes bridge.

This module mirrors the historical configuration globals from ``bridge.py`` while
providing a flat dataclass that later refactors can pass around explicitly.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from qq_hermes_bridge import config_utils, content_analysis_log, runtime_stats, self_learning, vision

STYLE_HINTS = [
    "像群友随口接话，短一点，不要端着。",
    "可以轻微吐槽，但别攻击人，也别拱火。",
    "先给结论，再补一句理由；别写成长文。",
    "不要把短回复拆成多段或空行，QQ 闲聊尽量一段发完。",
    "语气自然一点，少用 AI/客服腔。",
]

REPLY_TEMPLATES = {
    "empty_reply": [
        "我看到了 不过暂时没想好怎么回",
        "先略过 我还没组织好",
        "这条我先不硬接",
        "我有点卡住了 等会再说",
    ],
    "hermes_error": [
        "我这边卡了一下 等会再试",
        "刚才没跑顺 稍后再问我一次",
        "这下没处理好 先缓一下",
        "我这边断了一下 等会再来",
    ],
}


@dataclass
class Config:
    base_dir: Path
    log_dir: Path
    log_file: Path
    target_group_id: int
    group_config_dir: Path
    group_list_file: Path
    allowed_group_ids: set[int]
    default_group_config_dir: Path
    base_persona_file: Path
    default_persona_file: Path
    default_people_file: Path
    bot_qq: str
    onebot_http_url: str
    onebot_access_token: str
    bridge_inbound_token: str
    hermes_bin: str
    hermes_model: str
    hermes_provider: str
    hermes_provider_base_url: str
    hermes_api_key_env: str
    hermes_fallback_enabled: bool
    hermes_fallback_model: str
    hermes_fallback_provider: str
    hermes_fallback_provider_base_url: str
    hermes_fallback_api_key_env: str
    hermes_model_by_group: dict[int, str]
    hermes_provider_by_group: dict[int, str]
    hermes_group_sessions_enabled: bool
    hermes_group_session_prefix: str
    hermes_session_autocompact_enabled: bool
    hermes_session_max_messages: int
    hermes_session_max_body_chars: int
    hermes_session_compact_summary_chars: int
    reply_prefix: str
    max_prompt_chars: int
    hermes_timeout: int
    min_seconds_between_replies: float
    context_max_messages: int
    context_summary_max: int
    context_summarize_batch: int
    context_summary_max_chars: int
    context_summarize_enabled: bool
    context_max_chars_per_message: int
    persona_file: Path
    people_file: Path
    related_profile_max_matches: int
    related_profile_min_keyword_len: int
    knowledge_max_chars: int
    user_cooldown_seconds: float
    max_pending_replies: int
    max_pending_direct_replies: int
    max_reply_chars: int
    punctuation_style_enabled: bool
    skip_unclear_mentions: bool
    context_persist_enabled: bool
    context_cache_file: Path
    ocr_enabled: bool
    ocr_trigger_mode: str
    ocr_provider: str
    ocr_external_provider_allowed: bool
    ocr_max_images_per_message: int
    ocr_max_bytes_per_image: int
    ocr_allowed_content_types: set[str]
    ocr_download_timeout: float
    ocr_provider_timeout: float
    ocr_max_result_chars: int
    ocr_include_in_prompt: bool
    ocr_include_in_context: bool
    ocr_persist_text_in_context: bool
    ocr_log_text: bool
    ocr_log_image_urls: bool
    ocr_model: str
    ocr_provider_base_url: str
    ocr_api_key_env: str
    ocr_fallback_enabled: bool
    ocr_fallback_provider: str
    ocr_fallback_model: str
    ocr_fallback_provider_base_url: str
    ocr_fallback_api_key_env: str
    ocr_image_prompt: str
    ocr_context_group_ids: set[int]
    ocr_max_concurrent_tasks: int
    ocr_cache_ttl_seconds: float
    ocr_cache_max_entries: int
    self_learning_enabled: bool
    self_learning_collect_enabled: bool
    self_learning_inject_enabled: bool
    self_learning_allowed_group_ids: set[int]
    self_learning_min_message_chars: int
    self_learning_max_message_chars: int
    self_learning_max_samples_per_group: int
    self_learning_retention_days: int
    self_learning_max_prompt_chars: int
    self_learning_min_count_for_prompt: int
    self_learning_data_filename: str
    self_learning_config: self_learning.SelfLearningConfig
    content_analysis_log_enabled: bool
    content_analysis_log_file: Path
    content_analysis_allowed_group_ids: set[int]
    content_analysis_context_messages: int
    content_analysis_max_text_chars: int
    content_analysis_max_reply_chars: int
    content_analysis_include_summaries: bool
    runtime_stats_enabled: bool
    runtime_stats_file: Path
    runtime_stats_user_hash_salt: str
    runtime_stats_summary_interval_seconds: float
    prometheus_enabled: bool
    prometheus_include_group_id_label: bool
    perf_obs_enabled: bool
    perf_obs_detail_level: str
    perf_obs_sample_rate: float
    perf_obs_slow_reply_ms: int
    perf_obs_slow_hermes_ms: int
    perf_obs_slow_send_ms: int
    perf_obs_slow_ocr_ms: int
    perf_obs_interaction_ttl_seconds: float
    perf_obs_max_interactions: int
    jrrp_state_file: Path
    jrrp_results_file: Path
    proactive_enabled: bool
    proactive_trigger_threshold: float
    proactive_trigger_thresholds_by_group: dict[int, float]
    proactive_group_cooldown_seconds: float
    proactive_decay_per_minute: float
    proactive_daily_limit_per_group: int
    proactive_rate_limit_window_seconds: float
    proactive_rate_limit_max_replies: int
    proactive_context_focus_messages: int
    proactive_context_memory_messages: int
    proactive_burst_window_seconds: float
    proactive_burst_message_threshold: int
    proactive_burst_user_threshold: int
    proactive_name_triggers: list[str]
    proactive_topic_keywords: list[str]
    proactive_light_keywords: list[str]
    proactive_score_name_trigger: float
    proactive_score_topic_keyword: float
    proactive_score_light_keyword: float
    proactive_score_question: float
    proactive_score_open_question: float
    proactive_score_burst: float
    proactive_score_multi_user: float
    proactive_sensitive_cooldown_seconds: float
    proactive_night_start: str
    proactive_night_end: str
    proactive_night_score_multiplier: float
    proactive_sensitive_keywords: list[str]
    style_hints: list[str] = field(default_factory=lambda: list(STYLE_HINTS))
    reply_templates: dict[str, list[str]] = field(default_factory=lambda: {key: list(values) for key, values in REPLY_TEMPLATES.items()})


def load_dotenv(path: Path) -> None:
    config_utils.load_dotenv(path)


def env_list(name: str, default: str) -> list[str]:
    return config_utils.env_list(name, default)


def parse_group_float_map(raw: str) -> dict[int, float]:
    return config_utils.parse_group_float_map(raw)


def load_group_ids(target_group_id: int | None = None, group_list_file: Path | None = None) -> set[int]:
    resolved_target_group_id = int(os.getenv("TARGET_GROUP_ID", "975805598")) if target_group_id is None else int(target_group_id)
    if group_list_file is None:
        default_base_dir = Path(__file__).resolve().parent.parent
        group_config_dir = Path(os.getenv("GROUP_CONFIG_DIR", str(default_base_dir / "groups")))
        resolved_group_list_file = Path(os.getenv("GROUP_LIST_FILE", str(group_config_dir / "groups.txt")))
    else:
        resolved_group_list_file = Path(group_list_file)

    ids: set[int] = set()
    raw = os.getenv("GROUP_IDS", os.getenv("ALLOWED_GROUP_IDS", ""))
    for item in raw.split(","):
        item = item.strip()
        if item:
            ids.add(int(item))
    if resolved_group_list_file.exists():
        for raw_line in resolved_group_list_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.split("#", 1)[0].strip()
            if line:
                ids.add(int(line))
    ids.add(resolved_target_group_id)
    return ids


def _copy_reply_templates() -> dict[str, list[str]]:
    return {key: list(values) for key, values in REPLY_TEMPLATES.items()}


def _bool_env(name: str, default: str) -> bool:
    return os.getenv(name, default).lower() in {"1", "true", "yes"}


def _env_first(*names: str, default: str = "") -> str:
    return config_utils.env_first(*names, default=default)


def _api_key_env_name(*, explicit_names: tuple[str, ...], raw_names: tuple[str, ...]) -> str:
    raw_name = config_utils.env_name_if_set(*raw_names)
    if raw_name:
        return raw_name
    return _env_first(*explicit_names)


def load_config(base_dir: Path | None = None) -> Config:
    resolved_base_dir = Path(base_dir).resolve() if base_dir is not None else Path(__file__).resolve().parent.parent
    log_dir = resolved_base_dir / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "bridge.log"

    load_dotenv(resolved_base_dir / ".env")

    target_group_id = int(os.getenv("TARGET_GROUP_ID", "975805598"))
    group_config_dir = Path(os.getenv("GROUP_CONFIG_DIR", str(resolved_base_dir / "groups")))
    group_list_file = Path(os.getenv("GROUP_LIST_FILE", str(group_config_dir / "groups.txt")))
    allowed_group_ids = load_group_ids(target_group_id, group_list_file)
    default_group_config_dir = group_config_dir
    base_persona_file = Path(os.getenv("BASE_PERSONA_FILE", str(resolved_base_dir / "base_persona.md")))
    default_persona_file = group_config_dir / str(target_group_id) / "persona.md"
    default_people_file = group_config_dir / str(target_group_id) / "people.md"
    bot_qq = os.getenv("BOT_QQ", "").strip()
    onebot_http_url = os.getenv("ONEBOT_HTTP_URL", "http://127.0.0.1:3000").rstrip("/")
    onebot_access_token = os.getenv("ONEBOT_ACCESS_TOKEN", "").strip()
    bridge_inbound_token = os.getenv("BRIDGE_INBOUND_TOKEN", "").strip()
    hermes_bin = os.getenv("HERMES_BIN", "/home/roxy/.local/bin/hermes")
    hermes_model = _env_first("PRIMARY_CHAT_MODEL", "HERMES_MODEL", default=config_utils.DEFAULT_PRIMARY_CHAT_MODEL)
    hermes_provider = _env_first("PRIMARY_CHAT_MODEL_PROVIDER", "HERMES_PROVIDER", default=config_utils.DEFAULT_PRIMARY_CHAT_PROVIDER)
    hermes_provider_base_url = _env_first("PRIMARY_CHAT_MODEL_URL", "PRIMARY_CHAT_MODEL_BASE_URL", "HERMES_PROVIDER_BASE_URL")
    hermes_api_key_env = _api_key_env_name(
        explicit_names=("PRIMARY_CHAT_MODEL_API_KEY_ENV", "HERMES_API_KEY_ENV"),
        raw_names=("PRIMARY_CHAT_MODEL_API_KEY", "PRIMARY_CHAT_MODEL_API", "HERMES_API_KEY"),
    )
    hermes_fallback_enabled = config_utils.parse_bool(os.getenv("HERMES_FALLBACK_ENABLED", "true"))
    hermes_fallback_model = _env_first("VICE_CHAT_MODEL", "HERMES_FALLBACK_MODEL", default=config_utils.DEFAULT_FALLBACK_CHAT_MODEL)
    hermes_fallback_provider = _env_first("VICE_CHAT_MODEL_PROVIDER", "HERMES_FALLBACK_PROVIDER", default=config_utils.DEFAULT_FALLBACK_CHAT_PROVIDER)
    hermes_fallback_provider_base_url = _env_first("VICE_CHAT_MODEL_URL", "VICE_CHAT_MODEL_BASE_URL", "HERMES_FALLBACK_PROVIDER_BASE_URL")
    hermes_fallback_api_key_env = _api_key_env_name(
        explicit_names=("VICE_CHAT_MODEL_API_KEY_ENV", "HERMES_FALLBACK_API_KEY_ENV"),
        raw_names=("VICE_CHAT_MODEL_API_KEY", "VICE_CHAT_MODEL_API", "HERMES_FALLBACK_API_KEY"),
    )
    hermes_model_by_group = config_utils.parse_group_str_map(os.getenv("HERMES_MODEL_BY_GROUP", ""))
    hermes_provider_by_group = config_utils.parse_group_str_map(os.getenv("HERMES_PROVIDER_BY_GROUP", ""))
    hermes_group_sessions_enabled = _bool_env("HERMES_GROUP_SESSIONS_ENABLED", "true")
    hermes_group_session_prefix = os.getenv("HERMES_GROUP_SESSION_PREFIX", "qq-group").strip() or "qq-group"
    hermes_session_autocompact_enabled = _bool_env("HERMES_SESSION_AUTOCOMPACT_ENABLED", "true")
    hermes_session_max_messages = int(os.getenv("HERMES_SESSION_MAX_MESSAGES", "80"))
    hermes_session_max_body_chars = int(os.getenv("HERMES_SESSION_MAX_BODY_CHARS", "180000"))
    hermes_session_compact_summary_chars = int(os.getenv("HERMES_SESSION_COMPACT_SUMMARY_CHARS", "1200"))
    reply_prefix = os.getenv("REPLY_PREFIX", "").strip()
    max_prompt_chars = int(os.getenv("MAX_PROMPT_CHARS", "3500"))
    hermes_timeout = int(os.getenv("HERMES_TIMEOUT", "180"))
    min_seconds_between_replies = float(os.getenv("MIN_SECONDS_BETWEEN_REPLIES", "2"))
    context_max_messages = int(os.getenv("CONTEXT_MAX_MESSAGES", "20"))
    context_summary_max = int(os.getenv("CONTEXT_SUMMARY_MAX", "30"))
    context_summarize_batch = int(os.getenv("CONTEXT_SUMMARIZE_BATCH", "5"))
    context_summary_max_chars = int(os.getenv("CONTEXT_SUMMARY_MAX_CHARS", "180"))
    context_summarize_enabled = _bool_env("CONTEXT_SUMMARIZE_ENABLED", "true")
    context_max_chars_per_message = int(os.getenv("CONTEXT_MAX_CHARS_PER_MESSAGE", "300"))
    persona_file = Path(os.getenv("PERSONA_FILE", str(default_persona_file)))
    people_file = Path(os.getenv("PEOPLE_FILE", str(default_people_file)))
    related_profile_max_matches = int(os.getenv("RELATED_PROFILE_MAX_MATCHES", "3"))
    related_profile_min_keyword_len = int(os.getenv("RELATED_PROFILE_MIN_KEYWORD_LEN", "2"))
    knowledge_max_chars = int(os.getenv("KNOWLEDGE_MAX_CHARS", "3500"))
    user_cooldown_seconds = float(os.getenv("USER_COOLDOWN_SECONDS", "20"))
    max_pending_replies = int(os.getenv("MAX_PENDING_REPLIES", "3"))
    max_pending_direct_replies = int(os.getenv("MAX_PENDING_DIRECT_REPLIES", str(max(20, max_pending_replies))))
    max_reply_chars = int(os.getenv("MAX_REPLY_CHARS", "450"))
    punctuation_style_enabled = _bool_env("PUNCTUATION_STYLE_ENABLED", "false")
    skip_unclear_mentions = os.getenv("SKIP_UNCLEAR_MENTIONS", "true").lower() not in {"0", "false", "no"}
    context_persist_enabled = _bool_env("CONTEXT_PERSIST_ENABLED", "false")
    context_cache_file = Path(os.getenv("CONTEXT_CACHE_FILE", str(resolved_base_dir / "logs" / "recent_context.jsonl")))
    ocr_enabled = config_utils.parse_bool(os.getenv("OCR_ENABLED", "false"))
    ocr_trigger_mode = os.getenv("OCR_TRIGGER_MODE", "direct_only").strip() or "direct_only"
    ocr_provider = _env_first("PRIMARY_OCR_MODEL_PROVIDER", "IMAGE_MODEL_PROVIDER", "OCR_PROVIDER", default=config_utils.DEFAULT_PRIMARY_OCR_PROVIDER)
    ocr_external_provider_allowed = config_utils.parse_bool(os.getenv("OCR_EXTERNAL_PROVIDER_ALLOWED", "false"))
    ocr_max_images_per_message = int(os.getenv("OCR_MAX_IMAGES_PER_MESSAGE", "2"))
    ocr_max_bytes_per_image = int(os.getenv("OCR_MAX_BYTES_PER_IMAGE", "6291456"))
    ocr_allowed_content_types = set(config_utils.env_list("OCR_ALLOWED_CONTENT_TYPES", "image/jpeg,image/png,image/webp,image/gif"))
    ocr_download_timeout = float(os.getenv("OCR_DOWNLOAD_TIMEOUT", "8"))
    ocr_provider_timeout = float(os.getenv("OCR_PROVIDER_TIMEOUT", "30"))
    ocr_max_result_chars = int(os.getenv("OCR_MAX_RESULT_CHARS", "800"))
    ocr_include_in_prompt = config_utils.parse_bool(os.getenv("OCR_INCLUDE_IN_PROMPT", "true"))
    ocr_include_in_context = config_utils.parse_bool(os.getenv("OCR_INCLUDE_IN_CONTEXT", "true"))
    ocr_persist_text_in_context = config_utils.parse_bool(os.getenv("OCR_PERSIST_TEXT_IN_CONTEXT", "false"))
    ocr_log_text = config_utils.parse_bool(os.getenv("OCR_LOG_TEXT", "false"))
    ocr_log_image_urls = config_utils.parse_bool(os.getenv("OCR_LOG_IMAGE_URLS", "false"))
    ocr_model = _env_first("PRIMARY_OCR_MODEL", "IMAGE_MODEL", "OCR_MODEL", default=config_utils.DEFAULT_PRIMARY_OCR_MODEL)
    ocr_provider_base_url = _env_first("PRIMARY_OCR_MODEL_URL", "PRIMARY_OCR_MODEL_BASE_URL", "IMAGE_MODEL_URL", "IMAGE_MODEL_BASE_URL", "OCR_PROVIDER_BASE_URL")
    ocr_api_key_env = _api_key_env_name(
        explicit_names=("PRIMARY_OCR_MODEL_API_KEY_ENV", "IMAGE_MODEL_API_KEY_ENV", "OCR_API_KEY_ENV"),
        raw_names=("PRIMARY_OCR_MODEL_API_KEY", "PRIMARY_OCR_MODEL_API", "IMAGE_MODEL_API_KEY", "IMAGE_MODEL_API", "OCR_API_KEY"),
    )
    ocr_fallback_enabled = config_utils.parse_bool(os.getenv("OCR_FALLBACK_ENABLED", "true"))
    ocr_fallback_provider = _env_first("VICE_OCR_MODEL_PROVIDER", "OCR_FALLBACK_PROVIDER", default=config_utils.DEFAULT_FALLBACK_OCR_PROVIDER)
    ocr_fallback_model = _env_first("VICE_OCR_MODEL", "OCR_FALLBACK_MODEL", default=config_utils.DEFAULT_FALLBACK_OCR_MODEL)
    ocr_fallback_provider_base_url = _env_first("VICE_OCR_MODEL_URL", "VICE_OCR_MODEL_BASE_URL", "OCR_FALLBACK_PROVIDER_BASE_URL")
    ocr_fallback_api_key_env = _api_key_env_name(
        explicit_names=("VICE_OCR_MODEL_API_KEY_ENV", "OCR_FALLBACK_API_KEY_ENV"),
        raw_names=("VICE_OCR_MODEL_API_KEY", "VICE_OCR_MODEL_API", "OCR_FALLBACK_API_KEY"),
    )
    ocr_image_prompt = os.getenv("OCR_IMAGE_PROMPT", vision.DEFAULT_IMAGE_PROMPT).strip() or vision.DEFAULT_IMAGE_PROMPT
    ocr_context_group_ids = content_analysis_log.parse_group_ids(os.getenv("OCR_CONTEXT_GROUP_IDS", ""))
    ocr_max_concurrent_tasks = max(1, int(os.getenv("OCR_MAX_CONCURRENT_TASKS", "2")))
    ocr_cache_ttl_seconds = max(0.0, float(os.getenv("OCR_CACHE_TTL_SECONDS", "3600")))
    ocr_cache_max_entries = max(0, int(os.getenv("OCR_CACHE_MAX_ENTRIES", "512")))
    self_learning_enabled = config_utils.parse_bool(os.getenv("SELF_LEARNING_ENABLED", "false"))
    self_learning_collect_enabled = config_utils.parse_bool(os.getenv("SELF_LEARNING_COLLECT_ENABLED", "true" if self_learning_enabled else "false"))
    self_learning_inject_enabled = config_utils.parse_bool(os.getenv("SELF_LEARNING_INJECT_ENABLED", "true" if self_learning_enabled else "false"))
    self_learning_allowed_group_ids = content_analysis_log.parse_group_ids(os.getenv("SELF_LEARNING_ALLOWED_GROUP_IDS", ""))
    self_learning_min_message_chars = int(os.getenv("SELF_LEARNING_MIN_MESSAGE_CHARS", "2"))
    self_learning_max_message_chars = int(os.getenv("SELF_LEARNING_MAX_MESSAGE_CHARS", "300"))
    self_learning_max_samples_per_group = int(os.getenv("SELF_LEARNING_MAX_SAMPLES_PER_GROUP", "500"))
    self_learning_retention_days = int(os.getenv("SELF_LEARNING_RETENTION_DAYS", "30"))
    self_learning_max_prompt_chars = int(os.getenv("SELF_LEARNING_MAX_PROMPT_CHARS", "500"))
    self_learning_min_count_for_prompt = int(os.getenv("SELF_LEARNING_MIN_COUNT_FOR_PROMPT", "3"))
    self_learning_data_filename = os.getenv("SELF_LEARNING_DATA_FILENAME", "self_learning.json").strip() or "self_learning.json"
    self_learning_config = self_learning.SelfLearningConfig(
        enabled=self_learning_enabled,
        collect_enabled=self_learning_collect_enabled,
        inject_enabled=self_learning_inject_enabled,
        allowed_group_ids=self_learning_allowed_group_ids,
        min_message_chars=self_learning_min_message_chars,
        max_message_chars=self_learning_max_message_chars,
        max_samples_per_group=self_learning_max_samples_per_group,
        retention_days=self_learning_retention_days,
        max_prompt_chars=self_learning_max_prompt_chars,
        min_count_for_prompt=self_learning_min_count_for_prompt,
        data_filename=self_learning_data_filename,
    )
    content_analysis_log_enabled = content_analysis_log.enabled_from_env(os.getenv("CONTENT_ANALYSIS_LOG_ENABLED", "false"))
    content_analysis_log_file = Path(os.getenv("CONTENT_ANALYSIS_LOG_FILE", str(log_dir / "content_analysis.jsonl")))
    content_analysis_allowed_group_ids = content_analysis_log.parse_group_ids(os.getenv("CONTENT_ANALYSIS_ALLOWED_GROUP_IDS", ""))
    content_analysis_context_messages = int(os.getenv("CONTENT_ANALYSIS_CONTEXT_MESSAGES", "8"))
    content_analysis_max_text_chars = int(os.getenv("CONTENT_ANALYSIS_MAX_TEXT_CHARS", "1000"))
    content_analysis_max_reply_chars = int(os.getenv("CONTENT_ANALYSIS_MAX_REPLY_CHARS", "1000"))
    content_analysis_include_summaries = _bool_env("CONTENT_ANALYSIS_INCLUDE_SUMMARIES", "true")
    runtime_stats_enabled = runtime_stats.enabled_from_env(os.getenv("RUNTIME_STATS_ENABLED", "true"))
    runtime_stats_file = Path(os.getenv("RUNTIME_STATS_FILE", str(log_dir / "runtime_stats.jsonl")))
    runtime_stats_user_hash_salt = os.getenv("RUNTIME_STATS_USER_HASH_SALT", bot_qq or "qq-hermes-local")
    runtime_stats_summary_interval_seconds = float(os.getenv("RUNTIME_STATS_SUMMARY_INTERVAL_SECONDS", "300"))
    prometheus_enabled = config_utils.parse_bool(os.getenv("PROMETHEUS_ENABLED", "true"))
    prometheus_include_group_id_label = config_utils.parse_bool(os.getenv("PROMETHEUS_INCLUDE_GROUP_ID_LABEL", "false"))
    perf_obs_enabled = config_utils.parse_bool(os.getenv("PERF_OBS_ENABLED", "true"))
    perf_obs_detail_level = runtime_stats.normalize_label(os.getenv("PERF_OBS_DETAIL_LEVEL", "standard"), default="standard")
    perf_obs_sample_rate = max(0.0, min(1.0, float(os.getenv("PERF_OBS_SAMPLE_RATE", "1.0"))))
    perf_obs_slow_reply_ms = int(os.getenv("PERF_OBS_SLOW_REPLY_MS", "15000"))
    perf_obs_slow_hermes_ms = int(os.getenv("PERF_OBS_SLOW_HERMES_MS", "10000"))
    perf_obs_slow_send_ms = int(os.getenv("PERF_OBS_SLOW_SEND_MS", "3000"))
    perf_obs_slow_ocr_ms = int(os.getenv("PERF_OBS_SLOW_OCR_MS", "8000"))
    perf_obs_interaction_ttl_seconds = float(os.getenv("PERF_OBS_INTERACTION_TTL_SECONDS", "3600"))
    perf_obs_max_interactions = int(os.getenv("PERF_OBS_MAX_INTERACTIONS", "2000"))
    jrrp_state_file = Path(os.getenv("JRRP_STATE_FILE", str(log_dir / "jrrp_state.json")))
    jrrp_results_file = Path(os.getenv("JRRP_RESULTS_FILE", str(resolved_base_dir / "jrrp_results.json")))
    proactive_enabled = _bool_env("PROACTIVE_ENABLED", "true")
    proactive_trigger_threshold = float(os.getenv("PROACTIVE_TRIGGER_THRESHOLD", "16"))
    proactive_trigger_thresholds_by_group = parse_group_float_map(os.getenv("PROACTIVE_TRIGGER_THRESHOLDS_BY_GROUP", ""))
    proactive_group_cooldown_seconds = float(os.getenv("PROACTIVE_GROUP_COOLDOWN_SECONDS", "900"))
    proactive_decay_per_minute = float(os.getenv("PROACTIVE_DECAY_PER_MINUTE", "1"))
    proactive_daily_limit_per_group = int(os.getenv("PROACTIVE_DAILY_LIMIT_PER_GROUP", "8"))
    proactive_rate_limit_window_seconds = float(os.getenv("PROACTIVE_RATE_LIMIT_WINDOW_SECONDS", "60"))
    proactive_rate_limit_max_replies = int(os.getenv("PROACTIVE_RATE_LIMIT_MAX_REPLIES", "6"))
    proactive_context_focus_messages = int(os.getenv("PROACTIVE_CONTEXT_FOCUS_MESSAGES", "3"))
    proactive_context_memory_messages = int(os.getenv("PROACTIVE_CONTEXT_MEMORY_MESSAGES", "8"))
    proactive_burst_window_seconds = float(os.getenv("PROACTIVE_BURST_WINDOW_SECONDS", "120"))
    proactive_burst_message_threshold = int(os.getenv("PROACTIVE_BURST_MESSAGE_THRESHOLD", "6"))
    proactive_burst_user_threshold = int(os.getenv("PROACTIVE_BURST_USER_THRESHOLD", "3"))
    proactive_name_triggers = env_list("PROACTIVE_NAME_TRIGGERS", "Esti,Estilord,Esti1ord,机器人,bot,小E")
    proactive_topic_keywords = env_list("PROACTIVE_TOPIC_KEYWORDS", "精神状态,吃什么,南航,中大,联谊,实习,秋招,保研,考研,游戏,开黑")
    proactive_light_keywords = env_list("PROACTIVE_LIGHT_KEYWORDS", "笑死,绷不住,服了,寄,困,累,无聊")
    proactive_score_name_trigger = float(os.getenv("PROACTIVE_SCORE_NAME_TRIGGER", "10"))
    proactive_score_topic_keyword = float(os.getenv("PROACTIVE_SCORE_TOPIC_KEYWORD", "4"))
    proactive_score_light_keyword = float(os.getenv("PROACTIVE_SCORE_LIGHT_KEYWORD", "2"))
    proactive_score_question = float(os.getenv("PROACTIVE_SCORE_QUESTION", "2"))
    proactive_score_open_question = float(os.getenv("PROACTIVE_SCORE_OPEN_QUESTION", "4"))
    proactive_score_burst = float(os.getenv("PROACTIVE_SCORE_BURST", "4"))
    proactive_score_multi_user = float(os.getenv("PROACTIVE_SCORE_MULTI_USER", "3"))
    proactive_sensitive_cooldown_seconds = float(os.getenv("PROACTIVE_SENSITIVE_COOLDOWN_SECONDS", "1800"))
    proactive_night_start = os.getenv("PROACTIVE_NIGHT_START", "00:30")
    proactive_night_end = os.getenv("PROACTIVE_NIGHT_END", "08:30")
    proactive_night_score_multiplier = float(os.getenv("PROACTIVE_NIGHT_SCORE_MULTIPLIER", "0.2"))
    proactive_sensitive_keywords = env_list("PROACTIVE_SENSITIVE_KEYWORDS", "密码,验证码,账号,诈骗,开盒,身份证,裸照")

    return Config(
        base_dir=resolved_base_dir,
        log_dir=log_dir,
        log_file=log_file,
        target_group_id=target_group_id,
        group_config_dir=group_config_dir,
        group_list_file=group_list_file,
        allowed_group_ids=allowed_group_ids,
        default_group_config_dir=default_group_config_dir,
        base_persona_file=base_persona_file,
        default_persona_file=default_persona_file,
        default_people_file=default_people_file,
        bot_qq=bot_qq,
        onebot_http_url=onebot_http_url,
        onebot_access_token=onebot_access_token,
        bridge_inbound_token=bridge_inbound_token,
        hermes_bin=hermes_bin,
        hermes_model=hermes_model,
        hermes_provider=hermes_provider,
        hermes_provider_base_url=hermes_provider_base_url,
        hermes_api_key_env=hermes_api_key_env,
        hermes_fallback_enabled=hermes_fallback_enabled,
        hermes_fallback_model=hermes_fallback_model,
        hermes_fallback_provider=hermes_fallback_provider,
        hermes_fallback_provider_base_url=hermes_fallback_provider_base_url,
        hermes_fallback_api_key_env=hermes_fallback_api_key_env,
        hermes_model_by_group=hermes_model_by_group,
        hermes_provider_by_group=hermes_provider_by_group,
        hermes_group_sessions_enabled=hermes_group_sessions_enabled,
        hermes_group_session_prefix=hermes_group_session_prefix,
        hermes_session_autocompact_enabled=hermes_session_autocompact_enabled,
        hermes_session_max_messages=hermes_session_max_messages,
        hermes_session_max_body_chars=hermes_session_max_body_chars,
        hermes_session_compact_summary_chars=hermes_session_compact_summary_chars,
        reply_prefix=reply_prefix,
        max_prompt_chars=max_prompt_chars,
        hermes_timeout=hermes_timeout,
        min_seconds_between_replies=min_seconds_between_replies,
        context_max_messages=context_max_messages,
        context_summary_max=context_summary_max,
        context_summarize_batch=context_summarize_batch,
        context_summary_max_chars=context_summary_max_chars,
        context_summarize_enabled=context_summarize_enabled,
        context_max_chars_per_message=context_max_chars_per_message,
        persona_file=persona_file,
        people_file=people_file,
        related_profile_max_matches=related_profile_max_matches,
        related_profile_min_keyword_len=related_profile_min_keyword_len,
        knowledge_max_chars=knowledge_max_chars,
        user_cooldown_seconds=user_cooldown_seconds,
        max_pending_replies=max_pending_replies,
        max_pending_direct_replies=max_pending_direct_replies,
        max_reply_chars=max_reply_chars,
        punctuation_style_enabled=punctuation_style_enabled,
        skip_unclear_mentions=skip_unclear_mentions,
        context_persist_enabled=context_persist_enabled,
        context_cache_file=context_cache_file,
        ocr_enabled=ocr_enabled,
        ocr_trigger_mode=ocr_trigger_mode,
        ocr_provider=ocr_provider,
        ocr_external_provider_allowed=ocr_external_provider_allowed,
        ocr_max_images_per_message=ocr_max_images_per_message,
        ocr_max_bytes_per_image=ocr_max_bytes_per_image,
        ocr_allowed_content_types=ocr_allowed_content_types,
        ocr_download_timeout=ocr_download_timeout,
        ocr_provider_timeout=ocr_provider_timeout,
        ocr_max_result_chars=ocr_max_result_chars,
        ocr_include_in_prompt=ocr_include_in_prompt,
        ocr_include_in_context=ocr_include_in_context,
        ocr_persist_text_in_context=ocr_persist_text_in_context,
        ocr_log_text=ocr_log_text,
        ocr_log_image_urls=ocr_log_image_urls,
        ocr_model=ocr_model,
        ocr_provider_base_url=ocr_provider_base_url,
        ocr_api_key_env=ocr_api_key_env,
        ocr_fallback_enabled=ocr_fallback_enabled,
        ocr_fallback_provider=ocr_fallback_provider,
        ocr_fallback_model=ocr_fallback_model,
        ocr_fallback_provider_base_url=ocr_fallback_provider_base_url,
        ocr_fallback_api_key_env=ocr_fallback_api_key_env,
        ocr_image_prompt=ocr_image_prompt,
        ocr_context_group_ids=ocr_context_group_ids,
        ocr_max_concurrent_tasks=ocr_max_concurrent_tasks,
        ocr_cache_ttl_seconds=ocr_cache_ttl_seconds,
        ocr_cache_max_entries=ocr_cache_max_entries,
        self_learning_enabled=self_learning_enabled,
        self_learning_collect_enabled=self_learning_collect_enabled,
        self_learning_inject_enabled=self_learning_inject_enabled,
        self_learning_allowed_group_ids=self_learning_allowed_group_ids,
        self_learning_min_message_chars=self_learning_min_message_chars,
        self_learning_max_message_chars=self_learning_max_message_chars,
        self_learning_max_samples_per_group=self_learning_max_samples_per_group,
        self_learning_retention_days=self_learning_retention_days,
        self_learning_max_prompt_chars=self_learning_max_prompt_chars,
        self_learning_min_count_for_prompt=self_learning_min_count_for_prompt,
        self_learning_data_filename=self_learning_data_filename,
        self_learning_config=self_learning_config,
        content_analysis_log_enabled=content_analysis_log_enabled,
        content_analysis_log_file=content_analysis_log_file,
        content_analysis_allowed_group_ids=content_analysis_allowed_group_ids,
        content_analysis_context_messages=content_analysis_context_messages,
        content_analysis_max_text_chars=content_analysis_max_text_chars,
        content_analysis_max_reply_chars=content_analysis_max_reply_chars,
        content_analysis_include_summaries=content_analysis_include_summaries,
        runtime_stats_enabled=runtime_stats_enabled,
        runtime_stats_file=runtime_stats_file,
        runtime_stats_user_hash_salt=runtime_stats_user_hash_salt,
        runtime_stats_summary_interval_seconds=runtime_stats_summary_interval_seconds,
        prometheus_enabled=prometheus_enabled,
        prometheus_include_group_id_label=prometheus_include_group_id_label,
        perf_obs_enabled=perf_obs_enabled,
        perf_obs_detail_level=perf_obs_detail_level,
        perf_obs_sample_rate=perf_obs_sample_rate,
        perf_obs_slow_reply_ms=perf_obs_slow_reply_ms,
        perf_obs_slow_hermes_ms=perf_obs_slow_hermes_ms,
        perf_obs_slow_send_ms=perf_obs_slow_send_ms,
        perf_obs_slow_ocr_ms=perf_obs_slow_ocr_ms,
        perf_obs_interaction_ttl_seconds=perf_obs_interaction_ttl_seconds,
        perf_obs_max_interactions=perf_obs_max_interactions,
        jrrp_state_file=jrrp_state_file,
        jrrp_results_file=jrrp_results_file,
        proactive_enabled=proactive_enabled,
        proactive_trigger_threshold=proactive_trigger_threshold,
        proactive_trigger_thresholds_by_group=proactive_trigger_thresholds_by_group,
        proactive_group_cooldown_seconds=proactive_group_cooldown_seconds,
        proactive_decay_per_minute=proactive_decay_per_minute,
        proactive_daily_limit_per_group=proactive_daily_limit_per_group,
        proactive_rate_limit_window_seconds=proactive_rate_limit_window_seconds,
        proactive_rate_limit_max_replies=proactive_rate_limit_max_replies,
        proactive_context_focus_messages=proactive_context_focus_messages,
        proactive_context_memory_messages=proactive_context_memory_messages,
        proactive_burst_window_seconds=proactive_burst_window_seconds,
        proactive_burst_message_threshold=proactive_burst_message_threshold,
        proactive_burst_user_threshold=proactive_burst_user_threshold,
        proactive_name_triggers=proactive_name_triggers,
        proactive_topic_keywords=proactive_topic_keywords,
        proactive_light_keywords=proactive_light_keywords,
        proactive_score_name_trigger=proactive_score_name_trigger,
        proactive_score_topic_keyword=proactive_score_topic_keyword,
        proactive_score_light_keyword=proactive_score_light_keyword,
        proactive_score_question=proactive_score_question,
        proactive_score_open_question=proactive_score_open_question,
        proactive_score_burst=proactive_score_burst,
        proactive_score_multi_user=proactive_score_multi_user,
        proactive_sensitive_cooldown_seconds=proactive_sensitive_cooldown_seconds,
        proactive_night_start=proactive_night_start,
        proactive_night_end=proactive_night_end,
        proactive_night_score_multiplier=proactive_night_score_multiplier,
        proactive_sensitive_keywords=proactive_sensitive_keywords,
        style_hints=list(STYLE_HINTS),
        reply_templates=_copy_reply_templates(),
    )


__all__ = [
    "Config",
    "REPLY_TEMPLATES",
    "STYLE_HINTS",
    "env_list",
    "load_config",
    "load_dotenv",
    "load_group_ids",
    "parse_group_float_map",
]
