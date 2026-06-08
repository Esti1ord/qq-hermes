#!/usr/bin/env python3
"""
QQ 群 @ Hermes 桥接服务。

用途：接收 NapCat/OneBot v11 的 HTTP 事件，只处理指定群内 @ 机器人账号的消息，调用 Hermes 生成回复，再通过 OneBot HTTP API 发回群里。

默认配置见同目录 .env.example。不要把 QQ 密码、验证码、二维码交给本脚本或 Hermes。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import shlex
import subprocess
import time
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from qq_hermes_bridge import app_helpers, command_utils, commands, config_utils, content_analysis_log as analysis_log_utils, context_store, events, group_files, handlers, hermes_runtime, jrrp, logging_utils, matching, media, media_fetch, metrics, model_output, onebot, outbound, proactive, profiles, reply_processing, reply_queue, runtime_stats, search, search_runtime, self_learning, text_utils, user_controls, vision

BASE_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "bridge.log"


def load_dotenv(path: Path) -> None:
    config_utils.load_dotenv(path)


load_dotenv(BASE_DIR / ".env")

TARGET_GROUP_ID = int(os.getenv("TARGET_GROUP_ID", "975805598"))
GROUP_CONFIG_DIR = Path(os.getenv("GROUP_CONFIG_DIR", str(BASE_DIR / "groups")))
GROUP_LIST_FILE = Path(os.getenv("GROUP_LIST_FILE", str(GROUP_CONFIG_DIR / "groups.txt")))


def load_group_ids() -> set[int]:
    ids: set[int] = set()
    raw = os.getenv("GROUP_IDS", os.getenv("ALLOWED_GROUP_IDS", ""))
    for item in raw.split(","):
        item = item.strip()
        if item:
            ids.add(int(item))
    if GROUP_LIST_FILE.exists():
        for raw_line in GROUP_LIST_FILE.read_text(encoding="utf-8").splitlines():
            line = raw_line.split("#", 1)[0].strip()
            if line:
                ids.add(int(line))
    ids.add(TARGET_GROUP_ID)
    return ids


ALLOWED_GROUP_IDS = load_group_ids()
DEFAULT_GROUP_CONFIG_DIR = GROUP_CONFIG_DIR
BASE_PERSONA_FILE = Path(os.getenv("BASE_PERSONA_FILE", str(BASE_DIR / "base_persona.md")))
DEFAULT_PERSONA_FILE = GROUP_CONFIG_DIR / str(TARGET_GROUP_ID) / "persona.md"
DEFAULT_PEOPLE_FILE = GROUP_CONFIG_DIR / str(TARGET_GROUP_ID) / "people.md"
BOT_QQ = os.getenv("BOT_QQ", "").strip()
ONEBOT_HTTP_URL = os.getenv("ONEBOT_HTTP_URL", "http://127.0.0.1:3000").rstrip("/")
ONEBOT_ACCESS_TOKEN = os.getenv("ONEBOT_ACCESS_TOKEN", "").strip()
BRIDGE_INBOUND_TOKEN = os.getenv("BRIDGE_INBOUND_TOKEN", "").strip()
HERMES_BIN = os.getenv("HERMES_BIN", "/home/roxy/.local/bin/hermes")
HERMES_MODEL = os.getenv("HERMES_MODEL", "").strip()
HERMES_PROVIDER = os.getenv("HERMES_PROVIDER", "").strip()
HERMES_MODEL_BY_GROUP = config_utils.parse_group_str_map(os.getenv("HERMES_MODEL_BY_GROUP", ""))
HERMES_PROVIDER_BY_GROUP = config_utils.parse_group_str_map(os.getenv("HERMES_PROVIDER_BY_GROUP", ""))
HERMES_GROUP_SESSIONS_ENABLED = os.getenv("HERMES_GROUP_SESSIONS_ENABLED", "true").lower() in {"1", "true", "yes"}
HERMES_GROUP_SESSION_PREFIX = os.getenv("HERMES_GROUP_SESSION_PREFIX", "qq-group").strip() or "qq-group"
HERMES_SESSION_AUTOCOMPACT_ENABLED = os.getenv("HERMES_SESSION_AUTOCOMPACT_ENABLED", "true").lower() in {"1", "true", "yes"}
HERMES_SESSION_MAX_MESSAGES = int(os.getenv("HERMES_SESSION_MAX_MESSAGES", "80"))
HERMES_SESSION_MAX_BODY_CHARS = int(os.getenv("HERMES_SESSION_MAX_BODY_CHARS", "180000"))
HERMES_SESSION_COMPACT_SUMMARY_CHARS = int(os.getenv("HERMES_SESSION_COMPACT_SUMMARY_CHARS", "1200"))
REPLY_PREFIX = os.getenv("REPLY_PREFIX", "").strip()
MAX_PROMPT_CHARS = int(os.getenv("MAX_PROMPT_CHARS", "3500"))
HERMES_TIMEOUT = int(os.getenv("HERMES_TIMEOUT", "180"))
MIN_SECONDS_BETWEEN_REPLIES = float(os.getenv("MIN_SECONDS_BETWEEN_REPLIES", "2"))
CONTEXT_MAX_MESSAGES = int(os.getenv("CONTEXT_MAX_MESSAGES", "20"))
CONTEXT_SUMMARY_MAX = int(os.getenv("CONTEXT_SUMMARY_MAX", "30"))
CONTEXT_SUMMARIZE_BATCH = int(os.getenv("CONTEXT_SUMMARIZE_BATCH", "5"))
CONTEXT_SUMMARY_MAX_CHARS = int(os.getenv("CONTEXT_SUMMARY_MAX_CHARS", "180"))
CONTEXT_SUMMARIZE_ENABLED = os.getenv("CONTEXT_SUMMARIZE_ENABLED", "true").lower() in {"1", "true", "yes"}
CONTEXT_MAX_CHARS_PER_MESSAGE = int(os.getenv("CONTEXT_MAX_CHARS_PER_MESSAGE", "300"))
PERSONA_FILE = Path(os.getenv("PERSONA_FILE", str(DEFAULT_PERSONA_FILE)))
PEOPLE_FILE = Path(os.getenv("PEOPLE_FILE", str(DEFAULT_PEOPLE_FILE)))
RELATED_PROFILE_MAX_MATCHES = int(os.getenv("RELATED_PROFILE_MAX_MATCHES", "3"))
RELATED_PROFILE_MIN_KEYWORD_LEN = int(os.getenv("RELATED_PROFILE_MIN_KEYWORD_LEN", "2"))
KNOWLEDGE_MAX_CHARS = int(os.getenv("KNOWLEDGE_MAX_CHARS", "3500"))
USER_COOLDOWN_SECONDS = float(os.getenv("USER_COOLDOWN_SECONDS", "20"))
MAX_PENDING_REPLIES = int(os.getenv("MAX_PENDING_REPLIES", "3"))
MAX_PENDING_DIRECT_REPLIES = int(os.getenv("MAX_PENDING_DIRECT_REPLIES", str(max(20, MAX_PENDING_REPLIES))))
MAX_REPLY_CHARS = int(os.getenv("MAX_REPLY_CHARS", "450"))
PUNCTUATION_STYLE_ENABLED = os.getenv("PUNCTUATION_STYLE_ENABLED", "true").lower() in {"1", "true", "yes"}
SKIP_UNCLEAR_MENTIONS = os.getenv("SKIP_UNCLEAR_MENTIONS", "true").lower() not in {"0", "false", "no"}
CONTEXT_PERSIST_ENABLED = os.getenv("CONTEXT_PERSIST_ENABLED", "false").lower() in {"1", "true", "yes"}
CONTEXT_CACHE_FILE = Path(os.getenv("CONTEXT_CACHE_FILE", str(BASE_DIR / "logs" / "recent_context.jsonl")))
OCR_ENABLED = config_utils.parse_bool(os.getenv("OCR_ENABLED", "false"))
OCR_TRIGGER_MODE = os.getenv("OCR_TRIGGER_MODE", "direct_only").strip() or "direct_only"
OCR_PROVIDER = os.getenv("OCR_PROVIDER", "hermes").strip() or "hermes"
OCR_EXTERNAL_PROVIDER_ALLOWED = config_utils.parse_bool(os.getenv("OCR_EXTERNAL_PROVIDER_ALLOWED", "false"))
OCR_MAX_IMAGES_PER_MESSAGE = int(os.getenv("OCR_MAX_IMAGES_PER_MESSAGE", "2"))
OCR_MAX_BYTES_PER_IMAGE = int(os.getenv("OCR_MAX_BYTES_PER_IMAGE", "6291456"))
OCR_ALLOWED_CONTENT_TYPES = set(config_utils.env_list("OCR_ALLOWED_CONTENT_TYPES", "image/jpeg,image/png,image/webp,image/gif"))
OCR_DOWNLOAD_TIMEOUT = float(os.getenv("OCR_DOWNLOAD_TIMEOUT", "8"))
OCR_PROVIDER_TIMEOUT = float(os.getenv("OCR_PROVIDER_TIMEOUT", "30"))
OCR_MAX_RESULT_CHARS = int(os.getenv("OCR_MAX_RESULT_CHARS", "800"))
OCR_INCLUDE_IN_PROMPT = config_utils.parse_bool(os.getenv("OCR_INCLUDE_IN_PROMPT", "true"))
OCR_INCLUDE_IN_CONTEXT = config_utils.parse_bool(os.getenv("OCR_INCLUDE_IN_CONTEXT", "true"))
OCR_PERSIST_TEXT_IN_CONTEXT = config_utils.parse_bool(os.getenv("OCR_PERSIST_TEXT_IN_CONTEXT", "false"))
OCR_LOG_TEXT = config_utils.parse_bool(os.getenv("OCR_LOG_TEXT", "false"))
OCR_LOG_IMAGE_URLS = config_utils.parse_bool(os.getenv("OCR_LOG_IMAGE_URLS", "false"))
OCR_MODEL = os.getenv("OCR_MODEL", "").strip()
OCR_PROVIDER_BASE_URL = os.getenv("OCR_PROVIDER_BASE_URL", "").strip()
OCR_API_KEY_ENV = os.getenv("OCR_API_KEY_ENV", "").strip()
OCR_IMAGE_PROMPT = os.getenv("OCR_IMAGE_PROMPT", vision.DEFAULT_IMAGE_PROMPT).strip() or vision.DEFAULT_IMAGE_PROMPT
OCR_CONTEXT_GROUP_IDS = analysis_log_utils.parse_group_ids(os.getenv("OCR_CONTEXT_GROUP_IDS", ""))
OCR_MAX_CONCURRENT_TASKS = max(1, int(os.getenv("OCR_MAX_CONCURRENT_TASKS", "2")))
OCR_CACHE_TTL_SECONDS = max(0.0, float(os.getenv("OCR_CACHE_TTL_SECONDS", "3600")))
OCR_CACHE_MAX_ENTRIES = max(0, int(os.getenv("OCR_CACHE_MAX_ENTRIES", "512")))
SELF_LEARNING_ENABLED = config_utils.parse_bool(os.getenv("SELF_LEARNING_ENABLED", "false"))
SELF_LEARNING_COLLECT_ENABLED = config_utils.parse_bool(os.getenv("SELF_LEARNING_COLLECT_ENABLED", "true" if SELF_LEARNING_ENABLED else "false"))
SELF_LEARNING_INJECT_ENABLED = config_utils.parse_bool(os.getenv("SELF_LEARNING_INJECT_ENABLED", "true" if SELF_LEARNING_ENABLED else "false"))
SELF_LEARNING_ALLOWED_GROUP_IDS = analysis_log_utils.parse_group_ids(os.getenv("SELF_LEARNING_ALLOWED_GROUP_IDS", ""))
SELF_LEARNING_MIN_MESSAGE_CHARS = int(os.getenv("SELF_LEARNING_MIN_MESSAGE_CHARS", "2"))
SELF_LEARNING_MAX_MESSAGE_CHARS = int(os.getenv("SELF_LEARNING_MAX_MESSAGE_CHARS", "300"))
SELF_LEARNING_MAX_SAMPLES_PER_GROUP = int(os.getenv("SELF_LEARNING_MAX_SAMPLES_PER_GROUP", "500"))
SELF_LEARNING_RETENTION_DAYS = int(os.getenv("SELF_LEARNING_RETENTION_DAYS", "30"))
SELF_LEARNING_MAX_PROMPT_CHARS = int(os.getenv("SELF_LEARNING_MAX_PROMPT_CHARS", "500"))
SELF_LEARNING_MIN_COUNT_FOR_PROMPT = int(os.getenv("SELF_LEARNING_MIN_COUNT_FOR_PROMPT", "3"))
SELF_LEARNING_DATA_FILENAME = os.getenv("SELF_LEARNING_DATA_FILENAME", "self_learning.json").strip() or "self_learning.json"
SELF_LEARNING_CONFIG = self_learning.SelfLearningConfig(
    enabled=SELF_LEARNING_ENABLED,
    collect_enabled=SELF_LEARNING_COLLECT_ENABLED,
    inject_enabled=SELF_LEARNING_INJECT_ENABLED,
    allowed_group_ids=SELF_LEARNING_ALLOWED_GROUP_IDS,
    min_message_chars=SELF_LEARNING_MIN_MESSAGE_CHARS,
    max_message_chars=SELF_LEARNING_MAX_MESSAGE_CHARS,
    max_samples_per_group=SELF_LEARNING_MAX_SAMPLES_PER_GROUP,
    retention_days=SELF_LEARNING_RETENTION_DAYS,
    max_prompt_chars=SELF_LEARNING_MAX_PROMPT_CHARS,
    min_count_for_prompt=SELF_LEARNING_MIN_COUNT_FOR_PROMPT,
    data_filename=SELF_LEARNING_DATA_FILENAME,
)
CONTENT_ANALYSIS_LOG_ENABLED = analysis_log_utils.enabled_from_env(os.getenv("CONTENT_ANALYSIS_LOG_ENABLED", "false"))
CONTENT_ANALYSIS_LOG_FILE = Path(os.getenv("CONTENT_ANALYSIS_LOG_FILE", str(LOG_DIR / "content_analysis.jsonl")))
CONTENT_ANALYSIS_ALLOWED_GROUP_IDS = analysis_log_utils.parse_group_ids(os.getenv("CONTENT_ANALYSIS_ALLOWED_GROUP_IDS", ""))
CONTENT_ANALYSIS_CONTEXT_MESSAGES = int(os.getenv("CONTENT_ANALYSIS_CONTEXT_MESSAGES", "8"))
CONTENT_ANALYSIS_MAX_TEXT_CHARS = int(os.getenv("CONTENT_ANALYSIS_MAX_TEXT_CHARS", "1000"))
CONTENT_ANALYSIS_MAX_REPLY_CHARS = int(os.getenv("CONTENT_ANALYSIS_MAX_REPLY_CHARS", "1000"))
CONTENT_ANALYSIS_INCLUDE_SUMMARIES = os.getenv("CONTENT_ANALYSIS_INCLUDE_SUMMARIES", "true").lower() in {"1", "true", "yes"}
RUNTIME_STATS_ENABLED = runtime_stats.enabled_from_env(os.getenv("RUNTIME_STATS_ENABLED", "true"))
RUNTIME_STATS_FILE = Path(os.getenv("RUNTIME_STATS_FILE", str(LOG_DIR / "runtime_stats.jsonl")))
RUNTIME_STATS_USER_HASH_SALT = os.getenv("RUNTIME_STATS_USER_HASH_SALT", BOT_QQ or "qq-hermes-local")
RUNTIME_STATS_SUMMARY_INTERVAL_SECONDS = float(os.getenv("RUNTIME_STATS_SUMMARY_INTERVAL_SECONDS", "300"))
PROMETHEUS_ENABLED = config_utils.parse_bool(os.getenv("PROMETHEUS_ENABLED", "true"))
PROMETHEUS_INCLUDE_GROUP_ID_LABEL = config_utils.parse_bool(os.getenv("PROMETHEUS_INCLUDE_GROUP_ID_LABEL", "false"))
metrics.configure(enabled=PROMETHEUS_ENABLED, include_group_id_label=PROMETHEUS_INCLUDE_GROUP_ID_LABEL)
PERF_OBS_ENABLED = config_utils.parse_bool(os.getenv("PERF_OBS_ENABLED", "true"))
PERF_OBS_DETAIL_LEVEL = runtime_stats.normalize_label(os.getenv("PERF_OBS_DETAIL_LEVEL", "standard"), default="standard")
PERF_OBS_SAMPLE_RATE = max(0.0, min(1.0, float(os.getenv("PERF_OBS_SAMPLE_RATE", "1.0"))))
PERF_OBS_SLOW_REPLY_MS = int(os.getenv("PERF_OBS_SLOW_REPLY_MS", "15000"))
PERF_OBS_SLOW_HERMES_MS = int(os.getenv("PERF_OBS_SLOW_HERMES_MS", "10000"))
PERF_OBS_SLOW_SEND_MS = int(os.getenv("PERF_OBS_SLOW_SEND_MS", "3000"))
PERF_OBS_SLOW_OCR_MS = int(os.getenv("PERF_OBS_SLOW_OCR_MS", "8000"))
PERF_OBS_SLOW_SEARCH_MS = int(os.getenv("PERF_OBS_SLOW_SEARCH_MS", "10000"))
PERF_OBS_INTERACTION_TTL_SECONDS = float(os.getenv("PERF_OBS_INTERACTION_TTL_SECONDS", "3600"))
PERF_OBS_MAX_INTERACTIONS = int(os.getenv("PERF_OBS_MAX_INTERACTIONS", "2000"))
JRRP_STATE_FILE = Path(os.getenv("JRRP_STATE_FILE", str(LOG_DIR / "jrrp_state.json")))
JRRP_RESULTS_FILE = Path(os.getenv("JRRP_RESULTS_FILE", str(BASE_DIR / "jrrp_results.json")))
def env_list(name: str, default: str) -> list[str]:
    return config_utils.env_list(name, default)


def parse_group_float_map(raw: str) -> dict[int, float]:
    return config_utils.parse_group_float_map(raw)


PROACTIVE_ENABLED = os.getenv("PROACTIVE_ENABLED", "true").lower() in {"1", "true", "yes"}
PROACTIVE_TRIGGER_THRESHOLD = float(os.getenv("PROACTIVE_TRIGGER_THRESHOLD", "16"))
PROACTIVE_TRIGGER_THRESHOLDS_BY_GROUP = parse_group_float_map(os.getenv("PROACTIVE_TRIGGER_THRESHOLDS_BY_GROUP", ""))
PROACTIVE_GROUP_COOLDOWN_SECONDS = float(os.getenv("PROACTIVE_GROUP_COOLDOWN_SECONDS", "900"))
PROACTIVE_DECAY_PER_MINUTE = float(os.getenv("PROACTIVE_DECAY_PER_MINUTE", "1"))
PROACTIVE_DAILY_LIMIT_PER_GROUP = int(os.getenv("PROACTIVE_DAILY_LIMIT_PER_GROUP", "8"))
PROACTIVE_RATE_LIMIT_WINDOW_SECONDS = float(os.getenv("PROACTIVE_RATE_LIMIT_WINDOW_SECONDS", "60"))
PROACTIVE_RATE_LIMIT_MAX_REPLIES = int(os.getenv("PROACTIVE_RATE_LIMIT_MAX_REPLIES", "6"))
PROACTIVE_CONTEXT_FOCUS_MESSAGES = int(os.getenv("PROACTIVE_CONTEXT_FOCUS_MESSAGES", "3"))
PROACTIVE_CONTEXT_MEMORY_MESSAGES = int(os.getenv("PROACTIVE_CONTEXT_MEMORY_MESSAGES", "8"))
PROACTIVE_BURST_WINDOW_SECONDS = float(os.getenv("PROACTIVE_BURST_WINDOW_SECONDS", "120"))
PROACTIVE_BURST_MESSAGE_THRESHOLD = int(os.getenv("PROACTIVE_BURST_MESSAGE_THRESHOLD", "6"))
PROACTIVE_BURST_USER_THRESHOLD = int(os.getenv("PROACTIVE_BURST_USER_THRESHOLD", "3"))
PROACTIVE_NAME_TRIGGERS = env_list("PROACTIVE_NAME_TRIGGERS", "Esti,Estilord,Esti1ord,机器人,bot,小E")
PROACTIVE_TOPIC_KEYWORDS = env_list("PROACTIVE_TOPIC_KEYWORDS", "精神状态,吃什么,南航,中大,联谊,实习,秋招,保研,考研,游戏,开黑")
PROACTIVE_LIGHT_KEYWORDS = env_list("PROACTIVE_LIGHT_KEYWORDS", "笑死,绷不住,服了,寄,困,累,无聊")
PROACTIVE_SCORE_NAME_TRIGGER = float(os.getenv("PROACTIVE_SCORE_NAME_TRIGGER", "10"))
PROACTIVE_SCORE_TOPIC_KEYWORD = float(os.getenv("PROACTIVE_SCORE_TOPIC_KEYWORD", "4"))
PROACTIVE_SCORE_LIGHT_KEYWORD = float(os.getenv("PROACTIVE_SCORE_LIGHT_KEYWORD", "2"))
PROACTIVE_SCORE_QUESTION = float(os.getenv("PROACTIVE_SCORE_QUESTION", "2"))
PROACTIVE_SCORE_OPEN_QUESTION = float(os.getenv("PROACTIVE_SCORE_OPEN_QUESTION", "4"))
PROACTIVE_SCORE_BURST = float(os.getenv("PROACTIVE_SCORE_BURST", "4"))
PROACTIVE_SCORE_MULTI_USER = float(os.getenv("PROACTIVE_SCORE_MULTI_USER", "3"))
PROACTIVE_SENSITIVE_COOLDOWN_SECONDS = float(os.getenv("PROACTIVE_SENSITIVE_COOLDOWN_SECONDS", "1800"))
PROACTIVE_NIGHT_START = os.getenv("PROACTIVE_NIGHT_START", "00:30")
PROACTIVE_NIGHT_END = os.getenv("PROACTIVE_NIGHT_END", "08:30")
PROACTIVE_NIGHT_SCORE_MULTIPLIER = float(os.getenv("PROACTIVE_NIGHT_SCORE_MULTIPLIER", "0.2"))
PROACTIVE_SENSITIVE_KEYWORDS = env_list("PROACTIVE_SENSITIVE_KEYWORDS", "密码,验证码,账号,诈骗,开盒,身份证,裸照")
WEB_SEARCH_ENABLED = os.getenv("WEB_SEARCH_ENABLED", "true").lower() in {"1", "true", "yes"}
WEB_SEARCH_TIMEOUT = int(os.getenv("WEB_SEARCH_TIMEOUT", "45"))
WEB_SEARCH_MAX_CHARS = int(os.getenv("WEB_SEARCH_MAX_CHARS", "1200"))
WEB_SEARCH_BACKEND = os.getenv("WEB_SEARCH_BACKEND", "curl").strip().lower()
WEB_SEARCH_MODEL = os.getenv("WEB_SEARCH_MODEL", HERMES_MODEL).strip() or HERMES_MODEL
WEB_SEARCH_PROVIDER = os.getenv("WEB_SEARCH_PROVIDER", HERMES_PROVIDER).strip()
WEB_SEARCH_HTTP_TIMEOUT = float(os.getenv("WEB_SEARCH_HTTP_TIMEOUT", "8"))
WEB_SEARCH_MAX_SUCCESSFUL_FETCHES = int(os.getenv("WEB_SEARCH_MAX_SUCCESSFUL_FETCHES", "3"))
WEB_SEARCH_NOTICE_ENABLED = os.getenv("WEB_SEARCH_NOTICE_ENABLED", "true").lower() in {"1", "true", "yes"}
WEB_SEARCH_NOTICE_TEXT = os.getenv("WEB_SEARCH_NOTICE_TEXT", "我先联网查一下").strip() or "我先联网查一下"
DEEPSEEK_COMMAND_MODEL = os.getenv("DEEPSEEK_COMMAND_MODEL", HERMES_MODEL or "gpt-5.5").strip() or "gpt-5.5"
DEEPSEEK_COMMAND_PROVIDER = os.getenv("DEEPSEEK_COMMAND_PROVIDER", HERMES_PROVIDER).strip()
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
    "web_search_failed": [
        "（联网搜索刚才失败了；回复时说明不确定，别编最新信息。）",
        "（这次搜索没跑通；回复时按不确定处理，不要硬编。）",
        "（实时检索失败；只能说明没查准，不要补旧消息。）",
    ],
    "web_search_no_match": [
        "没搜到特别可靠的结果 先别当准信",
        "这次没搜准 可能得换个关键词",
        "没查到够稳的来源 先按不确定处理",
    ],
    "web_search_empty": [
        "（联网搜索没有明确结果；回复时说明不确定。）",
        "（搜索摘录不够明确；回复时别下定论。）",
        "（没拿到清楚结果；回复时说还没查准。）",
    ],
}


def pick_template(name: str, key: str = "") -> str:
    return logging_utils.pick_template(name, key, templates=REPLY_TEMPLATES)

_last_user_reply_at: dict[str, float] = {}
_pending_replies = 0
_recent_messages_by_group: dict[int, deque[dict[str, Any]]] = {}
_context_summaries_by_group: dict[int, deque[str]] = {}
_proactive_state_by_group: dict[int, dict[str, Any]] = {}
_recent_activity_by_group: dict[int, deque[dict[str, Any]]] = {}
_processed_event_keys: deque[str] = deque(maxlen=500)
_processed_event_key_set: set[str] = set()
_proactive_inflight_groups: set[int] = set()
_direct_reply_inflight_groups: set[int] = set()
_proactive_reply_times_by_group: dict[int, deque[float]] = {}
_reply_queue_by_group: dict[Any, deque[dict[str, Any]]] = {}
_reply_locks_by_group: dict[int, asyncio.Lock] = {}
_reply_workers_by_group: dict[int, asyncio.Task] = {}
_recent_outbound_by_group: dict[int, deque[dict[str, Any]]] = {}
_outbound_inflight_by_group: dict[int, set[str]] = {}
_runtime_started_at = time.time()
_last_runtime_summary_at = _runtime_started_at
_runtime_counters: dict[str, int] = {}
_interaction_started_at: dict[str, float] = {}
_interaction_order: deque[str] = deque(maxlen=max(1, PERF_OBS_MAX_INTERACTIONS))
_ocr_result_cache: dict[str, tuple[float, media.MediaRecognition]] = {}
_ocr_inflight: dict[str, asyncio.Task] = {}
_ocr_context_tasks: set[asyncio.Task] = set()
_ocr_semaphore: asyncio.Semaphore | None = None


def log(obj: Any) -> None:
    logging_utils.log(obj, log_file=LOG_FILE)


def runtime_stat(stat: str, **fields: Any) -> None:
    metrics.observe_runtime_stat(stat, fields)
    if not RUNTIME_STATS_ENABLED:
        return
    if os.getenv("PYTEST_CURRENT_TEST") and RUNTIME_STATS_FILE == LOG_DIR / "runtime_stats.jsonl":
        return
    event = runtime_stats.sanitize_stat_fields(stat, fields)
    event.setdefault("uptime_s", max(0, int(time.time() - _runtime_started_at)))
    RUNTIME_STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
    logging_utils.log(event, log_file=RUNTIME_STATS_FILE)


def increment_runtime_counter(name: str, amount: int = 1) -> None:
    _runtime_counters[name] = int(_runtime_counters.get(name, 0)) + int(amount)
    metrics.observe_runtime_counter(name, amount)


def runtime_user_hash(user_id: Any) -> str:
    if user_id in (None, ""):
        return ""
    return runtime_stats.safe_user_hash(user_id, salt=RUNTIME_STATS_USER_HASH_SALT)


def maybe_log_runtime_summary(now: float | None = None) -> None:
    global _last_runtime_summary_at
    current = time.time() if now is None else now
    if current - _last_runtime_summary_at < RUNTIME_STATS_SUMMARY_INTERVAL_SECONDS:
        return
    summary = runtime_stats.runtime_summary(_runtime_counters, started_at=_runtime_started_at, now=current)
    runtime_stat("runtime_summary", **summary)
    _last_runtime_summary_at = current


def runtime_event_record(event: dict[str, Any]) -> dict[str, Any]:
    return runtime_stats.safe_event_record(
        event,
        message_to_text_fn=message_to_text,
        is_allowed_group_fn=is_allowed_group,
        is_at_me_fn=is_at_me,
        is_reply_to_me_fn=is_reply_to_me,
        user_hash_salt=RUNTIME_STATS_USER_HASH_SALT,
    )


def runtime_now() -> float:
    return time.monotonic()


def runtime_elapsed_ms(start: float | None) -> int:
    if start is None:
        return 0
    return runtime_stats.duration_ms(start)


def runtime_perf_enabled() -> bool:
    return bool(RUNTIME_STATS_ENABLED and PERF_OBS_ENABLED and PERF_OBS_SAMPLE_RATE > 0)


def emit_perf_stat(stat: str, **fields: Any) -> None:
    enriched = dict(fields)
    if "duration_ms" in enriched and "duration_bucket" not in enriched:
        enriched["duration_bucket"] = runtime_stats.duration_bucket(enriched.get("duration_ms") or 0)
    if "queue_wait_ms" in enriched and "queue_wait_bucket" not in enriched:
        enriched["queue_wait_bucket"] = runtime_stats.duration_bucket(enriched.get("queue_wait_ms") or 0)
    if "e2e_ms" in enriched and "e2e_bucket" not in enriched:
        enriched["e2e_bucket"] = runtime_stats.duration_bucket(enriched.get("e2e_ms") or 0)
    if "output_len" in enriched and "output_len_bucket" not in enriched:
        enriched["output_len_bucket"] = runtime_stats.length_bucket(enriched.get("output_len") or 0)
    if "result_len" in enriched and "result_len_bucket" not in enriched:
        enriched["result_len_bucket"] = runtime_stats.length_bucket(enriched.get("result_len") or 0)
    if not runtime_perf_enabled():
        metrics.observe_runtime_stat(stat, enriched)
        return
    runtime_stat(stat, **enriched)


def runtime_interaction_id(event: dict[str, Any]) -> str:
    return runtime_stats.safe_interaction_hash(
        [
            event.get("group_id"),
            event.get("user_id"),
            event.get("message_id") or event.get("id") or event.get("message_seq") or event.get("real_id"),
            event.get("time"),
            event.get("post_type"),
            event.get("message_type"),
        ],
        salt=RUNTIME_STATS_USER_HASH_SALT,
    )


def remember_interaction_start(interaction_id: str, started_at: float) -> None:
    if not interaction_id:
        return
    _interaction_started_at[interaction_id] = started_at
    _interaction_order.append(interaction_id)
    while len(_interaction_started_at) > PERF_OBS_MAX_INTERACTIONS and _interaction_order:
        _interaction_started_at.pop(_interaction_order.popleft(), None)
    cutoff = runtime_now() - PERF_OBS_INTERACTION_TTL_SECONDS
    expired = [key for key, ts in _interaction_started_at.items() if ts < cutoff]
    for key in expired:
        _interaction_started_at.pop(key, None)


def interaction_e2e_ms(interaction_id: str | None, fallback_start: float | None = None) -> int:
    if interaction_id and interaction_id in _interaction_started_at:
        return runtime_elapsed_ms(_interaction_started_at.get(interaction_id))
    return runtime_elapsed_ms(fallback_start)


def interaction_safe_fields(event: dict[str, Any], interaction_id: str) -> dict[str, Any]:
    return {
        "interaction_id": interaction_id,
        "group_id": group_id_from_event(event),
        "user_hash": runtime_user_hash(event.get("user_id")),
    }


def runtime_route_decision(route: str, **fields: Any) -> None:
    emit_perf_stat("route_decision", route=runtime_stats.normalize_label(route), **fields)


def message_id_from_event(event: dict[str, Any]) -> str:
    for key in ("message_id", "id", "msg_id", "message_seq", "real_id"):
        if event.get(key) not in (None, ""):
            return str(event.get(key))
    return ""


def reply_message_for_event(event: dict[str, Any], message: str) -> str:
    return outbound.reply_to_message(message, message_id_from_event(event))


def is_name_mention(event: dict[str, Any]) -> bool:
    text = message_to_text(event.get("message"), include_at=False)
    return matching.contains_any_phrase(text, PROACTIVE_NAME_TRIGGERS, case_sensitive=False)


def message_identity_from_event(event: dict[str, Any]) -> dict[str, str]:
    identity: dict[str, str] = {}
    for key in ("message_id", "id", "msg_id", "message_seq", "real_id"):
        if event.get(key) not in (None, ""):
            identity[key] = str(event.get(key))
    return identity


def content_analysis_enabled_for_group(group_id: Any) -> bool:
    if not CONTENT_ANALYSIS_LOG_ENABLED:
        return False
    try:
        gid = int(group_id)
    except (TypeError, ValueError):
        return False
    if gid not in ALLOWED_GROUP_IDS:
        return False
    if CONTENT_ANALYSIS_ALLOWED_GROUP_IDS and gid not in CONTENT_ANALYSIS_ALLOWED_GROUP_IDS:
        return False
    return True


def analysis_context_snapshot(group_id: int | None) -> dict[str, Any]:
    if group_id is None:
        return {}
    return analysis_log_utils.context_snapshot(
        list(recent_messages_for_group(group_id)),
        list(context_summaries_for_group(group_id)),
        max_messages=CONTENT_ANALYSIS_CONTEXT_MESSAGES,
        max_chars=CONTENT_ANALYSIS_MAX_TEXT_CHARS,
        include_summaries=CONTENT_ANALYSIS_INCLUDE_SUMMARIES,
    )


def content_analysis_log(kind: str, group_id: int | None, **fields: Any) -> None:
    if not content_analysis_enabled_for_group(group_id):
        return
    max_chars = CONTENT_ANALYSIS_MAX_REPLY_CHARS if "reply" in str(kind) else CONTENT_ANALYSIS_MAX_TEXT_CHARS
    try:
        record = analysis_log_utils.sanitize_record(
            {"type": "content_analysis", "kind": kind, "group_id": group_id, **fields},
            max_chars=max_chars,
        )
        if isinstance(record, dict):
            analysis_log_utils.append_jsonl(CONTENT_ANALYSIS_LOG_FILE, record)
    except Exception as exc:
        log({"type": "content_analysis_log_error", "group_id": group_id, "error": type(exc).__name__})


def content_analysis_user_fields(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_id": event.get("user_id"),
        "sender": _sender_name(event),
        "message_id": message_id_from_event(event),
    }


def message_to_analysis_text(event: dict[str, Any], *, include_at: bool = False, max_chars: int | None = None) -> dict[str, Any]:
    return analysis_log_utils.sanitize_text(
        message_to_text(event.get("message"), include_at=include_at),
        CONTENT_ANALYSIS_MAX_TEXT_CHARS if max_chars is None else max_chars,
    )


def reply_to_analysis_text(reply: str) -> dict[str, Any]:
    return analysis_log_utils.sanitize_text(reply, CONTENT_ANALYSIS_MAX_REPLY_CHARS)


def segment_types_for_analysis(event: dict[str, Any]) -> dict[str, int]:
    return runtime_stats.segment_type_counts(event.get("message"))


def message_to_text(message: Any, include_at: bool = True) -> str:
    """兼容 OneBot 的 string 和 message segment array。"""
    return onebot.message_to_text(
        message,
        include_at=include_at,
        display_name_by_qq_fn=profile_display_name_by_qq,
    )


def _sender_name(event: dict[str, Any]) -> str:
    return onebot.sender_name(event)


def group_id_from_event(event: dict[str, Any], default: int | None = TARGET_GROUP_ID) -> int | None:
    return onebot.group_id_from_event(event, default=default)


def is_allowed_group(event: dict[str, Any]) -> bool:
    return onebot.is_allowed_group(event, allowed_group_ids=ALLOWED_GROUP_IDS)


def ocr_context_enabled_for_group(group_id: int | None) -> bool:
    if group_id is None or group_id not in ALLOWED_GROUP_IDS:
        return False
    if OCR_CONTEXT_GROUP_IDS and group_id not in OCR_CONTEXT_GROUP_IDS:
        return False
    return True


def persona_file_for_group(group_id: int) -> Path:
    return group_files.persona_file_for_group(
        group_id,
        group_config_dir=GROUP_CONFIG_DIR,
        target_group_id=TARGET_GROUP_ID,
        persona_file=PERSONA_FILE,
        default_persona_file=DEFAULT_PERSONA_FILE,
        default_group_config_dir=DEFAULT_GROUP_CONFIG_DIR,
    )


def knowledge_file_for_group(group_id: int) -> Path:
    return group_files.knowledge_file_for_group(group_id, group_config_dir=GROUP_CONFIG_DIR)


def knowledge_for_prompt(group_id: int | None) -> str:
    return group_files.knowledge_for_prompt(
        group_id,
        target_group_id=TARGET_GROUP_ID,
        knowledge_max_chars=KNOWLEDGE_MAX_CHARS,
        knowledge_file_for_group_fn=knowledge_file_for_group,
        load_text_file_fn=load_text_file,
    )


def group_people_file_for_prompt(group_id: int) -> Path | None:
    return group_files.group_people_file_for_prompt(
        group_id,
        target_group_id=TARGET_GROUP_ID,
        people_file=PEOPLE_FILE,
        persona_file=PERSONA_FILE,
        default_people_file=DEFAULT_PEOPLE_FILE,
        default_persona_file=DEFAULT_PERSONA_FILE,
        group_people_file_for_group_fn=group_people_file_for_group,
    )


def persona_file_for_prompt(group_id: int) -> Path:
    return group_files.persona_file_for_prompt(
        group_id,
        target_group_id=TARGET_GROUP_ID,
        people_file=PEOPLE_FILE,
        persona_file=PERSONA_FILE,
        default_people_file=DEFAULT_PEOPLE_FILE,
        default_persona_file=DEFAULT_PERSONA_FILE,
        persona_file_for_group_fn=persona_file_for_group,
    )


def group_prompt_for_prompt(group_id: int) -> str:
    return group_files.group_prompt_for_prompt(
        group_id,
        persona_file_for_prompt_fn=persona_file_for_prompt,
        load_text_file_fn=load_text_file,
    )


def base_persona_for_prompt() -> str:
    return group_files.base_persona_for_prompt(
        base_persona_file=BASE_PERSONA_FILE,
        load_text_file_fn=load_text_file,
    )


def persona_bundle_for_prompt(group_id: int | None = None) -> str:
    return group_files.persona_bundle_for_prompt(
        group_id,
        base_persona_for_prompt_fn=base_persona_for_prompt,
        group_prompt_for_prompt_fn=group_prompt_for_prompt,
    )


def strip_normal_chat_search_guidance(text: str) -> str:
    """普通聊天不再承载联网搜索功能，过滤人设/知识库里的旧搜索指令。"""
    return group_files.strip_normal_chat_search_guidance(text)


def normal_chat_persona_bundle_for_prompt(group_id: int | None = None) -> str:
    return group_files.normal_chat_persona_bundle_for_prompt(
        group_id,
        persona_bundle_for_prompt_fn=persona_bundle_for_prompt,
    )


def normal_chat_knowledge_for_prompt(group_id: int | None = None) -> str:
    return group_files.normal_chat_knowledge_for_prompt()


def search_knowledge_for_prompt(group_id: int | None = None) -> str:
    return knowledge_for_prompt(group_id)


def recent_messages_for_group(group_id: int) -> deque[dict[str, Any]]:
    return context_store.recent_messages_for_group(group_id, _recent_messages_by_group)


def context_summaries_for_group(group_id: int) -> deque[str]:
    return context_store.context_summaries_for_group(
        group_id,
        _context_summaries_by_group,
        maxlen=CONTEXT_SUMMARY_MAX,
    )


def proactive_state_for_group(group_id: int) -> dict[str, Any]:
    today = datetime.now().strftime("%Y-%m-%d")
    if group_id not in _proactive_state_by_group:
        _proactive_state_by_group[group_id] = {
            "score": 0.0,
            "last_decay_at": 0.0,
            "last_proactive_at": 0.0,
            "daily_count": 0,
            "daily_date": today,
            "sensitive_until": 0.0,
        }
    state = _proactive_state_by_group[group_id]
    if state.get("daily_date") != today:
        state["daily_date"] = today
        state["daily_count"] = 0
    return state


def recent_activity_for_group(group_id: int) -> deque[dict[str, Any]]:
    if group_id not in _recent_activity_by_group:
        _recent_activity_by_group[group_id] = deque(maxlen=80)
    return _recent_activity_by_group[group_id]


def proactive_reply_times_for_group(group_id: int) -> deque[float]:
    if group_id not in _proactive_reply_times_by_group:
        _proactive_reply_times_by_group[group_id] = deque(maxlen=max(1, PROACTIVE_RATE_LIMIT_MAX_REPLIES))
    return _proactive_reply_times_by_group[group_id]


def reply_queue_for_group(group_id: int, kind: str = "direct") -> deque[dict[str, Any]]:
    return reply_queue.queue_for_group(
        group_id,
        queues=_reply_queue_by_group,
        max_pending_replies=MAX_PENDING_REPLIES,
        proactive_rate_limit_max_replies=PROACTIVE_RATE_LIMIT_MAX_REPLIES,
        kind=kind,
        max_pending_direct_replies=MAX_PENDING_DIRECT_REPLIES,
    )


def reply_lock_for_group(group_id: int) -> asyncio.Lock:
    if group_id not in _reply_locks_by_group:
        _reply_locks_by_group[group_id] = asyncio.Lock()
    return _reply_locks_by_group[group_id]


def enqueue_reply_intent(group_id: int, intent: dict[str, Any]) -> dict[str, Any]:
    now = runtime_now()
    intent.setdefault("_perf_enqueued_at", now)
    intent.setdefault("_perf_kind", intent.get("kind") or "unknown")
    event = intent.get("event") if isinstance(intent.get("event"), dict) else {}
    if event:
        interaction_id = intent.setdefault("_perf_interaction_id", runtime_interaction_id(event))
        intent.setdefault("_perf_event_received_at", _interaction_started_at.get(interaction_id, now))
    else:
        interaction_id = str(intent.get("_perf_interaction_id") or "")
    queued = reply_queue.enqueue(
        group_id,
        intent,
        queues=_reply_queue_by_group,
        max_pending_replies=MAX_PENDING_REPLIES,
        proactive_rate_limit_max_replies=PROACTIVE_RATE_LIMIT_MAX_REPLIES,
        max_pending_direct_replies=MAX_PENDING_DIRECT_REPLIES,
    )
    log({
        "type": "reply_queued" if queued.get("queued") else "reply_queue_rejected",
        "group_id": group_id,
        "kind": queued.get("kind") or intent.get("kind"),
        "queued": queued.get("queued"),
        "queue_size": queued.get("queue_size"),
        "queue_limit": queued.get("queue_limit"),
        "reason": queued.get("reason"),
    })
    increment_runtime_counter("reply_enqueued" if queued.get("queued") else "queue_full")
    emit_perf_stat(
        "queue_event",
        group_id=group_id,
        interaction_id=interaction_id,
        kind=queued.get("kind") or intent.get("kind"),
        queued=bool(queued.get("queued")),
        queue_size=queued.get("queue_size"),
        queue_limit=queued.get("queue_limit"),
        reason=queued.get("reason") or "",
        event_to_enqueue_ms=runtime_elapsed_ms(intent.get("_perf_event_received_at")),
        direct_queue_size=reply_queue_size_by_kind(group_id, "direct"),
        proactive_queue_size=reply_queue_size_by_kind(group_id, "proactive"),
        worker_running=not reply_worker_idle(group_id),
    )
    return queued


def dequeue_reply_intent(group_id: int) -> dict[str, Any] | None:
    return reply_queue.dequeue(
        group_id,
        queues=_reply_queue_by_group,
        max_pending_replies=MAX_PENDING_REPLIES,
        proactive_rate_limit_max_replies=PROACTIVE_RATE_LIMIT_MAX_REPLIES,
        max_pending_direct_replies=MAX_PENDING_DIRECT_REPLIES,
    )


def reply_queue_size_by_kind(group_id: int, kind: str) -> int:
    return reply_queue.size_by_kind(
        group_id,
        kind,
        queues=_reply_queue_by_group,
        max_pending_replies=MAX_PENDING_REPLIES,
        proactive_rate_limit_max_replies=PROACTIVE_RATE_LIMIT_MAX_REPLIES,
        max_pending_direct_replies=MAX_PENDING_DIRECT_REPLIES,
    )


def reply_queue_size(group_id: int) -> int:
    return reply_queue.size(
        group_id,
        queues=_reply_queue_by_group,
        max_pending_replies=MAX_PENDING_REPLIES,
        proactive_rate_limit_max_replies=PROACTIVE_RATE_LIMIT_MAX_REPLIES,
        max_pending_direct_replies=MAX_PENDING_DIRECT_REPLIES,
    )


def load_text_file(path: Path, fallback: str) -> str:
    def on_error(exc: Exception, error_path: Path) -> None:
        log({"type": "profile_file_error", "path": str(error_path), "error": type(exc).__name__, "message": str(exc)})

    return group_files.load_text_file(path, fallback, on_error=on_error)


def field_values_from_section(section: str, field: str) -> list[str]:
    return profiles.field_values_from_section(section, field)


def reply_segments(event: dict[str, Any]) -> list[dict[str, Any]]:
    return onebot.reply_segments(event)


def reply_segment_sender_qq(data: dict[str, Any]) -> str:
    return onebot.reply_segment_sender_qq(data)


def reply_segment_message_id(data: dict[str, Any]) -> str:
    return onebot.reply_segment_message_id(data)


def recent_message_by_id(group_id: int | None, message_id: str) -> dict[str, Any] | None:
    if group_id is None or not message_id:
        return None
    for item in reversed(recent_messages_for_group(group_id)):
        ids = [item.get("message_id"), item.get("id"), item.get("message_seq"), item.get("real_id")]
        if any(str(x) == str(message_id) for x in ids if x not in (None, "")):
            return item
    return None


def is_reply_to_me(event: dict[str, Any]) -> bool:
    return onebot.is_reply_to_me(event, bot_qq=BOT_QQ)


def should_trigger_direct_reply(event: dict[str, Any]) -> bool:
    return is_at_me(event) or is_reply_to_me(event) or is_name_mention(event)


def reply_context_from_event(event: dict[str, Any]) -> str:
    contexts: list[str] = []
    reply_to_bot = is_reply_to_me(event)
    group_id = group_id_from_event(event)
    for seg in reply_segments(event):
        data = seg.get("data") or {}
        text = str(data.get("text") or data.get("message") or data.get("content") or "").strip()
        mid = reply_segment_message_id(data)
        qq = reply_segment_sender_qq(data)
        prefix = "正在回复机器人上一条发言" if reply_to_bot and qq == str(event.get("self_id") or BOT_QQ or "") else "引用消息"
        if not text and mid:
            cached = recent_message_by_id(group_id, mid)
            if cached:
                speaker = str(cached.get("name") or cached.get("user_id") or "引用对象")
                text = f"{speaker}：{cached.get('text') or ''}".strip()
        if text:
            contexts.append(f"{prefix}：{text[:CONTEXT_MAX_CHARS_PER_MESSAGE]}")
        elif mid:
            contexts.append(f"{prefix}ID: {mid}（未缓存到原文；结合当前消息和最近上下文判断，不要要求对方重发）")
        else:
            contexts.append(f"{prefix}（未缓存到原文；结合当前消息和最近上下文判断，不要要求对方重发）")
    if reply_to_bot:
        contexts.append("用户这条消息是在接机器人上一条回答，视作连续对话，请优先参考上面的被回复内容理解语气和指代。")
    return "\n".join(f"- {x}" for x in contexts) if contexts else "（当前消息没有引用/回复上下文）"


def save_context_cache() -> None:
    if not CONTEXT_CACHE_FILE:
        return
    if os.getenv("PYTEST_CURRENT_TEST") and CONTEXT_CACHE_FILE == BASE_DIR / "logs" / "recent_context.jsonl":
        return
    CONTEXT_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with CONTEXT_CACHE_FILE.open("w", encoding="utf-8") as f:
        for group_id, summaries in _context_summaries_by_group.items():
            for summary in list(summaries)[-CONTEXT_SUMMARY_MAX:]:
                f.write(json.dumps({"kind": "summary", "group_id": group_id, "text": summary}, ensure_ascii=False) + "\n")
        for group_id, messages in _recent_messages_by_group.items():
            for item in list(messages)[-CONTEXT_MAX_MESSAGES:]:
                row = dict(item)
                if row.get("ocr_text_nonpersistent") and not OCR_PERSIST_TEXT_IN_CONTEXT:
                    row["text"] = row.get("text_without_ocr") or row.get("text")
                row.pop("text_without_ocr", None)
                row.pop("ocr_text_nonpersistent", None)
                row.pop("media_refs", None)
                row["kind"] = "recent"
                row["group_id"] = group_id
                f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_context_cache() -> None:
    try:
        lines = CONTEXT_CACHE_FILE.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return
    except Exception as exc:
        log({"type": "context_cache_error", "error": type(exc).__name__, "message": str(exc)})
        return
    _recent_messages.clear()
    _recent_messages_by_group.clear()
    _context_summaries_by_group.clear()
    recent_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    for line in lines:
        try:
            item = json.loads(line)
        except Exception:
            continue
        if not isinstance(item, dict):
            continue
        kind = item.get("kind") or "recent"
        if kind == "summary" and item.get("text"):
            summary_rows.append(item)
        elif {"user_id", "name", "text"} <= set(item):
            recent_rows.append(item)
    for item in summary_rows[-CONTEXT_SUMMARY_MAX * max(1, len(ALLOWED_GROUP_IDS)):]:
        group_id = int(item.get("group_id") or TARGET_GROUP_ID)
        context_summaries_for_group(group_id).append(str(item.get("text") or "")[:CONTEXT_SUMMARY_MAX_CHARS])
    for item in recent_rows[-CONTEXT_MAX_MESSAGES * max(1, len(ALLOWED_GROUP_IDS)):]:
        group_id = int(item.get("group_id") or TARGET_GROUP_ID)
        clean = {"user_id": item.get("user_id"), "name": item.get("name"), "text": item.get("text")}
        for key in ("message_id", "id", "msg_id", "message_seq", "real_id"):
            if item.get(key) not in (None, ""):
                clean[key] = item.get(key)
        if item.get("role"):
            clean["role"] = item.get("role")
        recent_messages_for_group(group_id).append(clean)
        if group_id == TARGET_GROUP_ID:
            _recent_messages.append(clean)
    for group_id, messages in _recent_messages_by_group.items():
        metrics.set_context_messages(group_id, len(messages))


def cooldown_key(group_id: Any, user_id: Any) -> str:
    return user_controls.cooldown_key(group_id, user_id)


def should_rate_limit(group_id: Any, user_id: Any, now: float | None = None) -> tuple[bool, str]:
    return user_controls.should_rate_limit(
        group_id,
        user_id,
        replied_at=_last_user_reply_at,
        cooldown_seconds=USER_COOLDOWN_SECONDS,
        now=now,
    )


def mark_user_replied(group_id: Any, user_id: Any, now: float | None = None) -> None:
    user_controls.mark_user_replied(group_id, user_id, replied_at=_last_user_reply_at, now=now)


def should_rate_limit_direct_enqueue(group_id: Any, user_id: Any) -> tuple[bool, str]:
    return False, ""


def should_skip_unclear_mention(user_text: str) -> bool:
    return user_controls.should_skip_unclear_mention(user_text)


def apply_punctuation_style(text: str) -> str:
    return text_utils.apply_punctuation_style(text, enabled=PUNCTUATION_STYLE_ENABLED)


def normalize_reply_linebreaks(text: str) -> str:
    """QQ 群短回复不保留段落空行，避免模型把三句话拆成多段气泡感。"""
    return text_utils.normalize_reply_linebreaks(text)


def finalize_reply(text: str) -> str:
    return text_utils.finalize_reply(
        text,
        max_chars=MAX_REPLY_CHARS,
        empty_reply=pick_template("empty_reply", text or ""),
        punctuation_style_enabled=PUNCTUATION_STYLE_ENABLED,
    )


def prepare_reply_text(text: str) -> str:
    """清理回复文本但不做长度截断；需要硬限制的调用方自行压缩。"""
    return text_utils.prepare_reply_text(text, punctuation_style_enabled=PUNCTUATION_STYLE_ENABLED)


def style_hint_for(event: dict[str, Any]) -> str:
    return user_controls.style_hint_for(event, style_hints=STYLE_HINTS, message_to_text_fn=message_to_text)


def needs_web_search(text: str) -> bool:
    return search.needs_web_search(text, web_search_enabled=WEB_SEARCH_ENABLED)


def current_date_context(now: datetime | None = None) -> str:
    return search.current_date_context(now)


def normalize_search_query(query: str) -> str:
    return search.normalize_search_query(query)


def _compact_search_terms(text: str, limit: int = 160) -> str:
    return search.compact_search_terms(text, limit=limit)


def _salient_latin_terms(text: str) -> list[str]:
    return search.salient_latin_terms(text)


def plan_search_queries(query: str) -> list[str]:
    return search.plan_search_queries(query)


def candidate_urls_from_query(q: str) -> list[str]:
    return search.candidate_urls_from_query(q)


def jina_url_for_source(url: str) -> str:
    return search.jina_url_for_source(url)


def search_urls_for_query(q: str) -> list[str]:
    return search.search_urls_for_query(q)


def usable_search_output(text: str) -> bool:
    return search.usable_search_output(text)


def verify_search_evidence(query: str, normalized_query: str, evidence: str, date_context: str) -> str:
    start = runtime_now()
    verify_prompt = search_runtime.build_curl_verify_prompt(
        query=query,
        normalized_query=normalized_query,
        evidence=evidence,
        date_context=date_context,
    )
    p = subprocess.run(build_hermes_cmd(verify_prompt, use_group_session=False, model=WEB_SEARCH_MODEL, provider=WEB_SEARCH_PROVIDER), text=True, capture_output=True, timeout=WEB_SEARCH_TIMEOUT, cwd=str(BASE_DIR))
    emit_perf_stat(
        "web_search_verify_result",
        backend="curl",
        duration_ms=runtime_elapsed_ms(start),
        ok=p.returncode == 0,
        returncode=p.returncode,
        evidence_len=len(evidence or ""),
        output_len=len(p.stdout or ""),
        model_configured=bool(WEB_SEARCH_MODEL),
        provider_configured=bool(WEB_SEARCH_PROVIDER),
    )
    if p.returncode != 0:
        log({"type": "web_search_verify_error", "returncode": p.returncode, "stdout": (p.stdout or "")[-800:], "stderr": (p.stderr or "")[-800:]})
        return ""
    return strip_session_footer(p.stdout or "").strip()


def fetch_search_url(url: str) -> subprocess.CompletedProcess[str]:
    start = runtime_now()
    p = subprocess.run(
        ["curl", "-L", "-sS", "--max-time", str(int(WEB_SEARCH_HTTP_TIMEOUT)), url],
        text=True,
        capture_output=True,
        timeout=WEB_SEARCH_HTTP_TIMEOUT + 2,
        cwd=str(BASE_DIR),
    )
    emit_perf_stat(
        "web_search_fetch_result",
        backend="curl",
        duration_ms=runtime_elapsed_ms(start),
        ok=p.returncode == 0,
        returncode=p.returncode,
        output_len=len(p.stdout or ""),
    )
    return p


def run_curl_search(query: str) -> str:
    return search_runtime.run_curl_search(
        query,
        normalize_query_fn=normalize_search_query,
        current_date_context_fn=current_date_context,
        plan_search_queries_fn=plan_search_queries,
        search_urls_for_query_fn=search_urls_for_query,
        fetch_url_fn=fetch_search_url,
        usable_search_output_fn=usable_search_output,
        verify_search_evidence_fn=verify_search_evidence,
        log_fn=log,
        max_successful_fetches=WEB_SEARCH_MAX_SUCCESSFUL_FETCHES,
    )


def run_llm_web_search(query: str, normalized_query: str, date_context: str) -> str:
    search_prompt = search_runtime.build_llm_search_prompt(
        query=query,
        normalized_query=normalized_query,
        date_context=date_context,
    )
    cmd = build_hermes_cmd(search_prompt, use_group_session=False, model=WEB_SEARCH_MODEL, provider=WEB_SEARCH_PROVIDER)
    log({"type": "web_search_start", "query": query[:200]})
    try:
        p = subprocess.run(cmd, text=True, capture_output=True, timeout=WEB_SEARCH_TIMEOUT, cwd=str(BASE_DIR))
    except Exception as exc:
        log({"type": "web_search_error", "error": type(exc).__name__, "message": str(exc)})
        return pick_template("web_search_failed", normalized_query)
    if p.returncode != 0:
        log({"type": "web_search_error", "returncode": p.returncode, "stderr": p.stderr[-800:]})
        return pick_template("web_search_failed", normalized_query)
    return search_runtime.finalize_llm_search_result(
        p.stdout or "",
        normalized_query=normalized_query,
        max_chars=WEB_SEARCH_MAX_CHARS,
        empty_reply_fn=lambda query_text: pick_template("web_search_empty", query_text),
    )


def run_web_search(query: str) -> str:
    start = runtime_now()
    result = search_runtime.run_web_search(
        query,
        web_search_enabled=WEB_SEARCH_ENABLED,
        web_search_backend=WEB_SEARCH_BACKEND,
        normalize_query_fn=normalize_search_query,
        current_date_context_fn=current_date_context,
        run_curl_search_fn=run_curl_search,
        run_llm_search_fn=run_llm_web_search,
        pick_template_fn=pick_template,
        log_fn=log,
        max_chars=WEB_SEARCH_MAX_CHARS,
    )
    emit_perf_stat(
        "web_search_result",
        backend=WEB_SEARCH_BACKEND,
        duration_ms=runtime_elapsed_ms(start),
        ok=bool(result),
        query_len=len(query or ""),
        query_len_bucket=runtime_stats.length_bucket(len(query or "")),
        result_len=len(result or ""),
    )
    return result


def search_command_fallback_reply(query: str) -> str:
    return search.search_command_fallback_reply(
        query,
        no_match_reply=pick_template("web_search_no_match", re.sub(r"\s+", " ", query or "").strip()),
    )


def run_search_command_search(query: str, group_id: int | None = None) -> str:
    clean = re.sub(r"\s+", " ", query or "").strip()
    if not clean:
        return "用法：/search 你要查的内容"
    search_input = build_search_command_prompt(clean, group_id) if WEB_SEARCH_BACKEND == "llm" else clean
    result = run_web_search(search_input)
    if not result:
        return search_command_fallback_reply(clean)
    if result in REPLY_TEMPLATES.get("web_search_no_match", []) or result in REPLY_TEMPLATES.get("web_search_empty", []):
        return search_command_fallback_reply(clean)
    if result in REPLY_TEMPLATES.get("web_search_failed", []):
        return "搜索刚才跑挂了 稍后再试或换个关键词"
    return result[:WEB_SEARCH_MAX_CHARS]


def build_search_query(text: str, event: dict[str, Any] | None = None, group_id: int | None = None) -> str:
    base = re.sub(r"\s+", " ", text or "").strip()
    if event is None and group_id is None:
        return base
    gid = group_id if group_id is not None else group_id_from_event(event or {})
    parts = [f"原问题：{base}"]
    if event is not None:
        reply_context = reply_context_from_event(event)
        if reply_context and "没有引用/回复上下文" not in reply_context:
            parts.append(f"被回复/引用消息：{reply_context[:500]}")
    recent_items = list(recent_messages_for_group(gid or TARGET_GROUP_ID))[-5:]
    recent_lines = []
    for item in recent_items:
        role = str(item.get("role") or "").strip()
        if "机器人" in role:
            continue
        name = str(item.get("name") or item.get("user_id") or "群友")
        msg = re.sub(r"\s+", " ", str(item.get("text") or "")).strip()
        if msg and msg != base and msg not in base:
            recent_lines.append(f"{name}：{msg[:120]}")
    if recent_lines:
        parts.append("群聊近期上下文：" + " / ".join(recent_lines))
    return "\n".join(parts)[:1000]


def web_search_context_for_text(text: str, event: dict[str, Any] | None = None, group_id: int | None = None) -> str:
    if not needs_web_search(text):
        return "（当前消息不需要联网搜索。）"
    date_context = current_date_context()
    search_query = build_search_query(text, event=event, group_id=group_id)
    result = run_web_search(search_query)
    return f"{date_context}\n联网搜索结果：\n{result}\n\n如果联网搜索结果不足或冲突，请在回复中明确说不确定，不要把传闻当定论；不要用去年、旧赛季或不匹配赛事的结果代替当前问题。"


def build_prompt_with_search_flag(event: dict[str, Any], user_text: str) -> tuple[str, bool]:
    return build_prompt(event, user_text), needs_web_search(user_text)


def build_proactive_prompt_with_search_flag(event: dict[str, Any], reasons: list[str]) -> tuple[str, bool]:
    text = message_to_text(event.get("message"))
    return build_proactive_prompt(event, reasons), needs_web_search(text)


async def maybe_send_web_search_notice(group_id: int, search_needed: bool) -> bool:
    if not WEB_SEARCH_NOTICE_ENABLED or not search_needed:
        return False
    data = await send_group_msg(group_id, WEB_SEARCH_NOTICE_TEXT)
    if send_group_msg_succeeded(data):
        remember_bot_reply(group_id, WEB_SEARCH_NOTICE_TEXT)
        return True
    log({"type": "web_search_notice_send_failed", "group_id": group_id, "response": data})
    return False


def extract_person_profile(user_id: Any, nickname: str, people_file: Path | None = None) -> str:
    if people_file is None:
        people_file = PEOPLE_FILE
    return profiles.extract_person_profile(
        user_id,
        nickname,
        people_text=load_text_file(people_file, ""),
    )


def group_people_file_for_group(group_id: int) -> Path | None:
    return group_files.group_people_file_for_group(
        group_id,
        group_config_dir=GROUP_CONFIG_DIR,
        target_group_id=TARGET_GROUP_ID,
        people_file=PEOPLE_FILE,
        default_people_file=DEFAULT_PEOPLE_FILE,
        default_group_config_dir=DEFAULT_GROUP_CONFIG_DIR,
    )


def _people_sections(path: Path | None = None) -> list[str]:
    return profiles.people_sections(path, default_path=PEOPLE_FILE, load_text_file_fn=load_text_file)


def primary_alias_from_section(section: str) -> str:
    return profiles.primary_alias_from_section(section)


def profile_display_name_by_qq(qq: str) -> str:
    return profiles.profile_display_name_by_qq(qq, _people_sections())


def mentioned_people_labels(event: dict[str, Any]) -> list[str]:
    return profiles.mentioned_people_labels(
        event,
        self_id=str(event.get("self_id") or BOT_QQ or ""),
        display_name_by_qq_fn=profile_display_name_by_qq,
    )


def extract_profiles_for_query(event: dict[str, Any], user_text: str, people_file: Path | None = None) -> str:
    """提取当前问题涉及的人：被 @ 的 QQ，以及文本里出现的昵称。"""
    return profiles.extract_profiles_for_query(
        event,
        user_text,
        sections=_people_sections(people_file),
        self_id=str(event.get("self_id") or BOT_QQ or ""),
    )


def keyword_related_profiles(user_text: str, people_file: Path | None = None) -> str:
    """根据问题里的关键词，从 people.md 找可能相关的群友资料。"""
    return profiles.keyword_related_profiles(
        user_text,
        sections=_people_sections(people_file),
        min_keyword_len=RELATED_PROFILE_MIN_KEYWORD_LEN,
        max_matches=RELATED_PROFILE_MAX_MATCHES,
    )


def summary_source_line(message: dict[str, Any]) -> str:
    role = str(message.get("role") or "").strip()
    role_note = f"，{role}" if role else ""
    return f"- {message.get('name')}（QQ: {message.get('user_id')}{role_note}）：{message.get('text')}"


def summarization_prompt(group_id: int, messages: list[dict[str, Any]]) -> str:
    lines = "\n".join(summary_source_line(m) for m in messages)
    return f"""请把下面 QQ 群聊天片段压缩成一句中文上下文摘要，用于之后机器人理解前情。
要求：
- 只保留话题、关键事实、群友态度或待回答线索。
- 如果包含 Esti/机器人发言，只总结它在回应什么或造成了什么连续对话效果，不要保留机器人旧笑话、旧措辞或重复口头禅。
- 不要把已经过去的旧词写得像当前仍在继续的话题；除非群友明确还在接它。
- 不要加入评价，不要编造。
- 不超过 {CONTEXT_SUMMARY_MAX_CHARS} 字。
- 直接输出一句话，不要标题。

群号：{group_id}
聊天片段：
{lines}"""


def summarize_context_messages(group_id: int, messages: list[dict[str, Any]]) -> str:
    if not messages:
        return ""
    try:
        summary = run_hermes(summarization_prompt(group_id, messages))
    except Exception as exc:
        log({"type": "context_summary_error", "group_id": group_id, "error": type(exc).__name__, "message": str(exc)})
        summary = "；".join(str(m.get("text") or "") for m in messages)
    return finalize_summary(summary)


def finalize_summary(text: str) -> str:
    return context_store.finalize_summary(
        text,
        max_chars=CONTEXT_SUMMARY_MAX_CHARS,
        is_low_value_fn=is_low_value_summary,
    )


def summary_dedupe_key(text: str) -> str:
    return context_store.summary_dedupe_key(text)


def summary_ngrams(text: str, n: int = 3) -> set[str]:
    return context_store.summary_ngrams(text, n=n)


def is_low_value_summary(text: str) -> bool:
    return context_store.is_low_value_summary(text)


def visible_context_summaries(group_id: int | None, limit: int = 5) -> list[str]:
    return context_store.visible_context_summaries(
        group_id,
        target_group_id=TARGET_GROUP_ID,
        limit=limit,
        context_summaries_for_group_fn=context_summaries_for_group,
        finalize_summary_fn=finalize_summary,
    )


def compact_context_if_needed(group_id: int) -> None:
    messages = recent_messages_for_group(group_id)
    overflow = len(messages) - CONTEXT_MAX_MESSAGES
    batch_size = max(1, CONTEXT_SUMMARIZE_BATCH)
    if overflow < batch_size:
        return
    take = min(max(batch_size, overflow), len(messages) - CONTEXT_MAX_MESSAGES)
    old_messages = [messages.popleft() for _ in range(take)]
    summary = summarize_context_messages(group_id, old_messages) if CONTEXT_SUMMARIZE_ENABLED else "；".join(str(m.get("text") or "") for m in old_messages)
    summary = finalize_summary(summary)
    if summary:
        context_summaries_for_group(group_id).append(summary)
        log({"type": "context_compacted", "group_id": group_id, "messages": len(old_messages), "summary": summary})
        runtime_stat(
            "context_compaction",
            group_id=group_id,
            messages_compacted=len(old_messages),
            summary_len=len(summary),
            recent_context_count=len(messages),
            summary_count=len(context_summaries_for_group(group_id)),
            ok=True,
        )


def remember_message_item(group_id: int, item: dict[str, Any]) -> None:
    recent_messages_for_group(group_id).append(item)
    compact_context_if_needed(group_id)
    metrics.set_context_messages(group_id, len(recent_messages_for_group(group_id)))
    if group_id == TARGET_GROUP_ID:
        _recent_messages.append(item)
    if CONTEXT_PERSIST_ENABLED:
        save_context_cache()


def remember_bot_reply(group_id: int | None, text: str, self_id: Any = None) -> None:
    if group_id is None or not text:
        return
    bot_id = str(self_id or BOT_QQ or "3975680980")
    remember_message_item(
        group_id,
        context_store.make_bot_reply_item(text, bot_id=bot_id, max_chars=CONTEXT_MAX_CHARS_PER_MESSAGE),
    )


def remember_bot_pending_reply(group_id: int | None, user_text: str, self_id: Any = None) -> None:
    if group_id is None:
        return
    bot_id = str(self_id or BOT_QQ or "3975680980")
    remember_message_item(
        group_id,
        context_store.make_bot_pending_reply_item(user_text, bot_id=bot_id, max_chars=CONTEXT_MAX_CHARS_PER_MESSAGE),
    )


def drop_last_bot_pending_reply(group_id: int | None) -> None:
    changed = context_store.drop_last_bot_pending_reply(
        group_id,
        target_group_id=TARGET_GROUP_ID,
        recent_messages_for_group_fn=recent_messages_for_group,
        legacy_recent_messages=_recent_messages,
    )
    if changed:
        metrics.set_context_messages(group_id, len(recent_messages_for_group(group_id)))
    if changed and CONTEXT_PERSIST_ENABLED:
        save_context_cache()


def replace_last_bot_pending_reply(group_id: int | None, text: str, self_id: Any = None) -> None:
    drop_last_bot_pending_reply(group_id)
    remember_bot_reply(group_id, text, self_id)


def mark_repeated_bot_wording_for_human_message(group_id: int | None, item: dict[str, Any]) -> None:
    text = str(item.get("text") or "")
    if not text or group_id is None:
        return
    if model_output.proactive_output_repeats_recent_bot_wording(text, recent_bot_reply_texts_for_group(group_id, limit=3), min_key_chars=12, min_ngram_chars=16, overlap_threshold=0.88):
        item["annotation"] = "疑似复读/引用 Esti 旧回复，不一定是新事实或新主体"


def collect_self_learning_sample_for_item(group_id: int, item: dict[str, Any]) -> None:
    learning_text = item.get("text_without_ocr") or item.get("text") or ""
    text_for_command_check = str(learning_text or "")
    is_command = (
        is_context_command(text_for_command_check)
        or is_search_command(text_for_command_check)
        or is_deepseek_command(text_for_command_check)
        or is_jrrp_command(text_for_command_check)
    )
    self_learning.collect_learning_sample(
        group_id,
        learning_text,
        group_config_dir=GROUP_CONFIG_DIR,
        config=SELF_LEARNING_CONFIG,
        is_bot=False,
        is_command=is_command,
        on_error=lambda exc: log({"type": "self_learning_collect_error", "error": type(exc).__name__}),
    )


def remember_message(event: dict[str, Any], text_override: str | None = None, *, text_without_ocr: str | None = None, ocr_text_nonpersistent: bool = False) -> dict[str, Any] | None:
    """记录允许群最近消息，供被 @ 时作为上下文。"""
    if event.get("post_type") != "message" or event.get("message_type") != "group":
        return None
    if not is_allowed_group(event):
        return None
    text = text_override if text_override is not None else message_to_text(event.get("message"), include_at=False)
    if not text:
        text = "（非文本消息）"
    text = text[:CONTEXT_MAX_CHARS_PER_MESSAGE]
    group_id = group_id_from_event(event)
    if group_id is None:
        return None
    item = {
        "user_id": event.get("user_id"),
        "name": _sender_name(event),
        "text": text,
    }
    media_refs = media.extract_media_refs(event.get("message"), max_refs=OCR_MAX_IMAGES_PER_MESSAGE)
    if media_refs:
        item["media_refs"] = media_refs
    if text_without_ocr is not None:
        item["text_without_ocr"] = text_without_ocr[:CONTEXT_MAX_CHARS_PER_MESSAGE]
    if ocr_text_nonpersistent:
        item["ocr_text_nonpersistent"] = True
    for key, value in message_identity_from_event(event).items():
        item[key] = value
    mark_repeated_bot_wording_for_human_message(group_id, item)
    remember_message_item(group_id, item)
    collect_self_learning_sample_for_item(group_id, item)
    return item


def format_context_summaries(group_id: int | None = None) -> str:
    return context_store.format_context_summaries(
        group_id,
        target_group_id=TARGET_GROUP_ID,
        summary_max=CONTEXT_SUMMARY_MAX,
        visible_context_summaries_fn=visible_context_summaries,
    )


def _format_context_item(idx: int, item: dict[str, Any], weight: str | None = None) -> list[str]:
    return context_store.format_context_item(idx, item, weight)


def format_recent_context(group_id: int | None = None) -> str:
    """格式化指定群最近群聊上下文；为空时给出明确说明。"""
    return context_store.format_recent_context(
        group_id,
        target_group_id=TARGET_GROUP_ID,
        context_max_messages=CONTEXT_MAX_MESSAGES,
        recent_messages_for_group_fn=recent_messages_for_group,
        legacy_recent_messages=_recent_messages,
    )


def format_proactive_recent_context(group_id: int | None = None) -> str:
    """主动发言专用上下文：近几句高权重，旧消息衰减为背景，机器人旧回复不提供关键词。"""
    return context_store.format_proactive_recent_context(
        group_id,
        target_group_id=TARGET_GROUP_ID,
        focus_messages=PROACTIVE_CONTEXT_FOCUS_MESSAGES,
        memory_messages=PROACTIVE_CONTEXT_MEMORY_MESSAGES,
        recent_messages_for_group_fn=recent_messages_for_group,
        legacy_recent_messages=_recent_messages,
    )


def is_jrrp_command(text: str) -> bool:
    """今日人品：仅当整条文本严格为 jrrp 时触发，聊天句子里的 jrrp 不触发。"""
    return jrrp.is_jrrp_command(text)


def load_jrrp_state() -> dict[str, Any]:
    return jrrp.load_json_dict(
        JRRP_STATE_FILE,
        on_error=lambda exc: log({"type": "jrrp_state_load_error", "error": type(exc).__name__, "message": str(exc)}),
    )


def save_jrrp_state(state: dict[str, Any]) -> None:
    jrrp.save_json_dict(
        JRRP_STATE_FILE,
        state,
        on_error=lambda exc: log({"type": "jrrp_state_save_error", "error": type(exc).__name__, "message": str(exc)}),
    )


def load_jrrp_results() -> dict[str, Any]:
    return jrrp.load_json_dict(
        JRRP_RESULTS_FILE,
        on_error=lambda exc: log({"type": "jrrp_results_load_error", "error": type(exc).__name__, "message": str(exc)}),
    )


def _jrrp_pick(options: Any, seed: str, salt: str) -> str:
    return jrrp.pick_option(options, seed, salt)


def jrrp_level_for_score(results: dict[str, Any], score: int) -> dict[str, Any]:
    return jrrp.level_for_score(results, score)


def build_jrrp_reply(user_id: Any, nickname: str = "", now: datetime | None = None) -> tuple[str, bool]:
    return jrrp.build_jrrp_reply(
        user_id,
        nickname,
        now,
        load_state_fn=load_jrrp_state,
        save_state_fn=save_jrrp_state,
        load_results_fn=load_jrrp_results,
    )


def _normalized_command_text(text: str) -> str:
    return command_utils.normalized_command_text(text)


def _has_slash_command(text: str, command: str) -> bool:
    return command_utils.has_slash_command(text, command)


def _slash_command_query(text: str, command: str) -> str:
    return command_utils.slash_command_query(text, command)


def is_context_command(text: str) -> bool:
    """用户显式请求查看本群本地上下文缓存。"""
    return command_utils.is_context_command(text)


def is_search_command(text: str) -> bool:
    """用户显式请求联网搜索；普通聊天不自动搜索。"""
    return command_utils.is_search_command(text)


def search_command_query(text: str) -> str:
    return command_utils.search_command_query(text)


def is_deepseek_command(text: str) -> bool:
    """/deepseek 是独立深度搜索命令名，与 DeepSeek 模型无关。"""
    return command_utils.is_deepseek_command(text)


def deepseek_command_query(text: str) -> str:
    return command_utils.deepseek_command_query(text)


def is_context_command_bot_output(item: dict[str, Any]) -> bool:
    return commands.is_context_command_bot_output(item, reply_prefix=REPLY_PREFIX)


def _clip_context_line(text: Any, limit: int = 80) -> str:
    return commands.clip_context_line(text, limit)


def _append_context_line_with_budget(lines: list[str], line: str, budget: int) -> bool:
    return commands.append_context_line_with_budget(lines, line, budget)


def build_context_command_reply(group_id: int | None) -> str:
    """生成 /context 命令回复：只展示当前群本地摘要和最近上下文，不调用 LLM。"""
    gid = group_id if group_id is not None else TARGET_GROUP_ID
    return commands.build_context_command_reply(
        summaries=visible_context_summaries(gid, limit=3),
        messages=list(recent_messages_for_group(gid)),
        fallback_messages=list(_recent_messages),
        target_group=gid == TARGET_GROUP_ID,
        max_reply_chars=MAX_REPLY_CHARS,
        reply_prefix=REPLY_PREFIX,
        is_context_command_fn=is_context_command,
    )


def parse_hhmm(value: str) -> tuple[int, int]:
    return proactive.parse_hhmm(value)


def is_night_time(now: float | None = None) -> bool:
    return proactive.is_night_time(
        now,
        night_start=PROACTIVE_NIGHT_START,
        night_end=PROACTIVE_NIGHT_END,
    )


def decay_proactive_score(state: dict[str, Any], now: float) -> None:
    proactive.decay_score(state, now=now, decay_per_minute=PROACTIVE_DECAY_PER_MINUTE)


def proactive_add_recent_activity(group_id: int, event: dict[str, Any], text: str, now: float) -> list[dict[str, Any]]:
    return proactive.add_recent_activity(
        recent_activity_for_group(group_id),
        event=event,
        text=text,
        now=now,
        burst_window_seconds=PROACTIVE_BURST_WINDOW_SECONDS,
    )


def proactive_message_score(text: str) -> tuple[float, list[str]]:
    return proactive.message_score(
        text,
        name_triggers=PROACTIVE_NAME_TRIGGERS,
        topic_keywords=PROACTIVE_TOPIC_KEYWORDS,
        light_keywords=PROACTIVE_LIGHT_KEYWORDS,
        score_name_trigger=PROACTIVE_SCORE_NAME_TRIGGER,
        score_topic_keyword=PROACTIVE_SCORE_TOPIC_KEYWORD,
        score_light_keyword=PROACTIVE_SCORE_LIGHT_KEYWORD,
        score_question=PROACTIVE_SCORE_QUESTION,
        score_open_question=PROACTIVE_SCORE_OPEN_QUESTION,
    )


def can_send_proactive_now(group_id: int, now: float | None = None) -> str:
    return proactive.can_send_now(
        proactive_reply_times_for_group(group_id),
        now=time.time() if now is None else now,
        window_seconds=PROACTIVE_RATE_LIMIT_WINDOW_SECONDS,
        max_replies=PROACTIVE_RATE_LIMIT_MAX_REPLIES,
    )


def proactive_block_reason(state: dict[str, Any], now: float, group_id: int | None = None) -> str:
    rate_block = can_send_proactive_now(group_id, now) if group_id is not None else ""
    return proactive.block_reason(
        state,
        now=now,
        rate_block=rate_block,
        group_cooldown_seconds=PROACTIVE_GROUP_COOLDOWN_SECONDS,
        daily_limit=PROACTIVE_DAILY_LIMIT_PER_GROUP,
    )


def update_proactive_score(event: dict[str, Any], now: float | None = None) -> dict[str, Any]:
    now = time.time() if now is None else now
    group_id = group_id_from_event(event)
    if not PROACTIVE_ENABLED or group_id is None or not is_allowed_group(event) or is_at_me(event):
        return {"score": 0.0, "should_trigger": False, "reasons": [], "blocked": "disabled_or_ineligible"}
    text = message_to_text(event.get("message"))
    state = proactive_state_for_group(group_id)
    decay_proactive_score(state, now)
    if matching.contains_any_phrase(text, PROACTIVE_SENSITIVE_KEYWORDS):
        state["score"] = max(0.0, float(state.get("score", 0.0)) - 5.0)
        state["sensitive_until"] = now + PROACTIVE_SENSITIVE_COOLDOWN_SECONDS
        return {"score": state["score"], "should_trigger": False, "reasons": ["sensitive"], "blocked": "sensitive"}

    activity = proactive_add_recent_activity(group_id, event, text, now)
    add, reasons = proactive_message_score(text)
    return proactive.update_score_core(
        state,
        activity=activity,
        base_add=add,
        reasons=reasons,
        now=now,
        blocked=proactive_block_reason(state, now, group_id),
        burst_message_threshold=PROACTIVE_BURST_MESSAGE_THRESHOLD,
        burst_user_threshold=PROACTIVE_BURST_USER_THRESHOLD,
        score_burst=PROACTIVE_SCORE_BURST,
        score_multi_user=PROACTIVE_SCORE_MULTI_USER,
        night_score_multiplier=PROACTIVE_NIGHT_SCORE_MULTIPLIER,
        is_night=is_night_time(now),
        threshold=PROACTIVE_TRIGGER_THRESHOLDS_BY_GROUP.get(group_id, PROACTIVE_TRIGGER_THRESHOLD),
    )


def mark_proactive_replied(group_id: int, now: float | None = None) -> None:
    proactive.mark_replied(
        proactive_state_for_group(group_id),
        proactive_reply_times_for_group(group_id),
        now=time.time() if now is None else now,
    )


def mark_proactive_skipped(group_id: int) -> None:
    proactive.mark_skipped(proactive_state_for_group(group_id))


def event_dedupe_key(event: dict[str, Any]) -> str:
    return events.event_dedupe_key(event, message_to_text_fn=message_to_text)


def mark_event_seen(event: dict[str, Any]) -> bool:
    return events.mark_event_seen(
        event,
        keys=_processed_event_keys,
        key_set=_processed_event_key_set,
        message_to_text_fn=message_to_text,
    )


def is_at_me(event: dict[str, Any]) -> bool:
    return onebot.is_at_me(event, bot_qq=BOT_QQ)


def self_learning_context_for_prompt(group_id: int | None = None) -> str:
    return self_learning.learning_context_for_prompt(
        group_id,
        target_group_id=TARGET_GROUP_ID,
        group_config_dir=GROUP_CONFIG_DIR,
        config=SELF_LEARNING_CONFIG,
        on_error=lambda exc: log({"type": "self_learning_prompt_error", "error": type(exc).__name__}),
    )


def prompt_render_diagnostics(kind: str, group_id: int | None, rendered: Any) -> dict[str, Any]:
    sections = []
    truncated_sections = []
    for section in getattr(rendered, "sections", ()):
        item = {
            "key": section.key,
            "source": section.source,
            "priority": section.priority,
            "original_char_count": section.original_char_count,
            "rendered_char_count": section.rendered_char_count,
            "budget_chars": section.budget_chars,
            "truncated": section.truncated,
        }
        sections.append(item)
        if section.truncated:
            truncated_sections.append(section.key)
    return {
        "type": "prompt_rendered",
        "kind": kind,
        "group_id": group_id,
        "char_count": getattr(rendered, "char_count", len(getattr(rendered, "text", ""))),
        "section_count": len(sections),
        "truncated_sections": truncated_sections,
        "sections": sections,
    }


def log_prompt_render(kind: str, group_id: int | None, rendered: Any) -> None:
    log(prompt_render_diagnostics(kind, group_id, rendered))


def build_prompt(event: dict[str, Any], user_text: str, media_context: str = "（当前消息没有图片识别结果）") -> str:
    nick = _sender_name(event)
    user_id = event.get("user_id")
    group_id = group_id_from_event(event)
    clipped = user_text[:MAX_PROMPT_CHARS]
    people_file = group_people_file_for_prompt(group_id)
    rendered = commands.build_rendered_chat_prompt(
        group_id=group_id,
        date_context=current_date_context(),
        context_summaries=format_context_summaries(group_id),
        recent_context=format_recent_context(group_id),
        reply_context=reply_context_from_event(event),
        reply_to_bot_note="用户正在回复机器人上一条发言；把它视作连续对话，优先承接机器人上一条回答和用户这句短回复。" if is_reply_to_me(event) else "（不是回复机器人消息）",
        nick=nick,
        user_id=user_id,
        mentioned_labels="、".join(mentioned_people_labels(event)) or "（当前消息没有额外 @ 其他人）",
        user_text=clipped,
        person_profile=extract_person_profile(user_id, nick, people_file) if people_file else "（本群没有配置群友资料）",
        mentioned_profiles=extract_profiles_for_query(event, clipped, people_file) if people_file else "（本群没有配置被询问对象资料）",
        related_profiles=keyword_related_profiles(clipped, people_file) if people_file else "（本群没有配置相关群友资料）",
        persona=normal_chat_persona_bundle_for_prompt(group_id),
        max_prompt_chars=MAX_PROMPT_CHARS,
        style_hint=style_hint_for(event),
        media_context=media_context,
        learning_context=self_learning_context_for_prompt(group_id),
    )
    log_prompt_render("direct", group_id, rendered)
    return rendered.text


def build_proactive_prompt(event: dict[str, Any], reasons: list[str]) -> str:
    group_id = group_id_from_event(event)
    rendered = commands.build_rendered_proactive_prompt(
        group_id=group_id,
        date_context=current_date_context(),
        context_summaries=format_context_summaries(group_id),
        recent_context=format_proactive_recent_context(group_id),
        persona=normal_chat_persona_bundle_for_prompt(group_id),
        reasons=reasons,
    )
    log_prompt_render("proactive", group_id, rendered)
    return rendered.text


def ocr_enabled_for_route(route: str) -> bool:
    if not OCR_ENABLED:
        return False
    mode = str(OCR_TRIGGER_MODE or "direct_only").strip().lower()
    if mode in {"none", "off", "disabled"}:
        return False
    if mode in {"all", "all_allowed_messages"}:
        return route in {"direct", "context", "proactive"}
    if mode in {"direct_and_context", "context_and_direct"}:
        return route in {"direct", "context"}
    if mode == "context_only":
        return route == "context"
    if mode == "direct_and_proactive":
        return route in {"direct", "proactive"}
    return route == "direct"


def build_ocr_provider() -> vision.VisionProvider:
    if str(OCR_PROVIDER or "").strip().lower() not in {"none", "mock"} and not OCR_EXTERNAL_PROVIDER_ALLOWED:
        return vision.NoopVisionProvider()
    return vision.build_vision_provider(
        OCR_PROVIDER,
        hermes_bin=HERMES_BIN,
        model=OCR_MODEL or HERMES_MODEL,
        hermes_provider=HERMES_PROVIDER,
        timeout=OCR_PROVIDER_TIMEOUT,
        max_result_chars=OCR_MAX_RESULT_CHARS,
        cwd=BASE_DIR,
    )


def ocr_cache_key(ref: media.MediaRef) -> str:
    raw = "\0".join([ref.type, ref.file_id, ref.url, ref.summary, ref.sub_type])
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()


def prune_ocr_cache(now: float | None = None) -> None:
    if OCR_CACHE_MAX_ENTRIES <= 0:
        _ocr_result_cache.clear()
        return
    current = time.monotonic() if now is None else now
    if OCR_CACHE_TTL_SECONDS > 0:
        expired = [key for key, (created_at, _) in _ocr_result_cache.items() if current - created_at > OCR_CACHE_TTL_SECONDS]
        for key in expired:
            _ocr_result_cache.pop(key, None)
    overflow = len(_ocr_result_cache) - OCR_CACHE_MAX_ENTRIES
    if overflow > 0:
        oldest = sorted(_ocr_result_cache.items(), key=lambda item: item[1][0])[:overflow]
        for key, _ in oldest:
            _ocr_result_cache.pop(key, None)


def ocr_semaphore() -> asyncio.Semaphore:
    global _ocr_semaphore
    if _ocr_semaphore is None:
        _ocr_semaphore = asyncio.Semaphore(OCR_MAX_CONCURRENT_TASKS)
    return _ocr_semaphore


async def fetch_and_recognize_one_media(ref: media.MediaRef, provider: vision.VisionProvider) -> media.MediaRecognition:
    started = runtime_now()
    provider_name = getattr(provider, "name", OCR_PROVIDER)
    try:
        fetched = await media_fetch.fetch_onebot_image(
            ref,
            onebot_http_url=ONEBOT_HTTP_URL,
            access_token=ONEBOT_ACCESS_TOKEN,
            timeout=OCR_DOWNLOAD_TIMEOUT,
            max_bytes=OCR_MAX_BYTES_PER_IMAGE,
            allowed_content_types=OCR_ALLOWED_CONTENT_TYPES,
        )
    except Exception as exc:
        log({"type": "ocr_fetch_error", "media": media_fetch.media_ref_log_summary(ref, include_url=OCR_LOG_IMAGE_URLS), "error": type(exc).__name__})
        emit_perf_stat("ocr_fetch_result", status="exception", ok=False, error=type(exc).__name__, duration_ms=runtime_elapsed_ms(started), provider=provider_name)
        return media.MediaRecognition(index=ref.index, type=ref.type, status="error", provider=provider_name, error=type(exc).__name__)

    fetch_ms = runtime_elapsed_ms(started)
    log({
        "type": "media_fetch_done",
        "media": media_fetch.media_ref_log_summary(ref, include_url=OCR_LOG_IMAGE_URLS),
        "status": fetched.status,
        "error": fetched.error,
        "content_type": fetched.content_type,
        "bytes": len(fetched.content),
        "duration_ms": fetch_ms,
    })
    emit_perf_stat(
        "ocr_fetch_result",
        status=fetched.status,
        ok=fetched.status == "ok",
        error=fetched.error or "",
        content_type=fetched.content_type,
        bytes_len=len(fetched.content),
        duration_ms=fetch_ms,
        provider=provider_name,
    )
    if fetched.status != "ok":
        return media.MediaRecognition(index=ref.index, type=ref.type, status="error", provider=provider_name, error=fetched.error or fetched.status)

    provider_start = runtime_now()
    recognized = await asyncio.to_thread(provider.recognize_image, fetched, prompt=OCR_IMAGE_PROMPT)
    provider_ms = runtime_elapsed_ms(provider_start)
    log_event = {
        "type": "ocr_done" if recognized.status == "ok" else "ocr_error",
        "media": media_fetch.media_ref_log_summary(ref, include_url=OCR_LOG_IMAGE_URLS),
        "provider": recognized.provider,
        "status": recognized.status,
        "result_chars": len(recognized.text or recognized.description or ""),
        "error": recognized.error,
        "duration_ms": provider_ms,
    }
    emit_perf_stat(
        "ocr_provider_result",
        provider=recognized.provider or provider_name,
        status=recognized.status,
        ok=recognized.status == "ok",
        error=recognized.error or "",
        result_len=len(recognized.text or recognized.description or ""),
        duration_ms=provider_ms,
        timeout_s=OCR_PROVIDER_TIMEOUT,
    )
    if OCR_LOG_TEXT:
        log_event["text"] = (recognized.text or recognized.description or "")[:OCR_MAX_RESULT_CHARS]
    log(log_event)
    return recognized


def reindex_media_recognition(result: media.MediaRecognition, ref: media.MediaRef) -> media.MediaRecognition:
    if result.index == ref.index and result.type == ref.type:
        return result
    return media.MediaRecognition(
        index=ref.index,
        type=ref.type,
        status=result.status,
        text=result.text,
        description=result.description,
        provider=result.provider,
        error=result.error,
    )


async def fetch_and_recognize_one_media_cached(ref: media.MediaRef, provider: vision.VisionProvider) -> media.MediaRecognition:
    key = ocr_cache_key(ref)
    start = runtime_now()
    now = time.monotonic()
    prune_ocr_cache(now)
    cached = _ocr_result_cache.get(key)
    if cached is not None and (OCR_CACHE_TTL_SECONDS <= 0 or now - cached[0] <= OCR_CACHE_TTL_SECONDS):
        emit_perf_stat("ocr_cache_event", hit=True, inflight_joined=False, cache_size=len(_ocr_result_cache), duration_ms=runtime_elapsed_ms(start))
        return reindex_media_recognition(cached[1], ref)
    inflight = _ocr_inflight.get(key)
    if inflight is not None:
        result = reindex_media_recognition(await inflight, ref)
        emit_perf_stat("ocr_cache_event", hit=False, inflight_joined=True, cache_size=len(_ocr_result_cache), duration_ms=runtime_elapsed_ms(start))
        return result

    async def run() -> media.MediaRecognition:
        async with ocr_semaphore():
            return await fetch_and_recognize_one_media(ref, provider)

    task = asyncio.create_task(run())
    _ocr_inflight[key] = task
    try:
        result = await task
        if OCR_CACHE_MAX_ENTRIES > 0:
            _ocr_result_cache[key] = (time.monotonic(), result)
            prune_ocr_cache()
        emit_perf_stat("ocr_cache_event", hit=False, inflight_joined=False, cache_size=len(_ocr_result_cache), duration_ms=runtime_elapsed_ms(start))
        return result
    finally:
        _ocr_inflight.pop(key, None)


def reindex_media_ref(ref: media.MediaRef, index: int) -> media.MediaRef:
    if ref.index == index:
        return ref
    return media.MediaRef(
        index=index,
        type=ref.type,
        file_id=ref.file_id,
        url=ref.url,
        summary=ref.summary,
        sub_type=ref.sub_type,
        raw_keys=ref.raw_keys,
    )


def media_ref_identity(ref: media.MediaRef) -> tuple[str, str, str, str, str]:
    return (ref.type, ref.file_id, ref.url, ref.summary, ref.sub_type)


def reply_media_messages_from_data(data: dict[str, Any]) -> list[Any]:
    messages: list[Any] = []
    for key in ("message", "content", "text", "raw_message"):
        value = data.get(key)
        if value not in (None, ""):
            messages.append(value)
    for key in ("source", "origin", "reply"):
        value = data.get(key)
        if isinstance(value, dict):
            for nested_key in ("message", "content", "text", "raw_message"):
                nested = value.get(nested_key)
                if nested not in (None, ""):
                    messages.append(nested)
    return messages


def media_refs_for_event(event: dict[str, Any], *, max_refs: int, include_reply_media: bool = False) -> list[media.MediaRef]:
    refs: list[media.MediaRef] = []
    seen: set[tuple[str, str, str, str, str]] = set()

    def append_many(candidates: list[media.MediaRef]) -> None:
        for ref in candidates:
            if len(refs) >= max_refs:
                return
            key = media_ref_identity(ref)
            if key in seen:
                continue
            seen.add(key)
            refs.append(reindex_media_ref(ref, len(refs)))

    append_many(media.extract_media_refs(event.get("message"), max_refs=max_refs))
    if not include_reply_media or len(refs) >= max_refs:
        return refs

    group_id = group_id_from_event(event)
    for seg in reply_segments(event):
        if len(refs) >= max_refs:
            break
        data = seg.get("data") or {}
        if not isinstance(data, dict):
            continue
        for message in reply_media_messages_from_data(data):
            if len(refs) >= max_refs:
                break
            append_many(media.extract_media_refs(message, max_refs=max_refs - len(refs)))
        if len(refs) >= max_refs:
            break
        mid = reply_segment_message_id(data)
        cached = recent_message_by_id(group_id, mid) if mid else None
        cached_refs = cached.get("media_refs") if isinstance(cached, dict) else None
        if isinstance(cached_refs, list):
            append_many([ref for ref in cached_refs if isinstance(ref, media.MediaRef)])
    return refs


async def recognize_media_for_event(event: dict[str, Any], *, route: str, include_failures: bool = True) -> dict[str, Any]:
    start = runtime_now()
    refs = media_refs_for_event(event, max_refs=OCR_MAX_IMAGES_PER_MESSAGE, include_reply_media=(route == "direct"))
    if not refs:
        emit_perf_stat("ocr_route_result", route=route, group_id=event.get("group_id"), media_count=0, ok_count=0, error_count=0, skipped_count=0, duration_ms=runtime_elapsed_ms(start), enabled=ocr_enabled_for_route(route))
        return {"refs": [], "results": [], "media_context": "（当前消息没有图片识别结果）"}
    log({
        "type": "media_detected",
        "group_id": event.get("group_id"),
        "message_id": message_id_from_event(event),
        "route": route,
        "count": len(refs),
        "media": [media_fetch.media_ref_log_summary(ref, include_url=OCR_LOG_IMAGE_URLS) for ref in refs],
    })
    if not ocr_enabled_for_route(route):
        log({"type": "ocr_skipped", "group_id": event.get("group_id"), "message_id": message_id_from_event(event), "route": route, "reason": "disabled_or_route"})
        emit_perf_stat("ocr_route_result", route=route, group_id=event.get("group_id"), media_count=len(refs), ok_count=0, error_count=0, skipped_count=len(refs), duration_ms=runtime_elapsed_ms(start), enabled=False, reason="disabled_or_route")
        return {"refs": refs, "results": [], "media_context": "（当前消息没有图片识别结果）"}
    provider = build_ocr_provider()
    if isinstance(provider, vision.NoopVisionProvider):
        log({"type": "ocr_skipped", "group_id": event.get("group_id"), "message_id": message_id_from_event(event), "route": route, "reason": "provider_none"})
        emit_perf_stat("ocr_route_result", route=route, group_id=event.get("group_id"), media_count=len(refs), ok_count=0, error_count=0, skipped_count=len(refs), duration_ms=runtime_elapsed_ms(start), enabled=True, provider="none", reason="provider_none")
        return {"refs": refs, "results": [], "media_context": "（当前消息没有图片识别结果）"}
    results = [await fetch_and_recognize_one_media_cached(ref, provider) for ref in refs]
    ok_count = sum(1 for result in results if result.status == "ok")
    error_count = sum(1 for result in results if result.status == "error")
    skipped_count = sum(1 for result in results if result.status == "skipped")
    media_context = media.format_media_context(results, max_chars=OCR_MAX_RESULT_CHARS, include_failures=include_failures)
    emit_perf_stat(
        "ocr_route_result",
        route=route,
        group_id=event.get("group_id"),
        media_count=len(refs),
        result_count=len(results),
        ok_count=ok_count,
        error_count=error_count,
        skipped_count=skipped_count,
        provider=getattr(provider, "name", OCR_PROVIDER),
        include_failures=include_failures,
        result_len=0 if media_context == "（当前消息没有图片识别结果）" else len(media_context),
        duration_ms=runtime_elapsed_ms(start),
        enabled=True,
    )
    return {"refs": refs, "results": results, "media_context": media_context}


def ocr_context_text(base_text: str, media_context: str) -> str:
    if not OCR_INCLUDE_IN_CONTEXT:
        return base_text
    merged = media.merge_text_and_media_context(base_text, media_context)
    return merged[:CONTEXT_MAX_CHARS_PER_MESSAGE]


def update_recent_message_media_context(group_id: int | None, identity: dict[str, str], media_context: str, *, text_without_ocr: str) -> bool:
    if group_id is None or not identity:
        return False
    enriched = ocr_context_text(text_without_ocr, media_context)
    if not enriched or enriched == text_without_ocr:
        return False
    messages = recent_messages_for_group(group_id)
    for item in reversed(messages):
        if any(str(item.get(key)) == str(value) for key, value in identity.items() if value):
            item["text"] = enriched
            item["text_without_ocr"] = text_without_ocr[:CONTEXT_MAX_CHARS_PER_MESSAGE]
            if OCR_INCLUDE_IN_CONTEXT and not OCR_PERSIST_TEXT_IN_CONTEXT:
                item["ocr_text_nonpersistent"] = True
            mark_repeated_bot_wording_for_human_message(group_id, item)
            if CONTEXT_PERSIST_ENABLED:
                save_context_cache()
            return True
    return False


async def recognize_and_update_context_for_event(event: dict[str, Any], *, base_text: str, identity: dict[str, str], scheduled_at: float | None = None) -> None:
    start = runtime_now()
    group_id = group_id_from_event(event)
    if not ocr_context_enabled_for_group(group_id):
        return
    media_data = await recognize_media_for_event(event, route="context", include_failures=False)
    media_context = str(media_data.get("media_context") or "（当前消息没有图片识别结果）")
    updated = update_recent_message_media_context(group_id, identity, media_context, text_without_ocr=base_text)
    result_chars = 0 if media_context == "（当前消息没有图片识别结果）" else len(media_context)
    log({
        "type": "ocr_context_update" if updated else "ocr_context_update_missed",
        "group_id": group_id,
        "message_id": identity.get("message_id") or message_id_from_event(event),
        "updated": updated,
        "result_chars": result_chars,
    })
    emit_perf_stat(
        "ocr_context_update",
        group_id=group_id,
        updated=updated,
        result_len=result_chars,
        schedule_delay_ms=runtime_elapsed_ms(scheduled_at),
        duration_ms=runtime_elapsed_ms(start),
    )


def _consume_ocr_context_task(task: asyncio.Task) -> None:
    _ocr_context_tasks.discard(task)
    try:
        task.result()
    except asyncio.CancelledError:
        log({"type": "ocr_context_task_cancelled"})
    except Exception as exc:
        log({"type": "ocr_context_task_error", "error": type(exc).__name__, "message": str(exc)[:200]})


def schedule_context_ocr_for_event(event: dict[str, Any], *, base_text: str, identity: dict[str, str]) -> None:
    group_id = group_id_from_event(event)
    if not ocr_context_enabled_for_group(group_id):
        return
    if not ocr_enabled_for_route("context"):
        return
    if not media.has_processable_media(event.get("message")):
        return
    scheduled_at = runtime_now()
    task = asyncio.create_task(recognize_and_update_context_for_event(dict(event), base_text=base_text, identity=dict(identity), scheduled_at=scheduled_at))
    _ocr_context_tasks.add(task)
    task.add_done_callback(_consume_ocr_context_task)
    emit_perf_stat("ocr_context_task_scheduled", group_id=group_id, media_count=len(media.extract_media_refs(event.get("message"), max_refs=OCR_MAX_IMAGES_PER_MESSAGE)))




def remember_message_and_schedule_context_ocr(event: dict[str, Any]) -> dict[str, Any] | None:
    base_text = message_to_text(event.get("message"), include_at=False) or "（非文本消息）"
    item = remember_message(event, base_text)
    if item is not None:
        schedule_context_ocr_for_event(event, base_text=base_text, identity=message_identity_from_event(event))
    return item

def hermes_session_name_for_group(group_id: int | None) -> str:
    return hermes_runtime.hermes_session_name_for_group(
        group_id,
        target_group_id=TARGET_GROUP_ID,
        group_session_prefix=HERMES_GROUP_SESSION_PREFIX,
    )


def _sqlite_message_count_for_session(session_id: str) -> int:
    try:
        db_path = Path(os.getenv("HERMES_HOME", "/home/roxy/.hermes")) / "state.db"
        return hermes_runtime.sqlite_message_count_for_session(session_id, db_path=db_path)
    except Exception as exc:
        log({"type": "hermes_session_inspect_error", "session_id": session_id, "error": type(exc).__name__, "message": str(exc)})
        return 0


def _estimated_session_body_chars(session_id: str) -> int:
    try:
        db_path = Path(os.getenv("HERMES_HOME", "/home/roxy/.hermes")) / "state.db"
        return hermes_runtime.estimated_session_body_chars(session_id, db_path=db_path)
    except Exception as exc:
        log({"type": "hermes_session_inspect_error", "session_id": session_id, "error": type(exc).__name__, "message": str(exc)})
        return 0


def hermes_session_id_by_title(session_name: str) -> str:
    try:
        db_path = Path(os.getenv("HERMES_HOME", "/home/roxy/.hermes")) / "state.db"
        return hermes_runtime.session_id_by_title(session_name, db_path=db_path)
    except Exception as exc:
        log({"type": "hermes_session_lookup_error", "session_name": session_name, "error": type(exc).__name__, "message": str(exc)})
        return ""


def hermes_session_needs_compaction(session_id: str) -> tuple[bool, dict[str, int]]:
    return hermes_runtime.session_needs_compaction(
        session_id,
        max_messages=HERMES_SESSION_MAX_MESSAGES,
        max_body_chars=HERMES_SESSION_MAX_BODY_CHARS,
        message_count_fn=_sqlite_message_count_for_session,
        body_chars_fn=_estimated_session_body_chars,
    )


def hermes_session_summary_for_group(group_id: int | None) -> str:
    gid = group_id if group_id is not None else TARGET_GROUP_ID
    return hermes_runtime.session_summary_prompt(
        gid,
        summaries=format_context_summaries(gid),
        recent=format_recent_context(gid),
        max_chars=HERMES_SESSION_COMPACT_SUMMARY_CHARS,
    )


def delete_hermes_session(session_id: str, reason: str) -> bool:
    if not session_id:
        return False
    cmd = hermes_runtime.delete_session_cmd(HERMES_BIN, session_id)
    try:
        r = subprocess.run(cmd, text=True, capture_output=True, timeout=30, cwd=str(BASE_DIR))
    except Exception as exc:
        log({"type": "hermes_session_delete_error", "session_id": session_id, "reason": reason, "error": type(exc).__name__, "message": str(exc)})
        return False
    log(
        hermes_runtime.session_delete_log_event(
            session_id=session_id,
            reason=reason,
            returncode=r.returncode,
            stdout=r.stdout or "",
            stderr=r.stderr or "",
        )
    )
    return r.returncode == 0


def compact_group_hermes_session_if_needed(group_id: int | None) -> bool:
    if not HERMES_SESSION_AUTOCOMPACT_ENABLED or not HERMES_GROUP_SESSIONS_ENABLED:
        return False
    session_name = hermes_session_name_for_group(group_id)
    session_id = hermes_session_id_by_title(session_name)
    needs, stats = hermes_session_needs_compaction(session_id)
    if not needs:
        return False
    gid = group_id if group_id is not None else TARGET_GROUP_ID
    summary_prompt = hermes_session_summary_for_group(gid)
    log({"type": "hermes_session_autocompact_start", "group_id": gid, "session_name": session_name, "session_id": session_id, **stats})
    if not delete_hermes_session(session_id, "autocompact_threshold"):
        return False
    p = bootstrap_group_session(summary_prompt, group_id)
    if p is not None and p.returncode == 0:
        new_session_id = extract_session_id((p.stdout or "") + "\n" + (p.stderr or ""))
        log({"type": "hermes_session_autocompact_done", "group_id": gid, "old_session_id": session_id, "new_session_id": new_session_id})
        return True
    log({"type": "hermes_session_autocompact_error", "group_id": gid, "old_session_id": session_id, "returncode": getattr(p, "returncode", None), "stdout": (getattr(p, "stdout", "") or "")[-1000:], "stderr": (getattr(p, "stderr", "") or "")[-1000:]})
    return False


def output_indicates_missing_session(output: str) -> bool:
    return hermes_runtime.output_indicates_missing_session(output)


def extract_session_id(output: str) -> str:
    return hermes_runtime.extract_session_id(output)


def strip_session_footer(output: str) -> str:
    return hermes_runtime.strip_session_footer(output)


def hermes_model_for_group(group_id: int | None) -> str:
    if group_id is not None and group_id in HERMES_MODEL_BY_GROUP:
        return HERMES_MODEL_BY_GROUP[group_id]
    return HERMES_MODEL


def hermes_provider_for_group(group_id: int | None) -> str:
    if group_id is not None and group_id in HERMES_PROVIDER_BY_GROUP:
        return HERMES_PROVIDER_BY_GROUP[group_id]
    return HERMES_PROVIDER


def build_hermes_cmd(prompt: str, group_id: int | None = None, use_group_session: bool = True, model: str | None = None, provider: str | None = None) -> list[str]:
    return hermes_runtime.build_hermes_cmd(
        prompt,
        group_id=group_id,
        use_group_session=use_group_session,
        model=model,
        provider=provider,
        hermes_bin=HERMES_BIN,
        group_sessions_enabled=HERMES_GROUP_SESSIONS_ENABLED,
        group_session_prefix=HERMES_GROUP_SESSION_PREFIX,
        target_group_id=TARGET_GROUP_ID,
        hermes_model=hermes_model_for_group(group_id),
        hermes_provider=hermes_provider_for_group(group_id),
    )


def run_hermes_cmd(cmd: list[str], *, purpose: str = "unknown", group_id: int | None = None, use_group_session: bool = True, input_chars: int = 0) -> subprocess.CompletedProcess[str] | None:
    log({"type": "hermes_start", "cmd": " ".join(shlex.quote(x) for x in cmd[:3] + ["<prompt>"] + cmd[4:])})
    start = time.monotonic()
    try:
        result = subprocess.run(cmd, text=True, capture_output=True, timeout=HERMES_TIMEOUT, cwd=str(BASE_DIR))
        runtime_stat(
            "hermes_call",
            purpose=purpose,
            group_id=group_id,
            use_group_session=use_group_session,
            duration_ms=runtime_stats.duration_ms(start),
            ok=result.returncode == 0,
            returncode=result.returncode,
            input_chars=input_chars,
            output_len=len(result.stdout or "") + len(result.stderr or ""),
            timeout_s=HERMES_TIMEOUT,
            model_configured=bool(hermes_model_for_group(group_id)),
            provider_configured=bool(hermes_provider_for_group(group_id)),
        )
        increment_runtime_counter("hermes_calls")
        if result.returncode != 0:
            increment_runtime_counter("hermes_errors")
        return result
    except FileNotFoundError:
        runtime_stat("hermes_call", purpose=purpose, group_id=group_id, use_group_session=use_group_session, duration_ms=runtime_stats.duration_ms(start), ok=False, error="FileNotFoundError", input_chars=input_chars, timeout_s=HERMES_TIMEOUT)
        increment_runtime_counter("hermes_calls")
        increment_runtime_counter("hermes_errors")
        log({"type": "hermes_error", "error": "FileNotFoundError", "hermes_bin": HERMES_BIN})
    except subprocess.TimeoutExpired:
        runtime_stat("hermes_call", purpose=purpose, group_id=group_id, use_group_session=use_group_session, duration_ms=runtime_stats.duration_ms(start), ok=False, error="TimeoutExpired", input_chars=input_chars, timeout_s=HERMES_TIMEOUT)
        increment_runtime_counter("hermes_calls")
        increment_runtime_counter("hermes_errors")
        log({"type": "hermes_error", "error": "TimeoutExpired", "timeout": HERMES_TIMEOUT})
    except Exception as exc:
        runtime_stat("hermes_call", purpose=purpose, group_id=group_id, use_group_session=use_group_session, duration_ms=runtime_stats.duration_ms(start), ok=False, error=type(exc).__name__, input_chars=input_chars, timeout_s=HERMES_TIMEOUT)
        increment_runtime_counter("hermes_calls")
        increment_runtime_counter("hermes_errors")
        log({"type": "hermes_error", "error": type(exc).__name__, "message": str(exc)})
    return None


def bootstrap_group_session(prompt: str, group_id: int | None) -> subprocess.CompletedProcess[str] | None:
    p = run_hermes_cmd(build_hermes_cmd(prompt, group_id=group_id, use_group_session=False), purpose="session_bootstrap", group_id=group_id, use_group_session=False, input_chars=len(prompt))
    if not p or p.returncode != 0:
        return p
    session_id = extract_session_id((p.stdout or "") + "\n" + (p.stderr or ""))
    if session_id:
        session_name = hermes_session_name_for_group(group_id)
        rename_cmd = [HERMES_BIN, "sessions", "rename", session_id, session_name]
        try:
            r = subprocess.run(rename_cmd, text=True, capture_output=True, timeout=30, cwd=str(BASE_DIR))
            if r.returncode != 0:
                log({"type": "hermes_session_rename_error", "returncode": r.returncode, "stdout": (r.stdout or "")[-1000:], "stderr": (r.stderr or "")[-1000:], "session_id": session_id, "session_name": session_name})
            else:
                log({"type": "hermes_session_created", "session_id": session_id, "session_name": session_name})
        except Exception as exc:
            log({"type": "hermes_session_rename_error", "error": type(exc).__name__, "message": str(exc), "session_id": session_id, "session_name": session_name})
    return p


def _proactive_output_should_suppress(output: str) -> bool:
    return model_output.proactive_output_should_suppress(output)


def _strip_reply_prefix(text: str) -> str:
    clean = str(text or "")
    if REPLY_PREFIX and clean.startswith(REPLY_PREFIX):
        return clean[len(REPLY_PREFIX):].lstrip()
    return clean


def recent_bot_reply_texts_for_group(group_id: int | None, limit: int = 8) -> list[str]:
    gid = group_id if group_id is not None else TARGET_GROUP_ID
    texts: list[str] = []
    for item in reversed(list(recent_messages_for_group(gid))):
        role = str(item.get("role") or "")
        if "机器人" not in role or "正在生成回复" in role:
            continue
        text = _strip_reply_prefix(str(item.get("text") or ""))
        if text:
            texts.append(text)
        if len(texts) >= limit:
            break
    return texts


def _proactive_output_repeats_recent_bot_wording(group_id: int | None, output: str) -> bool:
    return model_output.proactive_output_repeats_recent_bot_wording(
        output,
        recent_bot_reply_texts_for_group(group_id),
    )


def run_proactive_reply(event: dict[str, Any], reasons: list[str]) -> str:
    group_id = group_id_from_event(event)
    raw = run_hermes_raw(build_proactive_prompt(event, reasons), group_id=group_id, use_group_session=False, purpose="proactive_reply")
    # 先检测是否需要沉默，再 finalize_reply，避免 finalize_reply 把空输出变成默认回复
    if _proactive_output_should_suppress(raw):
        return ""
    reply = finalize_reply(raw)
    if _proactive_output_repeats_recent_bot_wording(group_id, reply):
        log({"type": "proactive_repeated_bot_wording_suppressed", "group_id": group_id, "reply": reply[:120]})
        return ""
    return reply


def run_hermes_raw_result(prompt: str, group_id: int | None = None, use_group_session: bool = True, purpose: str = "unknown") -> dict[str, Any]:
    if use_group_session:
        compact_group_hermes_session_if_needed(group_id)
    p = run_hermes_cmd(build_hermes_cmd(prompt, group_id=group_id, use_group_session=use_group_session), purpose=purpose, group_id=group_id, use_group_session=use_group_session, input_chars=len(prompt))
    if p is None:
        return {"ok": False, "text": "", "reason": "hermes_process_failed"}
    output = (p.stdout or "") + "\n" + (p.stderr or "")
    if p.returncode != 0 and HERMES_GROUP_SESSIONS_ENABLED and use_group_session and output_indicates_missing_session(output):
        log({"type": "hermes_missing_group_session", "group_id": group_id, "session_name": hermes_session_name_for_group(group_id), "stdout": (p.stdout or "")[-1000:], "stderr": (p.stderr or "")[-1000:]})
        p = bootstrap_group_session(prompt, group_id)
        if p is None:
            return {"ok": False, "text": "", "reason": "hermes_session_bootstrap_failed"}
    if p.returncode != 0:
        log({"type": "hermes_error", "returncode": p.returncode, "stdout": (p.stdout or "")[-2000:], "stderr": (p.stderr or "")[-2000:]})
        return {
            "ok": False,
            "text": "",
            "reason": "hermes_nonzero",
            "returncode": p.returncode,
            "stdout": p.stdout or "",
            "stderr": p.stderr or "",
        }
    return {"ok": True, "text": strip_session_footer(p.stdout or ""), "reason": ""}


def run_hermes_raw(prompt: str, group_id: int | None = None, use_group_session: bool = True, purpose: str = "unknown") -> str:
    return str(run_hermes_raw_result(prompt, group_id, use_group_session, purpose=purpose).get("text") or "")


def run_hermes(prompt: str, group_id: int | None = None, use_group_session: bool = True, purpose: str = "unknown") -> str:
    raw = run_hermes_raw(prompt, group_id, use_group_session, purpose=purpose)
    if not raw:
        return pick_template("hermes_error", str(group_id or ""))
    # 去除 Hermes CLI 可能带出的尾部空白和过长内容
    return finalize_reply(raw)


def run_direct_hermes_raw(prompt: str, group_id: int | None = None, *, use_group_session: bool = True, purpose: str = "direct_reply") -> str:
    try:
        return run_hermes_raw(prompt, group_id, use_group_session=use_group_session, purpose=purpose)
    except TypeError as exc:
        if "purpose" not in str(exc):
            raise
        return run_hermes_raw(prompt, group_id, use_group_session=use_group_session)


def direct_retry_prompt(prompt: str) -> str:
    return (
        f"{prompt}\n\n"
        "注意：上一轮直接回复生成了空内容。当前消息是群友明确 @/提到 Esti 的直接提问，必须输出一条可发送到群里的简短回复；"
        "如果不确定，就用自然群聊口吻简短追问，不要输出空字符串。"
    )


def generate_direct_reply(prompt: str, group_id: int | None = None) -> dict[str, Any]:
    raw = run_direct_hermes_raw(prompt, group_id, purpose="direct_reply")
    if not raw:
        log({"type": "direct_reply_empty_retry", "group_id": group_id, "retry_use_group_session": False})
        raw = run_direct_hermes_raw(direct_retry_prompt(prompt), group_id, use_group_session=False, purpose="direct_reply_retry")
    if not raw:
        reply = pick_template("hermes_error", str(group_id or ""))
        log({"type": "direct_reply_generation_failed", "group_id": group_id, "reason": "direct_hermes_empty"})
        return {"ok": False, "generation_failed": True, "reason": "direct_hermes_empty", "reply": reply}
    return {"ok": True, "generation_failed": False, "reply": finalize_reply(raw)}


def direct_failure_notice_for_event(event: dict[str, Any]) -> str:
    parts: list[str] = []
    message_id = event.get("message_id") or event.get("id") or event.get("message_seq") or event.get("real_id")
    if message_id not in (None, ""):
        parts.append(f"[CQ:reply,id={message_id}]")
    user_id = event.get("user_id")
    if user_id not in (None, ""):
        parts.append(f"[CQ:at,qq={user_id}]")
    parts.append(" 稍后重试一下")
    return "".join(parts).strip()


async def send_group_msg(group_id: int, message: str) -> dict[str, Any]:
    start = time.monotonic()
    data: dict[str, Any] = {"ok": False, "error": "send_not_attempted"}
    try:
        data = await outbound.send_group_msg(
            group_id,
            message,
            onebot_http_url=ONEBOT_HTTP_URL,
            access_token=ONEBOT_ACCESS_TOKEN,
        )
        status_code = data.get("status_code") if isinstance(data, dict) else None
        log({"type": "send_group_msg", "status_code": status_code, "response": data})
        return data
    except Exception as exc:
        data = {"error": type(exc).__name__, "message": str(exc), "onebot_http_url": ONEBOT_HTTP_URL}
        log({"type": "send_group_msg_error", **data})
        return data
    finally:
        ok = send_group_msg_succeeded(data)
        increment_runtime_counter("send_attempts")
        if not ok:
            increment_runtime_counter("send_errors")
        runtime_stat(
            "send_group_msg",
            group_id=group_id,
            duration_ms=runtime_stats.duration_ms(start),
            ok=ok,
            status_code=data.get("status_code") if isinstance(data, dict) else None,
            onebot_status=str(data.get("status") or "")[:40] if isinstance(data, dict) else "",
            output_len=len(message or ""),
            suppressed_duplicate=False,
        )


def send_group_msg_succeeded(data: dict[str, Any]) -> bool:
    return outbound.send_group_msg_succeeded(data)


def _outbound_key(message: str) -> str:
    return outbound.outbound_key(message)


def is_recent_duplicate_outbound(group_id: int, message: str, now: float | None = None, window: float = 30.0) -> bool:
    return outbound.is_recent_duplicate_outbound(
        group_id,
        message,
        recent_by_group=_recent_outbound_by_group,
        now=now,
        window=window,
    )


def remember_successful_outbound(group_id: int, message: str, now: float | None = None, window: float = 30.0) -> None:
    outbound.remember_successful_outbound(
        group_id,
        message,
        recent_by_group=_recent_outbound_by_group,
        now=now,
        window=window,
    )


def should_suppress_duplicate_outbound(group_id: int, message: str, now: float | None = None, window: float = 30.0) -> bool:
    return is_recent_duplicate_outbound(group_id, message, now=now, window=window)


async def reserve_outbound_attempt(group_id: int, message: str, duplicate_window: float = 30.0) -> tuple[str, bool]:
    key = _outbound_key(message)
    async with _outbound_lock:
        if is_recent_duplicate_outbound(group_id, message, window=duplicate_window):
            return key, True
        inflight = _outbound_inflight_by_group.setdefault(group_id, set())
        if key in inflight:
            return key, True
        inflight.add(key)
        return key, False


async def finish_outbound_attempt(group_id: int, message: str, key: str, succeeded: bool, duplicate_window: float = 30.0) -> None:
    async with _outbound_lock:
        inflight = _outbound_inflight_by_group.setdefault(group_id, set())
        inflight.discard(key)
        if succeeded:
            remember_successful_outbound(group_id, message, window=duplicate_window)


async def send_group_msg_once(group_id: int, message: str, duplicate_window: float = 30.0) -> tuple[dict[str, Any], bool]:
    key, suppressed = await reserve_outbound_attempt(group_id, message, duplicate_window)
    if suppressed:
        log({"type": "duplicate_outbound_suppressed", "group_id": group_id, "message": (message or "")[:120]})
        increment_runtime_counter("duplicate_outbound_suppressed")
        runtime_stat(
            "send_group_msg",
            group_id=group_id,
            duration_ms=0,
            ok=True,
            output_len=len(message or ""),
            suppressed_duplicate=True,
        )
        return {"ok": True, "suppressed": "duplicate_outbound"}, True
    data: dict[str, Any] = {"ok": False, "error": "send_not_attempted"}
    try:
        data = await send_group_msg(group_id, message)
        return data, False
    finally:
        await finish_outbound_attempt(
            group_id,
            message,
            key,
            send_group_msg_succeeded(data),
            duplicate_window=duplicate_window,
        )


async def send_group_msg_rate_limited(group_id: int, message: str, *, once: bool = False, duplicate_window: float = 30.0) -> tuple[dict[str, Any], bool]:
    global _last_reply_at
    start = runtime_now()
    waited_ms = 0
    data: dict[str, Any] = {"ok": False, "error": "send_not_attempted"}
    suppressed = False
    async with _lock:
        wait = MIN_SECONDS_BETWEEN_REPLIES - (time.time() - _last_reply_at)
        if wait > 0:
            wait_start = runtime_now()
            await asyncio.sleep(wait)
            waited_ms = runtime_elapsed_ms(wait_start)
        if once:
            data, suppressed = await send_group_msg_once(group_id, message, duplicate_window=duplicate_window)
        else:
            data = await send_group_msg(group_id, message)
            suppressed = False
        if send_group_msg_succeeded(data):
            _last_reply_at = time.time()
    emit_perf_stat(
        "send_group_msg_rate_limited",
        group_id=group_id,
        duration_ms=runtime_elapsed_ms(start),
        rate_limit_wait_ms=waited_ms,
        ok=send_group_msg_succeeded(data),
        output_len=len(message or ""),
        suppressed_duplicate=suppressed,
    )
    return data, suppressed


async def send_immediate_reply(group_id: int, reply: str, event: dict[str, Any], trigger: str, log_type: str, remember_context: bool = False, **extra: Any) -> dict[str, Any]:
    """发送不进普通回复队列的命令回复，统一限速、失败判断和用户冷却标记。"""
    if REPLY_PREFIX:
        reply = REPLY_PREFIX + reply
    data, _suppressed = await send_group_msg_rate_limited(group_id, reply)
    if not send_group_msg_succeeded(data):
        log({"type": f"{log_type}_send_failed", "group_id": group_id, "user_id": event.get("user_id"), "response": data})
        return {"ok": False, "replied": False, "trigger": trigger, "error": "send_failed", "response": data}
    if remember_context:
        remember_bot_reply(group_id, reply, event.get("self_id"))
    content_analysis_log(
        "immediate_reply_sent",
        group_id,
        **content_analysis_user_fields(event),
        trigger=trigger,
        log_type=log_type,
        reply=reply_to_analysis_text(reply),
        extra=extra,
    )
    mark_user_replied(group_id, event.get("user_id"))
    log({"type": f"{log_type}_reply_sent", "group_id": group_id, "user_id": event.get("user_id"), **extra})
    return {"ok": True, "replied": True, "trigger": trigger, **extra}


def record_direct_reply_runtime_result(group_id: int, event: dict[str, Any], *, trigger: str, result: dict[str, Any], output_len: int, duration_start: float, perf: dict[str, Any] | None = None) -> None:
    perf = perf or {}
    interaction_id = str(perf.get("interaction_id") or "")
    if result.get("replied"):
        increment_runtime_counter("direct_replies_sent")
    if result.get("generation_failed"):
        increment_runtime_counter("direct_generation_failures")
    if result.get("error") == "send_failed":
        increment_runtime_counter("direct_send_errors")
    emit_perf_stat(
        "direct_reply_result",
        interaction_id=interaction_id,
        group_id=group_id,
        user_hash=runtime_user_hash(event.get("user_id")),
        trigger=trigger,
        ok=bool(result.get("ok")),
        replied=bool(result.get("replied")),
        generation_failed=bool(result.get("generation_failed")),
        send_failed=result.get("error") == "send_failed",
        failure_notice_sent=bool(result.get("failure_notice_sent")),
        output_len=output_len,
        queue_remaining=result.get("queue_remaining", reply_queue_size(group_id)),
        queue_wait_ms=perf.get("queue_wait_ms", 0),
        prompt_build_ms=perf.get("prompt_build_ms", 0),
        generation_ms=perf.get("generation_ms", 0),
        e2e_ms=perf.get("e2e_ms", 0),
        duration_ms=runtime_stats.duration_ms(duration_start),
    )
async def process_direct_reply_intent(group_id: int, queued_intent: dict[str, Any]) -> dict[str, Any]:
    global _last_reply_at
    event = queued_intent.get("event") or {}
    user_text = str(queued_intent.get("user_text") or "")
    media_context = str(queued_intent.get("media_context") or "（当前消息没有图片识别结果）")
    trigger = queued_intent.get("trigger") or "at"
    pending_remembered = False
    search_notice_sent = False
    start = runtime_now()
    interaction_id = str(queued_intent.get("_perf_interaction_id") or runtime_interaction_id(event))
    queue_wait_ms = int(queued_intent.get("_perf_queue_wait_ms") or runtime_elapsed_ms(queued_intent.get("_perf_enqueued_at")))
    event_received_at = queued_intent.get("_perf_event_received_at")
    prompt_build_ms = 0
    generation_ms = 0
    perf: dict[str, Any] = {"interaction_id": interaction_id, "queue_wait_ms": queue_wait_ms, "event_received_at": event_received_at}
    try:
        remember_bot_pending_reply(group_id, user_text, event.get("self_id"))
        pending_remembered = True
        content_analysis_log(
            "direct_generation_start",
            group_id,
            **content_analysis_user_fields(event),
            trigger=trigger,
            user_text=analysis_log_utils.sanitize_text(user_text, CONTENT_ANALYSIS_MAX_TEXT_CHARS),
            context=analysis_context_snapshot(group_id),
            queue_size=reply_queue_size(group_id),
        )
        prompt_start = runtime_now()
        prompt = build_prompt(event, user_text, media_context if OCR_INCLUDE_IN_PROMPT else "（当前消息没有图片识别结果）")
        prompt_build_ms = runtime_elapsed_ms(prompt_start)
        generation_start = runtime_now()
        generated = await asyncio.to_thread(generate_direct_reply, prompt, group_id)
        generation_ms = runtime_elapsed_ms(generation_start)
    except Exception as exc:
        log({"type": "direct_reply_error", "group_id": group_id, "user_id": event.get("user_id"), "error": type(exc).__name__, "message": str(exc)})
        generated = {
            "ok": False,
            "generation_failed": True,
            "reason": "direct_reply_failed",
            "reply": pick_template("hermes_error", str(group_id or "")),
        }
    perf["prompt_build_ms"] = prompt_build_ms
    perf["generation_ms"] = generation_ms
    perf["e2e_ms"] = interaction_e2e_ms(interaction_id, event_received_at)
    reply = str(generated.get("reply") or "")
    reason = str(generated.get("reason") or "")
    generation_failed = bool(generated.get("generation_failed"))
    if not reply:
        reply = pick_template("hermes_error", str(group_id or ""))
        reason = reason or "direct_hermes_empty"
        generation_failed = True
    if generation_failed:
        reply = direct_failure_notice_for_event(event)
    if REPLY_PREFIX and not generation_failed:
        reply = REPLY_PREFIX + reply
    outbound_reply = reply if generation_failed else reply_message_for_event(event, reply)
    data, suppressed = await send_group_msg_rate_limited(group_id, outbound_reply, once=not generation_failed)
    perf["e2e_ms"] = interaction_e2e_ms(interaction_id, event_received_at)
    if suppressed:
        drop_last_bot_pending_reply(group_id)
        result = reply_processing.direct_reply_duplicate_result(
            trigger=trigger,
            queue_remaining=reply_queue_size(group_id),
        )
        content_analysis_log(
            "direct_reply_suppressed",
            group_id,
            **content_analysis_user_fields(event),
            trigger=trigger,
            reason="duplicate_outbound",
            generation_failed=generation_failed,
            queue_remaining=reply_queue_size(group_id),
        )
        record_direct_reply_runtime_result(group_id, event, trigger=trigger, result=result, output_len=len(reply), duration_start=start, perf=perf)
        return result
    if not send_group_msg_succeeded(data):
        drop_last_bot_pending_reply(group_id)
        log({"type": "direct_reply_send_failed", "group_id": group_id, "user_id": event.get("user_id"), "generation_failed": generation_failed, "response": data})
        content_analysis_log(
            "direct_reply_failed",
            group_id,
            **content_analysis_user_fields(event),
            trigger=trigger,
            reason="send_failed",
            generation_failed=generation_failed,
            queue_remaining=reply_queue_size(group_id),
        )
        if generation_failed:
            result = reply_processing.direct_reply_generation_failed_result(
                trigger=trigger,
                reason=reason or "direct_hermes_empty",
                queue_remaining=reply_queue_size(group_id),
                failure_notice_sent=False,
                response=data,
            )
            record_direct_reply_runtime_result(group_id, event, trigger=trigger, result=result, output_len=len(reply), duration_start=start, perf=perf)
            return result
        result = reply_processing.direct_reply_send_failed_result(
            trigger=trigger,
            response=data,
        )
        record_direct_reply_runtime_result(group_id, event, trigger=trigger, result=result, output_len=len(reply), duration_start=start, perf=perf)
        return result
    replace_last_bot_pending_reply(group_id, reply, event.get("self_id"))
    if generation_failed:
        log({"type": "direct_generation_failed_notice_sent", "group_id": group_id, "user_id": event.get("user_id"), "reason": reason})
        result = reply_processing.direct_reply_generation_failed_result(
            trigger=trigger,
            reason=reason or "direct_hermes_empty",
            queue_remaining=reply_queue_size(group_id),
            failure_notice_sent=True,
            response=data,
        )
        content_analysis_log(
            "direct_reply_sent",
            group_id,
            **content_analysis_user_fields(event),
            trigger=trigger,
            reply=reply_to_analysis_text(reply),
            generation_failed=True,
            failure_notice_sent=True,
            reason=reason or "direct_hermes_empty",
            queue_remaining=reply_queue_size(group_id),
        )
        record_direct_reply_runtime_result(group_id, event, trigger=trigger, result=result, output_len=len(reply), duration_start=start, perf=perf)
        return result
    mark_user_replied(group_id, event.get("user_id"))
    result = reply_processing.direct_reply_success_result(
        trigger=trigger,
        queue_remaining=reply_queue_size(group_id),
        search_notice_sent=search_notice_sent,
    )
    content_analysis_log(
        "direct_reply_sent",
        group_id,
        **content_analysis_user_fields(event),
        trigger=trigger,
        reply=reply_to_analysis_text(reply),
        generation_failed=False,
        failure_notice_sent=False,
        queue_remaining=reply_queue_size(group_id),
        search_notice_sent=search_notice_sent,
    )
    record_direct_reply_runtime_result(group_id, event, trigger=trigger, result=result, output_len=len(reply), duration_start=start, perf=perf)
    return result


def record_proactive_runtime_result(group_id: int, event: dict[str, Any], proactive_data: dict[str, Any], *, result: dict[str, Any], output_len: int, suppressed_duplicate: bool, duration_start: float, perf: dict[str, Any] | None = None) -> None:
    perf = perf or {}
    interaction_id = str(perf.get("interaction_id") or "")
    if result.get("proactive_replied"):
        increment_runtime_counter("proactive_replies_sent")
    elif result.get("ignored") in {"proactive_model_skipped", "proactive_revalidated_blocked", "duplicate_outbound"}:
        increment_runtime_counter("proactive_skipped")
    if suppressed_duplicate:
        pass
    emit_perf_stat(
        "proactive_reply_result",
        interaction_id=interaction_id,
        group_id=group_id,
        ok=bool(result.get("ok")),
        sent=bool(result.get("proactive_replied")),
        skipped=bool(result.get("ignored")),
        suppressed_duplicate=suppressed_duplicate,
        output_len=output_len,
        score=proactive_data.get("score"),
        reasons=proactive_data.get("reasons", []),
        queue_remaining=result.get("queue_remaining", reply_queue_size(group_id)),
        queue_wait_ms=perf.get("queue_wait_ms", 0),
        generation_ms=perf.get("generation_ms", 0),
        e2e_ms=perf.get("e2e_ms", 0),
        duration_ms=runtime_stats.duration_ms(duration_start),
    )


def complete_proactive_skip(
    group_id: int,
    event: dict[str, Any],
    proactive_data: dict[str, Any],
    *,
    result_reason: str = "proactive_model_skipped",
    analysis_reason: str = "",
    blocked: str = "",
    phase: str = "",
    output_len: int = 0,
    duration_start: float,
    perf: dict[str, Any] | None = None,
) -> dict[str, Any]:
    mark_proactive_skipped(group_id)
    log_payload: dict[str, Any] = {
        "type": "proactive_skipped",
        "group_id": group_id,
        "score": proactive_data.get("score"),
        "reasons": proactive_data.get("reasons", []),
        "direct_name_trigger": proactive_data.get("direct_name_trigger", False),
    }
    if blocked:
        log_payload["blocked"] = blocked
    if phase:
        log_payload["phase"] = phase
    log(log_payload)

    result = reply_processing.proactive_skipped_result(
        proactive_data,
        queue_remaining=reply_queue_size(group_id),
        reason=result_reason,
        blocked=blocked,
    )
    analysis_fields: dict[str, Any] = {
        "score": proactive_data.get("score"),
        "reasons": proactive_data.get("reasons", []),
        "direct_name_trigger": proactive_data.get("direct_name_trigger", False),
        "queue_remaining": reply_queue_size(group_id),
    }
    if analysis_reason:
        analysis_fields["reason"] = analysis_reason
    if blocked:
        analysis_fields["blocked"] = blocked
    content_analysis_log(
        "proactive_skipped",
        group_id,
        **content_analysis_user_fields(event),
        **analysis_fields,
    )
    record_proactive_runtime_result(
        group_id,
        event,
        proactive_data,
        result=result,
        output_len=output_len,
        suppressed_duplicate=False,
        duration_start=duration_start,
        perf=perf,
    )
    return result


async def process_proactive_reply_intent(group_id: int, queued_intent: dict[str, Any]) -> dict[str, Any]:
    global _last_reply_at
    event = queued_intent.get("event") or {}
    proactive = queued_intent.get("proactive") or {}
    search_notice_sent = False
    start = runtime_now()
    interaction_id = str(queued_intent.get("_perf_interaction_id") or runtime_interaction_id(event))
    queue_wait_ms = int(queued_intent.get("_perf_queue_wait_ms") or runtime_elapsed_ms(queued_intent.get("_perf_enqueued_at")))
    event_received_at = queued_intent.get("_perf_event_received_at")
    generation_ms = 0
    perf: dict[str, Any] = {"interaction_id": interaction_id, "queue_wait_ms": queue_wait_ms, "event_received_at": event_received_at}
    perf["e2e_ms"] = interaction_e2e_ms(interaction_id, event_received_at)
    revalidate_block = proactive_block_reason(proactive_state_for_group(group_id), time.time(), group_id)
    if revalidate_block:
        return complete_proactive_skip(
            group_id,
            event,
            proactive,
            result_reason="proactive_revalidated_blocked",
            analysis_reason="dequeue_revalidate",
            blocked=revalidate_block,
            phase="dequeue_revalidate",
            duration_start=start,
            perf=perf,
        )
    content_analysis_log(
        "proactive_generation_start",
        group_id,
        **content_analysis_user_fields(event),
        trigger_text=message_to_analysis_text(event, include_at=False),
        score=proactive.get("score"),
        reasons=proactive.get("reasons", []),
        direct_name_trigger=proactive.get("direct_name_trigger", False),
        context=analysis_context_snapshot(group_id),
        queue_size=reply_queue_size(group_id),
    )
    generation_start = runtime_now()
    reply = await asyncio.to_thread(run_proactive_reply, event, proactive.get("reasons", []))
    generation_ms = runtime_elapsed_ms(generation_start)
    perf["generation_ms"] = generation_ms
    perf["e2e_ms"] = interaction_e2e_ms(interaction_id, event_received_at)
    if reply:
        if REPLY_PREFIX:
            reply = REPLY_PREFIX + reply
        data, suppressed = await send_group_msg_rate_limited(group_id, reply, once=True)
        perf["e2e_ms"] = interaction_e2e_ms(interaction_id, event_received_at)
        if suppressed:
            mark_proactive_skipped(group_id)
            log({"type": "proactive_duplicate_outbound_suppressed", "group_id": group_id, "score": proactive.get("score"), "reasons": proactive.get("reasons", [])})
            result = reply_processing.proactive_duplicate_result(
                proactive,
                queue_remaining=reply_queue_size(group_id),
            )
            content_analysis_log(
                "proactive_suppressed",
                group_id,
                **content_analysis_user_fields(event),
                reason="duplicate_outbound",
                score=proactive.get("score"),
                reasons=proactive.get("reasons", []),
                queue_remaining=reply_queue_size(group_id),
            )
            record_proactive_runtime_result(group_id, event, proactive, result=result, output_len=len(reply), suppressed_duplicate=True, duration_start=start, perf=perf)
            return result
        if not send_group_msg_succeeded(data):
            log({"type": "proactive_send_failed", "group_id": group_id, "response": data})
            result = reply_processing.proactive_send_failed_result(data)
            content_analysis_log(
                "proactive_suppressed",
                group_id,
                **content_analysis_user_fields(event),
                reason="send_failed",
                score=proactive.get("score"),
                reasons=proactive.get("reasons", []),
                queue_remaining=reply_queue_size(group_id),
            )
            record_proactive_runtime_result(group_id, event, proactive, result=result, output_len=len(reply), suppressed_duplicate=False, duration_start=start, perf=perf)
            return result
        remember_bot_reply(group_id, reply, event.get("self_id"))
        mark_proactive_replied(group_id)
        log({"type": "proactive_reply_sent", "group_id": group_id, "score": proactive.get("score"), "reasons": proactive.get("reasons", []), "direct_name_trigger": proactive.get("direct_name_trigger", False), "queue_remaining": reply_queue_size(group_id), "search_notice_sent": search_notice_sent})
        result = reply_processing.proactive_sent_result(
            proactive,
            queue_remaining=reply_queue_size(group_id),
            search_notice_sent=search_notice_sent,
        )
        content_analysis_log(
            "proactive_reply_sent",
            group_id,
            **content_analysis_user_fields(event),
            reply=reply_to_analysis_text(reply),
            score=proactive.get("score"),
            reasons=proactive.get("reasons", []),
            direct_name_trigger=proactive.get("direct_name_trigger", False),
            queue_remaining=reply_queue_size(group_id),
            search_notice_sent=search_notice_sent,
        )
        record_proactive_runtime_result(group_id, event, proactive, result=result, output_len=len(reply), suppressed_duplicate=False, duration_start=start, perf=perf)
        return result
    return complete_proactive_skip(
        group_id,
        event,
        proactive,
        duration_start=start,
        perf=perf,
    )


async def process_one_reply_intent(group_id: int) -> dict[str, Any]:
    async with reply_lock_for_group(group_id):
        queued_intent = dequeue_reply_intent(group_id)
        if queued_intent is None:
            return {"ok": True, "ignored": "reply_queue_empty"}

        kind = str(queued_intent.get("kind") or "")
        interaction_id = str(queued_intent.get("_perf_interaction_id") or "")
        queue_wait_ms = runtime_elapsed_ms(queued_intent.get("_perf_enqueued_at"))
        queued_intent["_perf_queue_wait_ms"] = queue_wait_ms
        emit_perf_stat(
            "reply_intent_dequeued",
            group_id=group_id,
            interaction_id=interaction_id,
            kind=kind,
            queue_wait_ms=queue_wait_ms,
            direct_queue_size=reply_queue_size_by_kind(group_id, "direct"),
            proactive_queue_size=reply_queue_size_by_kind(group_id, "proactive"),
        )
        if kind == "direct":
            return await process_direct_reply_intent(group_id, queued_intent)

        if kind == "proactive":
            return await process_proactive_reply_intent(group_id, queued_intent)

        return {"ok": True, "ignored": "unknown_reply_intent", "kind": kind}


async def process_reply_intent(group_id: int, intent: dict[str, Any]) -> dict[str, Any]:
    """Compatibility wrapper: process one queued reply intent immediately."""
    return await process_one_reply_intent(group_id)


def reply_worker_idle(group_id: int) -> bool:
    task = _reply_workers_by_group.get(group_id)
    return task is None or task.done()


async def drain_reply_queue(group_id: int) -> None:
    worker_start = runtime_now()
    processed_count = 0
    error_count = 0
    log({"type": "reply_worker_started", "group_id": group_id})
    emit_perf_stat("reply_worker_started", group_id=group_id, direct_queue_size=reply_queue_size_by_kind(group_id, "direct"), proactive_queue_size=reply_queue_size_by_kind(group_id, "proactive"))
    try:
        while True:
            result = await process_one_reply_intent(group_id)
            log({"type": "reply_worker_processed", "group_id": group_id, "result": result})
            if result.get("ignored") == "reply_queue_empty":
                break
            processed_count += 1
            if not result.get("ok", True):
                error_count += 1
    except Exception as exc:
        error_count += 1
        log({"type": "reply_worker_error", "group_id": group_id, "error": type(exc).__name__, "message": str(exc)})
    finally:
        current = asyncio.current_task()
        if _reply_workers_by_group.get(group_id) is current:
            _reply_workers_by_group.pop(group_id, None)
        queue_remaining = reply_queue_size(group_id)
        log({"type": "reply_worker_drained", "group_id": group_id, "queue_remaining": queue_remaining})
        emit_perf_stat(
            "reply_worker_drained",
            group_id=group_id,
            duration_ms=runtime_elapsed_ms(worker_start),
            processed_count=processed_count,
            error_count=error_count,
            queue_remaining=queue_remaining,
            direct_queue_size=reply_queue_size_by_kind(group_id, "direct"),
            proactive_queue_size=reply_queue_size_by_kind(group_id, "proactive"),
        )
        if queue_remaining > 0 and reply_worker_idle(group_id):
            ensure_reply_worker(group_id)


def ensure_reply_worker(group_id: int) -> dict[str, Any]:
    task = _reply_workers_by_group.get(group_id)
    if task is not None and not task.done():
        return {
            "ok": True,
            "queued": True,
            "group_id": group_id,
            "queue_size": reply_queue_size(group_id),
            "worker": "already_running",
        }
    task = asyncio.create_task(drain_reply_queue(group_id))
    _reply_workers_by_group[group_id] = task
    log({"type": "reply_worker_scheduled", "group_id": group_id, "queue_size": reply_queue_size(group_id)})
    return {
        "ok": True,
        "queued": True,
        "group_id": group_id,
        "queue_size": reply_queue_size(group_id),
        "worker": "scheduled",
    }


async def wait_reply_worker(group_id: int) -> None:
    task = _reply_workers_by_group.get(group_id)
    if task is not None:
        await task


async def wait_ocr_context_tasks(group_id: int | None = None) -> None:
    tasks = list(_ocr_context_tasks)
    if not tasks:
        return
    await asyncio.gather(*tasks, return_exceptions=True)


app = FastAPI(title="QQ Hermes Bridge")
_last_reply_at = 0.0
_lock = asyncio.Lock()
_outbound_lock = asyncio.Lock()
_recent_messages: deque[dict[str, Any]] = deque(maxlen=CONTEXT_MAX_MESSAGES)
if CONTEXT_PERSIST_ENABLED:
    load_context_cache()
runtime_stat(
    "bridge_start",
    pid=os.getpid(),
    allowed_group_count=len(ALLOWED_GROUP_IDS),
    target_group_id=TARGET_GROUP_ID,
    runtime_stats_enabled=RUNTIME_STATS_ENABLED,
    prometheus_enabled=PROMETHEUS_ENABLED,
    prometheus_group_id_label_enabled=PROMETHEUS_INCLUDE_GROUP_ID_LABEL,
    context_persist_enabled=CONTEXT_PERSIST_ENABLED,
    proactive_enabled=PROACTIVE_ENABLED,
    group_sessions_enabled=HERMES_GROUP_SESSIONS_ENABLED,
)


def require_inbound_auth(req: Request) -> None:
    headers = getattr(req, "headers", {})
    if not app_helpers.request_is_authorized(headers, BRIDGE_INBOUND_TOKEN):
        raise HTTPException(status_code=401, detail="unauthorized")


@app.get("/health")
async def health(req: Request) -> dict[str, Any]:
    detailed = bool(BRIDGE_INBOUND_TOKEN) and app_helpers.request_is_authorized(req.headers, BRIDGE_INBOUND_TOKEN)
    return app_helpers.health_response(
        target_group_id=TARGET_GROUP_ID,
        allowed_group_ids=ALLOWED_GROUP_IDS,
        bot_qq=BOT_QQ,
        onebot_http_url=ONEBOT_HTTP_URL,
        detailed=detailed,
    )


@app.get("/metrics", response_class=PlainTextResponse)
async def prometheus_metrics() -> PlainTextResponse:
    if not PROMETHEUS_ENABLED:
        raise HTTPException(status_code=404, detail="metrics disabled")
    return PlainTextResponse(metrics.generate_latest(), media_type=metrics.CONTENT_TYPE)


def build_search_command_prompt(query: str, group_id: int | None = None) -> str:
    return commands.build_search_command_prompt(
        query,
        date_context=current_date_context(),
        knowledge=search_knowledge_for_prompt(group_id),
    )


def build_search_command_reply(query: str, group_id: int | None = None) -> str:
    clean = commands.clean_query(query)
    if not clean:
        return "用法：/search 你要查的内容"
    return finalize_reply(run_search_command_search(clean, group_id))


def build_deepseek_command_prompt(query: str, search_result: str, group_id: int | None = None) -> str:
    return commands.build_deepseek_command_prompt(
        query,
        search_result,
        date_context=current_date_context(),
        knowledge=search_knowledge_for_prompt(group_id),
        max_reply_chars=MAX_REPLY_CHARS,
    )


def _whole_clause_fit(text: str, limit: int) -> str:
    """最后安全网：按完整短句保留，避免从长回复中硬截半句话。"""
    return text_utils.whole_clause_fit(
        text,
        limit,
        punctuation_style_enabled=PUNCTUATION_STYLE_ENABLED,
    )


def compress_deepseek_reply(query: str, draft: str, search_result: str, group_id: int | None = None) -> str:
    start = runtime_now()
    budget = max(120, MAX_REPLY_CHARS - 20)
    prompt = commands.build_compress_deepseek_prompt(
        query=query,
        draft=draft,
        search_result=search_result,
        budget=budget,
    )
    cmd = build_hermes_cmd(prompt, group_id=group_id, use_group_session=False, model=DEEPSEEK_COMMAND_MODEL, provider=DEEPSEEK_COMMAND_PROVIDER)
    try:
        p = subprocess.run(cmd, text=True, capture_output=True, timeout=HERMES_TIMEOUT, cwd=str(BASE_DIR))
    except Exception as exc:
        emit_perf_stat("deepseek_command_phase", phase="compress", group_id=group_id, duration_ms=runtime_elapsed_ms(start), ok=False, error=type(exc).__name__, draft_len=len(draft or ""), search_result_len=len(search_result or ""))
        log({"type": "deepseek_command_compress_error", "error": type(exc).__name__, "message": str(exc)})
        return ""
    emit_perf_stat(
        "deepseek_command_phase",
        phase="compress",
        group_id=group_id,
        duration_ms=runtime_elapsed_ms(start),
        ok=p.returncode == 0,
        returncode=p.returncode,
        draft_len=len(draft or ""),
        search_result_len=len(search_result or ""),
        output_len=len(p.stdout or ""),
    )
    if p.returncode != 0:
        log({"type": "deepseek_command_compress_error", "returncode": p.returncode, "stdout": (p.stdout or "")[-800:], "stderr": (p.stderr or "")[-800:]})
        return ""
    return prepare_reply_text(strip_session_footer(p.stdout or ""))


def finalize_deepseek_command_reply(raw: str, query: str, search_result: str, group_id: int | None = None) -> str:
    return commands.finalize_deepseek_command_reply(
        raw,
        query=query,
        search_result=search_result,
        max_reply_chars=MAX_REPLY_CHARS,
        strip_session_footer_fn=strip_session_footer,
        prepare_reply_text_fn=prepare_reply_text,
        empty_reply_fn=lambda raw_text, query_text: pick_template("empty_reply", raw_text or query_text),
        compress_fn=compress_deepseek_reply,
        whole_clause_fit_fn=_whole_clause_fit,
        group_id=group_id,
    )


def build_deepseek_command_reply(query: str, group_id: int | None = None) -> str:
    clean = commands.clean_query(query)
    if not clean:
        return "用法：/deepseek 你要深度搜索/分析的问题"
    search_start = runtime_now()
    search_result = run_web_search(clean)
    emit_perf_stat("deepseek_command_phase", phase="search", group_id=group_id, duration_ms=runtime_elapsed_ms(search_start), ok=bool(search_result), query_len=len(clean), search_result_len=len(search_result or ""))
    prompt = build_deepseek_command_prompt(clean, search_result, group_id)
    cmd = build_hermes_cmd(prompt, group_id=group_id, use_group_session=False, model=DEEPSEEK_COMMAND_MODEL, provider=DEEPSEEK_COMMAND_PROVIDER)
    draft_start = runtime_now()
    try:
        p = subprocess.run(cmd, text=True, capture_output=True, timeout=HERMES_TIMEOUT, cwd=str(BASE_DIR))
    except Exception as exc:
        emit_perf_stat("deepseek_command_phase", phase="draft", group_id=group_id, duration_ms=runtime_elapsed_ms(draft_start), ok=False, error=type(exc).__name__, query_len=len(clean), search_result_len=len(search_result or ""))
        log({"type": "deepseek_command_error", "error": type(exc).__name__, "message": str(exc)})
        return "深度思考这次跑挂了 稍后再试"
    emit_perf_stat(
        "deepseek_command_phase",
        phase="draft",
        group_id=group_id,
        duration_ms=runtime_elapsed_ms(draft_start),
        ok=p.returncode == 0,
        returncode=p.returncode,
        query_len=len(clean),
        search_result_len=len(search_result or ""),
        output_len=len(p.stdout or ""),
        model_configured=bool(DEEPSEEK_COMMAND_MODEL),
        provider_configured=bool(DEEPSEEK_COMMAND_PROVIDER),
    )
    if p.returncode != 0:
        log({"type": "deepseek_command_error", "returncode": p.returncode, "stdout": (p.stdout or "")[-800:], "stderr": (p.stderr or "")[-800:]})
        return "深度思考这次没跑通 稍后再试"
    return finalize_deepseek_command_reply(p.stdout or "", clean, search_result, group_id)


def select_command_action(event: dict[str, Any], user_text: str) -> dict[str, Any] | None:
    return handlers.command_action_for_text(
        user_text,
        event=event,
        group_id=group_id_from_event(event),
        is_context_command_fn=is_context_command,
        is_search_command_fn=is_search_command,
        search_command_query_fn=search_command_query,
        is_deepseek_command_fn=is_deepseek_command,
        deepseek_command_query_fn=deepseek_command_query,
        is_jrrp_command_fn=is_jrrp_command,
        sender_name_fn=_sender_name,
        build_context_reply_fn=build_context_command_reply,
        build_search_reply_fn=build_search_command_reply,
        build_deepseek_reply_fn=build_deepseek_command_reply,
        build_jrrp_reply_fn=build_jrrp_reply,
    )


async def execute_command_action(group_id: int | None, event: dict[str, Any], command_action: dict[str, Any]) -> dict[str, Any]:
    start = runtime_now()
    interaction_id = str(command_action.get("interaction_id") or runtime_interaction_id(event))
    if command_action["kind"] == "threaded_immediate":
        if command_action.get("command") == "search" or command_action.get("trigger") == "search_command":
            reply = await asyncio.to_thread(build_search_command_reply, command_action["query"], group_id)
        else:
            reply = await asyncio.to_thread(build_deepseek_command_reply, command_action["query"], group_id)
    else:
        reply = command_action["reply"]
    result = await send_immediate_reply(
        group_id,
        reply,
        event,
        command_action["trigger"],
        command_action["log_type"],
        remember_context=bool(command_action.get("remember_context")),
        **command_action.get("extra", {}),
    )
    command = str(command_action.get("command") or command_action.get("trigger") or "")
    increment_runtime_counter("commands_total")
    if result.get("ok"):
        increment_runtime_counter("command_success")
    else:
        increment_runtime_counter("command_errors")
    emit_perf_stat(
        "command_result",
        interaction_id=interaction_id,
        group_id=group_id,
        user_hash=runtime_user_hash(event.get("user_id")),
        command=command,
        trigger=command_action.get("trigger"),
        threaded=command_action.get("kind") == "threaded_immediate",
        ok=bool(result.get("ok")),
        output_len=len(reply or ""),
        duration_ms=runtime_stats.duration_ms(start),
        e2e_ms=interaction_e2e_ms(interaction_id, _interaction_started_at.get(interaction_id)),
    )
    return result


def select_proactive_route_action(event: dict[str, Any]) -> dict[str, Any]:
    return handlers.proactive_action_for_non_direct_reply(
        event,
        proactive=update_proactive_score(event),
        group_id=group_id_from_event(event),
        enqueue_reply_intent_fn=enqueue_reply_intent,
        log_fn=log,
    )


def select_direct_route_action(event: dict[str, Any], user_text: str, media_context: str = "") -> dict[str, Any]:
    return handlers.direct_action_for_event(
        event,
        user_text=user_text,
        skip_unclear_mentions=SKIP_UNCLEAR_MENTIONS,
        should_skip_unclear_mention_fn=should_skip_unclear_mention,
        should_rate_limit_fn=should_rate_limit_direct_enqueue,
        group_id_fn=group_id_from_event,
        is_reply_to_me_fn=is_reply_to_me,
        is_at_me_fn=is_at_me,
        is_name_mention_fn=is_name_mention,
        enqueue_reply_intent_fn=enqueue_reply_intent,
        log_fn=log,
        media_context=media_context,
    )


async def execute_route_action(action: dict[str, Any]) -> dict[str, Any]:
    if action.get("kind") == "process_reply_intent":
        return ensure_reply_worker(action["group_id"])
    return action


@app.post("/onebot")
async def onebot_event(req: Request) -> dict[str, Any]:
    global _last_reply_at
    request_start = runtime_now()
    require_inbound_auth(req)
    event = await req.json()
    interaction_id = runtime_interaction_id(event)
    remember_interaction_start(interaction_id, request_start)
    event_record = runtime_event_record(event)
    emit_perf_stat("interaction_received", interaction_id=interaction_id, duration_ms=runtime_elapsed_ms(request_start), **event_record)
    increment_runtime_counter("events_total")
    if event.get("post_type") == "message" and event.get("message_type") == "group" and is_allowed_group(event):
        increment_runtime_counter("allowed_group_messages")
    runtime_stat("inbound_event", interaction_id=interaction_id, **event_record)
    log(handlers.event_log_record(event))
    if event.get("post_type") == "message" and event.get("message_type") == "group" and not mark_event_seen(event):
        increment_runtime_counter("duplicate_events")
        increment_runtime_counter("ignored_total")
        runtime_route_decision("ignored", interaction_id=interaction_id, group_id=event.get("group_id"), user_hash=runtime_user_hash(event.get("user_id")), reason="duplicate_event", duration_ms=runtime_elapsed_ms(request_start))
        maybe_log_runtime_summary()
        log({"type": "ignored", "reason": "duplicate_event", "group_id": event.get("group_id"), "message_id": event.get("message_id")})
        return {"ok": True, "ignored": "duplicate_event"}
    precheck = handlers.precheck_group_message(event, is_allowed_group_fn=is_allowed_group)
    if precheck is not None:
        increment_runtime_counter("ignored_total")
        runtime_route_decision("ignored", interaction_id=interaction_id, group_id=event.get("group_id"), user_hash=runtime_user_hash(event.get("user_id")), reason=precheck.get("ignored", "precheck"), duration_ms=runtime_elapsed_ms(request_start))
        maybe_log_runtime_summary()
        return precheck

    group_id = group_id_from_event(event)
    content_analysis_log(
        "inbound_message",
        group_id,
        **content_analysis_user_fields(event),
        message=message_to_analysis_text(event, include_at=False),
        segment_types=segment_types_for_analysis(event),
    )

    user_text = message_to_text(event.get("message"))
    command_action = select_command_action(event, user_text)
    if command_action is not None:
        remember_message_and_schedule_context_ocr(event)
        group_id = group_id_from_event(event)
        command_action["interaction_id"] = interaction_id
        runtime_route_decision("command", interaction_id=interaction_id, group_id=group_id, user_hash=runtime_user_hash(event.get("user_id")), command=command_action.get("command") or command_action.get("trigger"), trigger=command_action.get("trigger"), duration_ms=runtime_elapsed_ms(request_start))
        result = await execute_command_action(group_id, event, command_action)
        maybe_log_runtime_summary()
        return result

    if not should_trigger_direct_reply(event):
        remember_message_and_schedule_context_ocr(event)
        action = select_proactive_route_action(event)
        proactive_score = action.get("proactive_score") or (action.get("intent") or {}).get("proactive", {}).get("score")
        proactive_payload = (action.get("intent") or {}).get("proactive") or {}
        if action.get("kind") == "process_reply_intent":
            increment_runtime_counter("proactive_triggers")
            runtime_route_decision("proactive", interaction_id=interaction_id, group_id=event.get("group_id"), user_hash=runtime_user_hash(event.get("user_id")), score=proactive_payload.get("score"), reasons=proactive_payload.get("reasons", []), blocked=proactive_payload.get("blocked", ""), queued=True, duration_ms=runtime_elapsed_ms(request_start))
            result = await execute_route_action(action)
            maybe_log_runtime_summary()
            return result
        increment_runtime_counter("ignored_total")
        runtime_route_decision("ignored", interaction_id=interaction_id, group_id=event.get("group_id"), user_hash=runtime_user_hash(event.get("user_id")), reason=action.get("ignored", "not_at_me"), blocked=action.get("blocked", ""), score=proactive_score, duration_ms=runtime_elapsed_ms(request_start))
        maybe_log_runtime_summary()
        return action

    user_text = handlers.prepare_direct_user_text(message_to_text(event.get("message")))
    media_data = await recognize_media_for_event(event, route="direct")
    media_context = str(media_data.get("media_context") or "（当前消息没有图片识别结果）")
    base_context_text = message_to_text(event.get("message"), include_at=False) or "（非文本消息）"
    remember_message(
        event,
        ocr_context_text(base_context_text, media_context),
        text_without_ocr=base_context_text,
        ocr_text_nonpersistent=OCR_INCLUDE_IN_CONTEXT and not OCR_PERSIST_TEXT_IN_CONTEXT,
    )
    action = select_direct_route_action(event, user_text, media_context)
    if action.get("kind") == "process_reply_intent":
        increment_runtime_counter("direct_requests")
        runtime_route_decision("direct", interaction_id=interaction_id, group_id=event.get("group_id"), user_hash=runtime_user_hash(event.get("user_id")), trigger=(action.get("intent") or {}).get("trigger", "at"), queued=True, duration_ms=runtime_elapsed_ms(request_start))
        result = await execute_route_action(action)
        maybe_log_runtime_summary()
        return result
    increment_runtime_counter("ignored_total")
    runtime_route_decision("ignored", interaction_id=interaction_id, group_id=event.get("group_id"), user_hash=runtime_user_hash(event.get("user_id")), reason=action.get("ignored", "direct_not_queued"), duration_ms=runtime_elapsed_ms(request_start))
    maybe_log_runtime_summary()
    return action



class TestRequest(BaseModel):
    text: str = "测试一下 @ 回复"
    user_id: int = 10000
    nickname: str = "测试用户"
    group_id: int = TARGET_GROUP_ID


@app.post("/test")
async def test(request: Request, req: TestRequest) -> dict[str, Any]:
    require_inbound_auth(request)
    fake = {
        "post_type": "message",
        "message_type": "group",
        "group_id": req.group_id,
        "user_id": req.user_id,
        "self_id": int(BOT_QQ or 0),
        "sender": {"nickname": req.nickname},
        "message": [{"type": "at", "data": {"qq": BOT_QQ or "0"}}, {"type": "text", "data": {"text": req.text}}],
    }
    prompt = build_prompt(fake, req.text)
    reply = await asyncio.to_thread(run_hermes, prompt)
    return {"ok": True, "reply": reply}
