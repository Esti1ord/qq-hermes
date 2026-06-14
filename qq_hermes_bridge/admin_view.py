"""Content-safe local admin view helpers for the QQ/Hermes bridge.

The admin surface is intentionally structural: it reports counts, routing labels,
and prompt-section metadata, but never returns raw chat, prompt bodies, model
outputs, OCR text, provider URLs, API-key env names/values, tokens, cookies, or
local secret paths.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from . import prompt_service

REDACTED = "[redacted]"

REPLY_ERROR_REASONS: tuple[dict[str, str], ...] = (
    {"key": "direct_generation_failures", "label": "直接回复生成失败"},
    {"key": "direct_send_errors", "label": "直接回复发送失败"},
    {"key": "send_errors", "label": "群消息发送失败"},
    {"key": "command_errors", "label": "命令处理错误"},
    {"key": "hermes_errors", "label": "Hermes 模型调用错误"},
)

_SENSITIVE_MARKERS = (
    "http://",
    "https://",
    "authorization",
    "bearer ",
    "cookie",
    "token",
    "secret",
    "passwd",
    "password",
    "api_key",
    "apikey",
)
_SECRET_TOKEN_RE = re.compile(r"(?i)\b(sk|pk|ghp|xox[baprs]?)-[a-z0-9_-]{8,}")
_URLISH_RE = re.compile(r"(?i)\b(?:[a-z0-9-]+\.)+[a-z]{2,}(?::\d+|/|\b)")
_HOST_PORT_RE = re.compile(r"(?i)\b(?:localhost|(?:\d{1,3}\.){3}\d{1,3}|\[[0-9a-f:]+\])(?::\d+|/|\b)")
_ENV_SECRET_NAME_RE = re.compile(r"\b[A-Z][A-Z0-9_]*(?:_(?:API|KEY|TOKEN|SECRET|COOKIE))(?:_[A-Z0-9]+)*\b")
_ABSOLUTE_PATH_RE = re.compile(r"^(?:/|~[/\\]|[a-zA-Z]:[/\\])")

_SECTION_SUMMARIES = {
    "runtime_date": "当前日期/相对时间提示；只展示组成，不展示完整提示词。",
    "summary_context": "生成的群聊摘要缓存会进入模型上下文；这里只展示数量和长度，不展示摘要文本。",
    "recent_context": "最近群聊上下文会进入模型上下文；这里只展示消息数量、角色计数和长度，不展示聊天内容。",
    "quoted_context": "被回复/引用消息会进入模型上下文；管理员视图不展示引用原文。",
    "current_message": "当前触发消息是直接回复的最高优先级输入；管理员视图不展示消息正文或用户标识。",
    "response_strategy": "运行时回复策略、风格限制和安全规则。",
    "media_context": "图片识别结果可作为辅助输入；管理员视图只展示 OCR 配置状态，不展示 OCR 文本或图片 URL。",
    "sender_profile": "提问者资料可作为弱线索；管理员视图不展示资料内容。",
    "mentioned_profiles": "被提及对象资料可作为弱线索；管理员视图不展示资料内容。",
    "related_profiles": "关键词相关群友资料可作为低权重线索；管理员视图不展示资料内容。",
    "self_learning": "群内用语/风格学习提示可作为低权重线索；管理员视图不展示样例或学习文本。",
    "style_examples": "内置回复风格样例与反例。",
    "persona": "基础人设与群聊提示词会进入上下文；管理员视图只展示组成，不展示内容。",
    "decision_strategy": "主动发言判断策略和沉默条件。",
    "trigger_reasons": "主动发言触发原因属于内部诊断；只展示结构和计数。",
    "proactive_examples": "内置主动发言样例与反例。",
}


def safe_display_value(value: Any, *, max_chars: int = 80) -> str:
    """Return a short display label, redacting URL/token/path-shaped values."""
    text = str(value or "").strip()
    if not text:
        return ""
    lower = text.lower()
    if any(marker in lower for marker in _SENSITIVE_MARKERS):
        return REDACTED
    if _SECRET_TOKEN_RE.search(text) or _URLISH_RE.search(text) or _HOST_PORT_RE.search(text) or _ENV_SECRET_NAME_RE.search(text):
        return REDACTED
    if _ABSOLUTE_PATH_RE.search(text):
        return REDACTED
    if len(text) > max_chars:
        return text[: max(1, max_chars - 1)] + "…"
    return text


def safe_model_provider_details(model: Any, provider: Any) -> dict[str, Any]:
    """Build content-safe model/provider display details."""
    model_text = str(model or "").strip()
    provider_text = str(provider or "").strip()
    safe_model = safe_display_value(model_text)
    safe_provider = safe_display_value(provider_text)
    return {
        "model": safe_model,
        "provider": safe_provider,
        "model_configured": bool(model_text),
        "provider_configured": bool(provider_text),
        "model_redacted": bool(model_text and safe_model == REDACTED),
        "provider_redacted": bool(provider_text and safe_provider == REDACTED),
    }


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number or number in (float("inf"), float("-inf")):
        return default
    return number


def _round_float(value: Any, digits: int = 3, default: float = 0.0) -> float:
    return round(_safe_float(value, default), digits)


def safe_counters(counters: Mapping[str, Any]) -> dict[str, int]:
    """Return runtime counters with controlled names and integer values only."""
    safe: dict[str, int] = {}
    for key, value in counters.items():
        name = re.sub(r"[^a-zA-Z0-9_:-]", "_", str(key or "unknown"))[:80]
        if not name:
            continue
        safe[name] = _safe_int(value)
    return dict(sorted(safe.items()))


def build_reply_error_summary(counters: Mapping[str, Any]) -> dict[str, Any]:
    """Aggregate stable reply error counters for /admin/state."""
    reasons = [
        {
            "key": reason["key"],
            "label": reason["label"],
            "count": _safe_int(counters.get(reason["key"])),
        }
        for reason in REPLY_ERROR_REASONS
    ]
    return {
        "total": sum(reason["count"] for reason in reasons),
        "reasons": reasons,
    }


def summarize_context(messages: Iterable[Mapping[str, Any]], summaries: Iterable[Any]) -> dict[str, Any]:
    """Summarize context buffers without exposing message or summary text."""
    message_list = [item for item in messages if isinstance(item, Mapping)]
    summary_list = list(summaries)
    human_count = 0
    bot_count = 0
    pending_bot_count = 0
    annotated_count = 0
    media_ref_count = 0
    ocr_nonpersistent_count = 0
    total_text_chars = 0
    max_text_chars = 0

    for item in message_list:
        role = str(item.get("role") or "")
        if "机器人" in role:
            bot_count += 1
            if "正在生成回复" in role:
                pending_bot_count += 1
        else:
            human_count += 1
        if str(item.get("annotation") or "").strip():
            annotated_count += 1
        refs = item.get("media_refs") or ()
        try:
            media_ref_count += len(refs)  # type: ignore[arg-type]
        except TypeError:
            media_ref_count += 0
        if item.get("ocr_text_nonpersistent"):
            ocr_nonpersistent_count += 1
        text_len = len(str(item.get("text") or ""))
        total_text_chars += text_len
        max_text_chars = max(max_text_chars, text_len)

    summary_total_chars = sum(len(str(summary or "")) for summary in summary_list)
    return {
        "recent_message_count": len(message_list),
        "human_message_count": human_count,
        "bot_message_count": bot_count,
        "pending_bot_message_count": pending_bot_count,
        "annotated_message_count": annotated_count,
        "media_ref_count": media_ref_count,
        "ocr_nonpersistent_message_count": ocr_nonpersistent_count,
        "stored_text_total_chars": total_text_chars,
        "stored_text_max_chars": max_text_chars,
        "summary_count": len(summary_list),
        "summary_total_chars": summary_total_chars,
        "content_hidden": True,
    }


def _safe_reason_label(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if ":" in text:
        prefix, detail = text.split(":", 1)
        safe_prefix = re.sub(r"[^a-zA-Z0-9_.-]", "_", prefix)[:32] or "reason"
        safe_detail = safe_display_value(detail, max_chars=32) or REDACTED
        return f"{safe_prefix}:{safe_detail}"
    return safe_display_value(text, max_chars=48) or REDACTED


def _safe_reason_labels(reasons: Any, *, limit: int = 20) -> list[str]:
    if isinstance(reasons, (str, bytes)):
        values = [reasons]
    else:
        try:
            values = list(reasons or [])
        except TypeError:
            values = []
    labels: list[str] = []
    for item in values[: max(0, int(limit or 20))]:
        label = _safe_reason_label(item)
        if label:
            labels.append(label)
    return labels


def safe_proactive_state(
    state: Mapping[str, Any],
    *,
    now: float,
    scoring: Mapping[str, Any] | None = None,
    activity: Mapping[str, Any] | None = None,
    limits: Mapping[str, Any] | None = None,
    score_model: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    scoring = scoring or {}
    activity = activity or {}
    limits = limits or {}
    score_model = score_model or {}
    sensitive_until = _safe_float(state.get("sensitive_until"), 0.0)
    reasons = _safe_reason_labels(scoring.get("reasons"))
    daily_remaining = limits.get("daily_remaining")
    return {
        "enabled": bool(score_model.get("enabled", True)),
        "score": _round_float(scoring.get("score", state.get("score"))),
        "current_window_score": _round_float(scoring.get("score", state.get("score"))),
        "last_recorded_score": _round_float(state.get("score")),
        "heat": _round_float(scoring.get("heat")),
        "opening_score": _round_float(scoring.get("opening_score")),
        "threshold": _round_float(scoring.get("threshold", score_model.get("threshold"))),
        "threshold_source": safe_display_value(scoring.get("threshold_source") or score_model.get("threshold_source") or "default", max_chars=32),
        "should_trigger": bool(scoring.get("should_trigger", False)),
        "blocked": safe_display_value(scoring.get("blocked") or "", max_chars=48),
        "direct_name_trigger": bool(scoring.get("direct_name_trigger", False)),
        "reasons": reasons,
        "reason_count": len(reasons),
        "score_scale": "0-100",
        "score_model": {
            "mode": safe_display_value(score_model.get("mode") or "bounded_sliding_window", max_chars=48) or "bounded_sliding_window",
            "scale": "0-100",
            "scale_min": _round_float(score_model.get("scale_min"), default=0.0),
            "scale_max": _round_float(score_model.get("scale_max"), default=100.0),
            "window_seconds": _round_float(score_model.get("window_seconds")),
            "threshold": _round_float(score_model.get("threshold", scoring.get("threshold"))),
            "default_threshold": _round_float(score_model.get("default_threshold")),
            "threshold_source": safe_display_value(score_model.get("threshold_source") or scoring.get("threshold_source") or "default", max_chars=32),
            "legacy_accumulation": False,
            "content_hidden": True,
        },
        "activity": {
            "window_seconds": _round_float(activity.get("window_seconds")),
            "message_count": _safe_int(activity.get("message_count")),
            "speaker_count": _safe_int(activity.get("speaker_count")),
            "dominant_speaker_share": _round_float(activity.get("dominant_speaker_share")),
            "max_consecutive_same_speaker": _safe_int(activity.get("max_consecutive_same_speaker")),
            "content_hidden": True,
        },
        "limits": {
            "group_cooldown_seconds": _round_float(limits.get("group_cooldown_seconds")),
            "group_cooldown_remaining_seconds": _safe_int(limits.get("group_cooldown_remaining_seconds")),
            "daily_limit_per_group": _safe_int(limits.get("daily_limit_per_group")),
            "daily_remaining": None if daily_remaining is None else _safe_int(daily_remaining),
            "rate_limit_window_seconds": _round_float(limits.get("rate_limit_window_seconds")),
            "rate_limit_max_replies": _safe_int(limits.get("rate_limit_max_replies")),
            "rate_limit_recent_replies": _safe_int(limits.get("rate_limit_recent_replies")),
            "rate_limit_reset_seconds": _safe_int(limits.get("rate_limit_reset_seconds")),
            "sensitive_cooldown_remaining_seconds": _safe_int(limits.get("sensitive_cooldown_remaining_seconds")),
        },
        "daily_count": _safe_int(state.get("daily_count"), 0),
        "sensitive_active": bool(sensitive_until and sensitive_until > now),
        "content_hidden": True,
    }


def _request_for_kind(
    kind: str,
    *,
    group_id: int | None,
    max_prompt_chars: int,
    direct_prompt_profile: str = "rich",
    direct_prompt_total_budget_chars: int | None = None,
) -> prompt_service.PromptRequest:
    if kind == "proactive":
        return prompt_service.build_proactive_prompt_request(
            group_id=group_id,
            date_context="hidden",
            context_summaries="hidden",
            recent_context="hidden",
            persona="hidden",
            reasons=["hidden"],
        )
    return prompt_service.build_direct_prompt_request(
        group_id=group_id,
        date_context="hidden",
        context_summaries="hidden",
        recent_context="hidden",
        reply_context="hidden",
        reply_to_bot_note="hidden",
        nick="hidden",
        user_id="hidden",
        mentioned_labels="hidden",
        user_text="hidden",
        person_profile="hidden",
        mentioned_profiles="hidden",
        related_profiles="hidden",
        persona="hidden",
        max_prompt_chars=max_prompt_chars,
        style_hint="hidden",
        media_context="hidden",
        learning_context="hidden",
        direct_prompt_profile=direct_prompt_profile,
        total_budget_chars=direct_prompt_total_budget_chars,
    )


def _section_metrics(key: str, *, context_stats: Mapping[str, Any], ocr_enabled: bool, self_learning_enabled: bool) -> dict[str, Any]:
    if key == "summary_context":
        return {
            "summary_count": _safe_int(context_stats.get("summary_count")),
            "summary_total_chars": _safe_int(context_stats.get("summary_total_chars")),
        }
    if key == "recent_context":
        return {
            "recent_message_count": _safe_int(context_stats.get("recent_message_count")),
            "human_message_count": _safe_int(context_stats.get("human_message_count")),
            "bot_message_count": _safe_int(context_stats.get("bot_message_count")),
            "pending_bot_message_count": _safe_int(context_stats.get("pending_bot_message_count")),
            "stored_text_total_chars": _safe_int(context_stats.get("stored_text_total_chars")),
        }
    if key == "media_context":
        return {
            "ocr_enabled": bool(ocr_enabled),
            "media_ref_count": _safe_int(context_stats.get("media_ref_count")),
            "ocr_text_hidden": True,
        }
    if key == "self_learning":
        return {"enabled": bool(self_learning_enabled), "examples_hidden": True}
    if key in {"current_message", "quoted_context"}:
        return {"raw_text_hidden": True}
    if key in {"sender_profile", "mentioned_profiles", "related_profiles", "persona"}:
        return {"content_hidden": True}
    return {}


def _prompt_kind_overview(
    kind: str,
    *,
    group_id: int | None,
    context_stats: Mapping[str, Any],
    max_prompt_chars: int,
    ocr_enabled: bool,
    self_learning_enabled: bool,
    direct_prompt_profile: str = "rich",
    direct_prompt_total_budget_chars: int | None = None,
) -> dict[str, Any]:
    request = _request_for_kind(
        kind,
        group_id=group_id,
        max_prompt_chars=max_prompt_chars,
        direct_prompt_profile=direct_prompt_profile,
        direct_prompt_total_budget_chars=direct_prompt_total_budget_chars,
    )
    sections: list[dict[str, Any]] = []
    for section in request.sections:
        budget = prompt_service._budget_for_section(request.kind, section, profile=request.profile)  # noqa: SLF001 - prompt metadata only; no body exposed.
        sections.append({
            "key": section.key,
            "title": section.title,
            "source": section.source,
            "priority": section.priority,
            "budget_chars": budget,
            "summary": _SECTION_SUMMARIES.get(section.key, "该组成部分会进入模型上下文；管理员视图不展示原文。"),
            "metrics": _section_metrics(
                section.key,
                context_stats=context_stats,
                ocr_enabled=ocr_enabled,
                self_learning_enabled=self_learning_enabled,
            ),
            "content_hidden": True,
        })
    return {
        "kind": request.kind,
        "section_count": len(sections),
        "rules_count": len(request.rules),
        "max_prompt_chars": max_prompt_chars if request.kind == "direct" else None,
        "profile": request.profile,
        "total_budget_chars": request.total_budget_chars if request.kind == "direct" else None,
        "output_contract": "group_text_only" if request.kind == "direct" else "group_text_or_silent_marker",
        "sections": sections,
    }


def build_context_composition_overview(
    *,
    group_id: int | None,
    context_stats: Mapping[str, Any],
    max_prompt_chars: int,
    ocr_enabled: bool,
    self_learning_enabled: bool,
    direct_prompt_profile: str = "rich",
    direct_prompt_total_budget_chars: int | None = None,
) -> dict[str, Any]:
    """Return prompt composition metadata without prompt/body content."""
    return {
        "selected_group_id": group_id,
        "content_hidden": True,
        "direct": _prompt_kind_overview(
            "direct",
            group_id=group_id,
            context_stats=context_stats,
            max_prompt_chars=max_prompt_chars,
            ocr_enabled=ocr_enabled,
            self_learning_enabled=self_learning_enabled,
            direct_prompt_profile=direct_prompt_profile,
            direct_prompt_total_budget_chars=direct_prompt_total_budget_chars,
        ),
        "proactive": _prompt_kind_overview(
            "proactive",
            group_id=group_id,
            context_stats=context_stats,
            max_prompt_chars=max_prompt_chars,
            ocr_enabled=ocr_enabled,
            self_learning_enabled=self_learning_enabled,
            direct_prompt_profile=direct_prompt_profile,
            direct_prompt_total_budget_chars=direct_prompt_total_budget_chars,
        ),
    }


def build_admin_html() -> str:
    """Return a dependency-free admin page that renders /admin/state safely."""
    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>QQ Hermes 本地状态</title>
  <style>
    :root { color-scheme: light dark; font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    body { margin: 0; background: #0f172a; color: #e2e8f0; }
    header { padding: 24px; background: linear-gradient(135deg, #1e293b, #111827); border-bottom: 1px solid #334155; }
    h1 { margin: 0 0 8px; font-size: 24px; }
    h2 { margin: 0 0 12px; font-size: 18px; }
    h3 { margin: 14px 0 8px; font-size: 16px; }
    p { margin: 4px 0; color: #94a3b8; }
    button, select, input, textarea { padding: 8px 12px; border: 1px solid #475569; border-radius: 8px; background: #1e293b; color: #e2e8f0; }
    textarea { min-height: 80px; resize: vertical; }
    input, textarea { box-sizing: border-box; width: 100%; }
    form.admin-memory-form { display: grid; gap: 10px; grid-template-columns: minmax(150px, 220px) minmax(100px, 140px) 1fr auto; align-items: end; margin: 12px 0 16px; }
    form.admin-memory-form label { display: grid; gap: 6px; font-size: 13px; }
    .actions { display: flex; flex-wrap: wrap; gap: 6px; }
    .danger { border-color: #7f1d1d; }
    .memory-preview { max-width: 520px; }
    @media (max-width: 800px) { form.admin-memory-form { grid-template-columns: 1fr; } }
    button { cursor: pointer; }
    button:hover { background: #334155; }
    label { color: #cbd5e1; font-weight: 600; }
    main { padding: 16px; display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); }
    section { border: 1px solid #334155; border-radius: 12px; padding: 16px; background: #111827; box-shadow: 0 10px 30px rgba(0, 0, 0, .18); }
    dl { display: grid; grid-template-columns: minmax(130px, 42%) 1fr; gap: 8px 12px; margin: 0; }
    dt { color: #94a3b8; }
    dd { margin: 0; overflow-wrap: anywhere; }
    table { width: 100%; border-collapse: collapse; font-size: 14px; }
    th, td { border-bottom: 1px solid #334155; padding: 8px 6px; text-align: left; vertical-align: top; }
    th { color: #cbd5e1; font-weight: 600; }
    pre { margin: 0; max-height: 520px; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; color: #cbd5e1; }
    code, pre { background: #020617; border: 1px solid #334155; border-radius: 8px; padding: 10px; }
    .toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: 10px 12px; margin-top: 14px; }
    .status-grid, .metric-grid { display: grid; gap: 10px; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); margin-top: 14px; }
    .status-pill, .metric-card { border: 1px solid #334155; border-radius: 10px; background: #0b1220; padding: 12px; }
    .status-pill span, .metric-label { display: block; color: #94a3b8; font-size: 12px; margin-bottom: 4px; }
    .status-pill strong, .metric-value { display: block; font-size: 20px; font-weight: 700; overflow-wrap: anywhere; }
    .metric-desc { margin-top: 6px; font-size: 12px; color: #94a3b8; }
    .delta { display: inline-block; margin-top: 6px; font-size: 12px; }
    .delta.up { color: #86efac; }
    .delta.down { color: #fca5a5; }
    .delta.flat { color: #94a3b8; }
    .muted { color: #94a3b8; }
    .ok { color: #86efac; }
    .warn { color: #fcd34d; }
    .error-box { margin-top: 12px; padding: 10px; border: 1px solid #92400e; border-radius: 8px; background: #451a03; color: #fed7aa; white-space: pre-wrap; overflow-wrap: anywhere; }
    .hidden { display: none; }
    .full { grid-column: 1 / -1; }
    .composition-summary { display: grid; gap: 8px; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); margin: 10px 0 14px; }
    .summary-chip { border: 1px solid #334155; border-radius: 8px; background: #0b1220; padding: 10px; }
    .summary-chip span { display: block; color: #94a3b8; font-size: 12px; }
    .summary-chip strong { display: block; margin-top: 2px; }
  </style>
</head>
<body>
  <header>
    <h1>QQ Hermes 本地数据查看</h1>
    <p>实时查看运行状态、当前模型路由、输入给机器人的提示词组成概览，以及手动管理记忆 / 自学习内容。</p>
    <p>安全策略：本页不展示原始聊天、完整 prompt、模型输出、OCR 文本、Provider URL、Token/Cookie 或本地密钥路径。</p>
    <div class="toolbar">
      <button id="refresh" type="button">立即刷新</button>
      <label for="group-select">查看群</label>
      <select id="group-select" aria-label="选择群"><option value="">加载中…</option></select>
      <span id="status" class="muted" aria-live="polite"></span>
    </div>
    <div class="status-grid" aria-label="实时连接状态">
      <div class="status-pill"><span>连接状态</span><strong id="connection-state">初始化</strong></div>
      <div class="status-pill"><span>最近成功刷新</span><strong id="last-success">尚未成功</strong></div>
      <div class="status-pill"><span>成功刷新次数</span><strong id="refresh-count">0</strong></div>
      <div class="status-pill"><span>当前查看群</span><strong id="selected-group-label">（待加载）</strong></div>
    </div>
  </header>
  <main>
    <section><h2>实时连接状态</h2><div id="connection"></div><div id="error-details" class="error-box hidden" role="alert"></div></section>
    <section><h2>运行状态</h2><div id="runtime"></div></section>
    <section><h2>主动发言评分</h2><div id="proactive"></div></section>
    <section><h2>模型 / Provider</h2><div id="model"></div></section>
    <section><h2>OCR / 媒体</h2><div id="ocr"></div></section>
    <section class="full"><h2>指标趋势</h2><div id="metrics" class="metric-grid"></div></section>
    <section class="full"><h2>回复错误原因</h2><div id="reply-error-reasons"></div></section>
    <section class="full"><h2>群状态</h2><div id="groups"></div></section>
    <section class="full">
      <h2>记忆 / 自学习管理</h2>
      <p class="muted">用于删除/停用不合适的学习样例，或添加人工提示、记忆、梗/风格条目。列表只展示短预览和安全元数据。</p>
      <form id="memory-add-form" class="admin-memory-form">
        <label>类型
          <select id="memory-entry-type">
            <option value="memory">记忆</option>
            <option value="prompt_guidance">Prompt 指引</option>
            <option value="self_learning">自学习/梗</option>
          </select>
        </label>
        <label>初始权重
          <input id="memory-entry-weight" type="number" min="0.1" max="20" step="0.1" value="1">
        </label>
        <label>内容
          <textarea id="memory-entry-text" maxlength="600" placeholder="添加给 Esti 使用的人工记忆或提示；不要填写 token、URL、Cookie、图片链接、用户 ID 等敏感内容。"></textarea>
        </label>
        <button id="memory-add" type="submit">添加条目</button>
      </form>
      <div id="memory-status" class="muted" aria-live="polite"></div>
      <div id="memory"></div>
    </section>
    <section class="full"><h2>输入给机器人的提示词组成概览</h2><div id="composition"></div></section>
    <section class="full"><h2>当前 /admin/state JSON（只读）</h2><pre id="state-json" aria-label="content-safe admin state json">等待首次刷新…</pre></section>
  </main>
<script>
const $ = (id) => document.getElementById(id);
const REFRESH_INTERVAL_MS = 5000;
let selectedGroupId = null;
let lastSuccessfulRefreshAt = null;
let successRefreshCount = 0;
let connectionState = '初始化';
let lastErrorDetail = '';
let previousMetricValues = null;

function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }
function text(value) { return value === null || value === undefined || value === '' ? '（空）' : String(value); }
function numberValue(value) {
  const num = Number(value || 0);
  return Number.isFinite(num) ? num : 0;
}
function addKV(dl, key, value) {
  const dt = document.createElement('dt');
  const dd = document.createElement('dd');
  dt.textContent = key;
  dd.textContent = text(value);
  dl.append(dt, dd);
}
function renderKV(target, rows) {
  clear(target);
  const dl = document.createElement('dl');
  rows.forEach(([key, value]) => addKV(dl, key, value));
  target.appendChild(dl);
}
function formatLocalTime(date) {
  return date ? date.toLocaleString('zh-CN', { hour12: false }) : '尚未成功';
}
function selectedGroupFromState(state) {
  if (state && state.selected_group_id !== undefined && state.selected_group_id !== null) return state.selected_group_id;
  const comp = (state && (state.prompt_composition || state.context_composition)) || {};
  return comp.selected_group_id;
}
function stateUrl() {
  const params = new URLSearchParams();
  if (selectedGroupId !== null && selectedGroupId !== undefined && selectedGroupId !== '') {
    params.set('group_id', String(selectedGroupId));
  }
  const query = params.toString();
  return query ? `/admin/state?${query}` : '/admin/state';
}
function updateConnectionDisplays() {
  const selectedLabel = selectedGroupId === null || selectedGroupId === undefined ? '默认目标群' : String(selectedGroupId);
  $('connection-state').textContent = connectionState;
  $('last-success').textContent = formatLocalTime(lastSuccessfulRefreshAt);
  $('refresh-count').textContent = String(successRefreshCount);
  $('selected-group-label').textContent = selectedLabel;
  renderKV($('connection'), [
    ['连接状态', connectionState],
    ['最近成功刷新', formatLocalTime(lastSuccessfulRefreshAt)],
    ['成功刷新次数', successRefreshCount],
    ['当前查看群', selectedLabel],
    ['轮询间隔', `${REFRESH_INTERVAL_MS / 1000} 秒`],
  ]);
  const errorBox = $('error-details');
  if (lastErrorDetail) {
    errorBox.textContent = lastErrorDetail;
    errorBox.className = 'error-box';
  } else {
    errorBox.textContent = '';
    errorBox.className = 'error-box hidden';
  }
}
function populateGroupSelector(state) {
  const selector = $('group-select');
  const groups = Array.isArray(state.groups) ? state.groups : [];
  const stateSelected = selectedGroupFromState(state);
  if (selectedGroupId === null && stateSelected !== undefined && stateSelected !== null && stateSelected !== '') {
    selectedGroupId = stateSelected;
  }
  const desired = selectedGroupId === null || selectedGroupId === undefined ? '' : String(selectedGroupId);
  const optionValues = groups.map((group) => String(group.group_id));
  clear(selector);
  if (!groups.length) {
    const option = document.createElement('option');
    option.value = '';
    option.textContent = '无可用群';
    selector.appendChild(option);
    selector.value = '';
    return;
  }
  groups.forEach((group) => {
    const value = String(group.group_id);
    const option = document.createElement('option');
    option.value = value;
    option.textContent = `${value}${group.is_target_group ? '（目标）' : ''}${group.allowed ? '' : '（未允许）'}`;
    selector.appendChild(option);
  });
  if (desired && optionValues.includes(desired)) {
    selector.value = desired;
  } else {
    selector.value = optionValues[0];
    selectedGroupId = groups[0].group_id;
  }
  updateConnectionDisplays();
}
function renderRuntime(state) {
  const rt = state.runtime || {};
  const pending = rt.pending || {};
  renderKV($('runtime'), [
    ['状态', rt.status],
    ['进程 PID', rt.pid],
    ['运行秒数', rt.uptime_seconds],
    ['允许群数量', rt.allowed_group_count],
    ['目标群', rt.target_group_id],
    ['队列总数', pending.queue_total],
    ['活跃 worker', pending.active_worker_count],
    ['Direct inflight', pending.direct_inflight_count],
    ['Proactive inflight', pending.proactive_inflight_count],
    ['更新时间', state.generated_at],
  ]);
}
function selectedProactiveState(state) {
  const top = state.proactive || {};
  if (top.selected_group) return top.selected_group;
  const selected = selectedGroupFromState(state);
  const groups = Array.isArray(state.groups) ? state.groups : [];
  const group = groups.find((item) => String(item.group_id) === String(selected));
  return (group && group.proactive) || {};
}
function renderProactive(state) {
  const proactive = selectedProactiveState(state);
  const model = proactive.score_model || ((state.proactive || {}).score_model) || {};
  const activity = proactive.activity || {};
  const limits = proactive.limits || {};
  const score = proactive.current_window_score !== undefined ? proactive.current_window_score : proactive.score;
  const threshold = proactive.threshold !== undefined ? proactive.threshold : model.threshold;
  renderKV($('proactive'), [
    ['启用', proactive.enabled],
    ['评分模型', model.mode || 'bounded_sliding_window'],
    ['分数范围', model.scale || '0-100'],
    ['当前窗口评分', score],
    ['热度分', proactive.heat],
    ['开口信号分', proactive.opening_score],
    ['触发阈值', `${text(threshold)}（${text(proactive.threshold_source || model.threshold_source || 'default')}）`],
    ['窗口长度', `${activity.window_seconds || model.window_seconds || 0} 秒`],
    ['窗口消息 / 发言人数', `${activity.message_count || 0} 条 / ${activity.speaker_count || 0} 人`],
    ['最高单人占比', activity.dominant_speaker_share],
    ['最长同人连发', activity.max_consecutive_same_speaker],
    ['当前阻塞', proactive.blocked || '无'],
    ['当前可触发', proactive.should_trigger],
    ['今日主动次数', `${proactive.daily_count || 0} / ${limits.daily_limit_per_group || 0}`],
    ['群冷却剩余', `${limits.group_cooldown_remaining_seconds || 0} 秒`],
    ['限速窗口', `${limits.rate_limit_recent_replies || 0} / ${limits.rate_limit_max_replies || 0}（${limits.rate_limit_window_seconds || 0} 秒）`],
    ['主动队列 / inflight', `${proactive.queue_size || 0} / ${proactive.inflight ? '是' : '否'}`],
    ['原因标签', (proactive.reasons || []).join(', ') || '无'],
  ]);
}
function renderModel(state) {
  const routing = state.model_routing || {};
  const primary = routing.primary || {};
  const selected = routing.selected_group || {};
  const fallback = routing.fallback || {};
  renderKV($('model'), [
    ['主模型', primary.model],
    ['主 Provider', primary.provider],
    ['当前群模型', selected.model],
    ['当前群 Provider', selected.provider],
    ['按群模型覆盖数', routing.group_model_override_count],
    ['按群 Provider 覆盖数', routing.group_provider_override_count],
    ['群会话启用', routing.group_sessions_enabled],
    ['会话自动压缩', routing.session_autocompact_enabled],
    ['Fallback 启用', fallback.enabled],
    ['Fallback 可用', fallback.available_for_selected_group],
    ['Fallback 模型', fallback.model],
    ['Fallback Provider', fallback.provider],
  ]);
}
function renderOcr(state) {
  const ocr = state.ocr || {};
  const fallback = ocr.fallback || {};
  const status = ocr.status || {};
  renderKV($('ocr'), [
    ['OCR 启用', ocr.enabled],
    ['外部 Provider 允许', ocr.external_provider_allowed],
    ['Provider', ocr.provider],
    ['模型', ocr.model],
    ['结果进入 prompt', ocr.include_in_prompt],
    ['结果进入上下文', ocr.include_in_context],
    ['OCR inflight', status.inflight_count],
    ['OCR 上下文任务', status.context_task_count],
    ['OCR 缓存条目', `${status.cache_entries || 0} / ${status.cache_max_entries || 0}`],
    ['Fallback 启用', fallback.enabled],
    ['Fallback Provider', fallback.provider],
    ['Fallback 模型', fallback.model],
  ]);
}
function renderReplyErrorReasons(state) {
  const target = $('reply-error-reasons');
  clear(target);
  const replyErrors = state.reply_errors || {};
  const reasons = Array.isArray(replyErrors.reasons) ? replyErrors.reasons : [];
  const visibleRows = reasons.filter((row) => numberValue(row.count) > 0);
  if (!visibleRows.length) {
    const empty = document.createElement('p');
    empty.className = 'muted';
    empty.textContent = '暂无回复错误';
    target.appendChild(empty);
    return;
  }
  const table = document.createElement('table');
  const head = document.createElement('tr');
  ['错误原因', 'counter key', '计数'].forEach((name) => {
    const th = document.createElement('th'); th.textContent = name; head.appendChild(th);
  });
  table.appendChild(head);
  visibleRows.forEach((row) => {
    const tr = document.createElement('tr');
    [row.label, row.key, numberValue(row.count)].forEach((value) => { const td = document.createElement('td'); td.textContent = text(value); tr.appendChild(td); });
    table.appendChild(tr);
  });
  target.appendChild(table);
}
function metricRows(state) {
  const rt = state.runtime || {};
  const pending = rt.pending || {};
  const counters = rt.counters || {};
  const ocr = state.ocr || {};
  const ocrStatus = ocr.status || {};
  const proactive = selectedProactiveState(state);
  const replySuccess = numberValue(counters.direct_replies_sent) + numberValue(counters.proactive_replies_sent) + numberValue(counters.command_success);
  const replyErrors = numberValue(state.reply_errors && state.reply_errors.total);
  return [
    { key: 'proactive_score', label: '主动窗口评分', value: numberValue(proactive.current_window_score !== undefined ? proactive.current_window_score : proactive.score), desc: '0-100 当前窗口热度 + 开口信号' },
    { key: 'proactive_heat', label: '主动热度分', value: numberValue(proactive.heat), desc: '短窗口消息密度、人数和分布' },
    { key: 'proactive_opening', label: '开口信号分', value: numberValue(proactive.opening_score), desc: '梗队形、问题、观点征询或共鸣信号' },
    { key: 'proactive_threshold', label: '主动触发阈值', value: numberValue(proactive.threshold), desc: '当前群 0-100 阈值配置', trend: false },
    { key: 'queue_total', label: '队列总数', value: numberValue(pending.queue_total), desc: 'direct + proactive 待处理' },
    { key: 'active_worker_count', label: '活跃 worker', value: numberValue(pending.active_worker_count), desc: '正在运行的回复 worker' },
    { key: 'direct_inflight_count', label: 'Direct inflight', value: numberValue(pending.direct_inflight_count), desc: '直接回复生成中' },
    { key: 'proactive_inflight_count', label: 'Proactive inflight', value: numberValue(pending.proactive_inflight_count), desc: '主动发言生成中' },
    { key: 'reply_success_total', label: '回复成功计数', value: replySuccess, desc: 'direct / proactive / command 成功' },
    { key: 'reply_error_total', label: '回复错误计数', value: replyErrors, desc: '发送、生成、命令和 Hermes 错误' },
    { key: 'events_total', label: '事件总数', value: numberValue(counters.events_total), desc: '收到的 OneBot 事件计数' },
    { key: 'ignored_total', label: '忽略计数', value: numberValue(counters.ignored_total), desc: '未进入回复流程的事件' },
    { key: 'ocr_enabled', label: 'OCR 状态', value: ocr.enabled ? '启用' : '关闭', desc: '当前 OCR 配置状态', trend: false },
    { key: 'ocr_inflight_count', label: 'OCR inflight', value: numberValue(ocrStatus.inflight_count), desc: '正在识别的图片任务' },
    { key: 'ocr_context_task_count', label: 'OCR 上下文任务', value: numberValue(ocrStatus.context_task_count), desc: '后台上下文识别任务' },
    { key: 'ocr_cache_entries', label: 'OCR 缓存条目', value: numberValue(ocrStatus.cache_entries), desc: '短期图片识别缓存' },
  ];
}
function renderMetricDelta(card, item) {
  const delta = document.createElement('span');
  delta.className = 'delta flat';
  if (item.trend === false || typeof item.value !== 'number') {
    delta.textContent = '趋势：不适用';
  } else if (!previousMetricValues || previousMetricValues[item.key] === undefined) {
    delta.textContent = '趋势：本次为基线';
  } else {
    const diff = item.value - Number(previousMetricValues[item.key] || 0);
    delta.textContent = `Δ ${diff > 0 ? '+' : ''}${diff}`;
    delta.className = `delta ${diff > 0 ? 'up' : diff < 0 ? 'down' : 'flat'}`;
  }
  card.appendChild(delta);
}
function renderMetrics(state) {
  const target = $('metrics');
  clear(target);
  const rows = metricRows(state);
  rows.forEach((item) => {
    const card = document.createElement('div');
    card.className = 'metric-card';
    const label = document.createElement('span');
    label.className = 'metric-label';
    label.textContent = item.label;
    const value = document.createElement('strong');
    value.className = 'metric-value';
    value.textContent = text(item.value);
    const desc = document.createElement('div');
    desc.className = 'metric-desc';
    desc.textContent = item.desc;
    card.append(label, value, desc);
    renderMetricDelta(card, item);
    target.appendChild(card);
  });
  previousMetricValues = Object.fromEntries(rows.filter((item) => typeof item.value === 'number').map((item) => [item.key, item.value]));
}
function renderGroups(state) {
  const target = $('groups');
  clear(target);
  const table = document.createElement('table');
  const head = document.createElement('tr');
  ['群', '模型', 'Provider', '最近消息', '摘要', '队列', '主动窗口分'].forEach((name) => {
    const th = document.createElement('th'); th.textContent = name; head.appendChild(th);
  });
  table.appendChild(head);
  (state.groups || []).forEach((group) => {
    const tr = document.createElement('tr');
    const ctx = group.context || {};
    const queues = group.queues || {};
    const proactive = group.proactive || {};
    const pScore = proactive.current_window_score !== undefined ? proactive.current_window_score : (proactive.score || 0);
    const pThreshold = proactive.threshold !== undefined ? proactive.threshold : ((proactive.score_model || {}).threshold || 0);
    [
      String(group.group_id) + (group.is_target_group ? '（目标）' : ''),
      group.model && group.model.model,
      group.model && group.model.provider,
      `${ctx.recent_message_count || 0} 条（人 ${ctx.human_message_count || 0} / 机器人 ${ctx.bot_message_count || 0}）`,
      `${ctx.summary_count || 0} 条 / ${ctx.summary_total_chars || 0} 字`,
      `direct ${queues.direct || 0} / proactive ${queues.proactive || 0}`,
      `${pScore} / ${pThreshold}${proactive.blocked ? `（${proactive.blocked}）` : ''}`,
    ].forEach((value) => { const td = document.createElement('td'); td.textContent = text(value); tr.appendChild(td); });
    table.appendChild(tr);
  });
  target.appendChild(table);
}
function addSummaryChip(parent, label, value) {
  const chip = document.createElement('div');
  chip.className = 'summary-chip';
  const span = document.createElement('span');
  span.textContent = label;
  const strong = document.createElement('strong');
  strong.textContent = text(value);
  chip.append(span, strong);
  parent.appendChild(chip);
}
function renderCompositionKind(parent, label, data) {
  const h = document.createElement('h3');
  h.textContent = label;
  parent.appendChild(h);
  const summary = document.createElement('div');
  summary.className = 'composition-summary';
  addSummaryChip(summary, 'section 数量', data.section_count || 0);
  addSummaryChip(summary, '规则数量', data.rules_count || 0);
  addSummaryChip(summary, 'prompt 上限', data.max_prompt_chars === null || data.max_prompt_chars === undefined ? '不适用' : data.max_prompt_chars);
  addSummaryChip(summary, '输出约定', data.output_contract || '（空）');
  parent.appendChild(summary);
  const table = document.createElement('table');
  const head = document.createElement('tr');
  ['section', 'key', 'source / priority', 'budget', '简述'].forEach((name) => {
    const th = document.createElement('th'); th.textContent = name; head.appendChild(th);
  });
  table.appendChild(head);
  (data.sections || []).forEach((section) => {
    const tr = document.createElement('tr');
    [
      section.title,
      section.key,
      `${section.source} / ${section.priority}`,
      section.budget_chars === null || section.budget_chars === undefined ? '不限' : section.budget_chars,
      section.summary,
    ].forEach((value) => { const td = document.createElement('td'); td.textContent = text(value); tr.appendChild(td); });
    table.appendChild(tr);
  });
  parent.appendChild(table);
}
function renderComposition(state) {
  const target = $('composition');
  clear(target);
  const comp = state.prompt_composition || state.context_composition || {};
  const note = document.createElement('p');
  note.className = 'muted';
  note.textContent = `当前查看群：${text(comp.selected_group_id)}。仅展示输入给机器人的 prompt 组成元数据：section 名称/key、source、priority、budget、简短静态摘要和数量/限制；所有原文内容均隐藏。`;
  target.appendChild(note);
  renderCompositionKind(target, 'Direct 回复 prompt', comp.direct || {});
  renderCompositionKind(target, 'Proactive 主动发言 prompt', comp.proactive || {});
}
function memoryUrl() {
  const params = new URLSearchParams();
  if (selectedGroupId !== null && selectedGroupId !== undefined && selectedGroupId !== '') {
    params.set('group_id', String(selectedGroupId));
  }
  const query = params.toString();
  return query ? `/admin/memory?${query}` : '/admin/memory';
}
function memoryPayload(extra) {
  return Object.assign({ group_id: selectedGroupId }, extra || {});
}
async function postMemoryAction(url, payload) {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(await errorFromResponse(response));
  return response.json();
}
function renderMemoryRows(state) {
  const target = $('memory');
  clear(target);
  const entries = Array.isArray(state.entries) ? state.entries : [];
  const summary = state.summary || {};
  const note = document.createElement('p');
  note.className = 'muted';
  note.textContent = `当前群 ${text(state.group_id)}：共 ${summary.total || 0} 条，启用 ${summary.active || 0}，停用 ${summary.disabled || 0}，人工 ${summary.manual || 0}，自学习 ${summary.self_learning || 0}。`;
  target.appendChild(note);
  if (!entries.length) {
    const empty = document.createElement('p');
    empty.className = 'muted';
    empty.textContent = '暂无可管理记忆或自学习条目';
    target.appendChild(empty);
    return;
  }
  const table = document.createElement('table');
  const head = document.createElement('tr');
  ['预览', '类型 / 来源', '状态', '权重 / 强化', '操作'].forEach((name) => {
    const th = document.createElement('th'); th.textContent = name; head.appendChild(th);
  });
  table.appendChild(head);
  entries.forEach((entry) => {
    const tr = document.createElement('tr');
    const preview = document.createElement('td');
    preview.className = 'memory-preview';
    preview.textContent = entry.redacted ? '[redacted]' : text(entry.preview);
    const source = document.createElement('td');
    source.textContent = `${text(entry.type)} / ${text(entry.source)}`;
    const status = document.createElement('td');
    status.textContent = text(entry.status);
    const counters = document.createElement('td');
    counters.textContent = `${text(entry.weight)} / ${text(entry.reinforcement)}`;
    const actions = document.createElement('td');
    const box = document.createElement('div');
    box.className = 'actions';
    const strengthen = document.createElement('button');
    strengthen.type = 'button';
    strengthen.textContent = '强化';
    strengthen.disabled = !(entry.operations && entry.operations.strengthen);
    strengthen.addEventListener('click', () => memoryAction('/admin/memory/strengthen', { entry_id: entry.id, amount: 1 }, '已强化'));
    const disable = document.createElement('button');
    disable.type = 'button';
    disable.textContent = '停用';
    disable.disabled = !(entry.operations && entry.operations.disable);
    disable.addEventListener('click', () => memoryAction('/admin/memory/delete', { entry_id: entry.id, mode: 'disable' }, '已停用'));
    const del = document.createElement('button');
    del.type = 'button';
    del.className = 'danger';
    del.textContent = '删除';
    del.addEventListener('click', () => memoryAction('/admin/memory/delete', { entry_id: entry.id, mode: 'delete' }, '已删除'));
    box.append(strengthen, disable, del);
    actions.appendChild(box);
    [preview, source, status, counters, actions].forEach((td) => tr.appendChild(td));
    table.appendChild(tr);
  });
  target.appendChild(table);
}
async function loadMemory() {
  const status = $('memory-status');
  if (!status) return;
  status.textContent = '正在加载记忆 / 自学习条目…';
  status.className = 'muted';
  try {
    const response = await fetch(memoryUrl(), { cache: 'no-store' });
    if (!response.ok) throw new Error(await errorFromResponse(response));
    const state = await response.json();
    renderMemoryRows(state);
    status.textContent = '记忆 / 自学习条目已更新';
    status.className = 'ok';
  } catch (error) {
    status.textContent = `记忆 / 自学习加载失败：${error && error.message ? error.message : error}`;
    status.className = 'warn';
  }
}
async function memoryAction(url, payload, okText) {
  const status = $('memory-status');
  try {
    status.textContent = '正在提交记忆管理操作…';
    status.className = 'muted';
    await postMemoryAction(url, memoryPayload(payload));
    status.textContent = okText;
    status.className = 'ok';
    await loadMemory();
  } catch (error) {
    status.textContent = `记忆管理操作失败：${error && error.message ? error.message : error}`;
    status.className = 'warn';
  }
}
function renderJson(state) {
  $('state-json').textContent = JSON.stringify(state, null, 2);
}
async function errorFromResponse(response) {
  let detail = '';
  try {
    const payload = await response.json();
    if (payload && typeof payload.detail === 'string') detail = payload.detail;
  } catch (ignored) {
    detail = '';
  }
  return `HTTP ${response.status}${response.statusText ? ' ' + response.statusText : ''}${detail ? '：' + detail : ''}`;
}
async function loadState() {
  const status = $('status');
  connectionState = lastSuccessfulRefreshAt ? '刷新中' : '连接中';
  lastErrorDetail = '';
  updateConnectionDisplays();
  status.textContent = ' 正在刷新…';
  status.className = 'muted';
  try {
    const response = await fetch(stateUrl(), { cache: 'no-store' });
    if (!response.ok) throw new Error(await errorFromResponse(response));
    const state = await response.json();
    populateGroupSelector(state);
    renderRuntime(state);
    renderProactive(state);
    renderModel(state);
    renderOcr(state);
    renderMetrics(state);
    renderReplyErrorReasons(state);
    renderGroups(state);
    renderComposition(state);
    renderJson(state);
    await loadMemory();
    lastSuccessfulRefreshAt = new Date();
    successRefreshCount += 1;
    connectionState = '已连接';
    status.textContent = ' 已更新';
    status.className = 'ok';
  } catch (error) {
    connectionState = '错误';
    lastErrorDetail = `刷新 /admin/state 失败：${error && error.message ? error.message : error}`;
    status.textContent = ' 刷新失败';
    status.className = 'warn';
  }
  updateConnectionDisplays();
}
$('refresh').addEventListener('click', loadState);
$('memory-add-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const textValue = $('memory-entry-text').value || '';
  await memoryAction('/admin/memory/add', {
    entry_type: $('memory-entry-type').value,
    text: textValue,
    weight: Number($('memory-entry-weight').value || 1),
  }, '已添加');
  if (textValue.trim()) $('memory-entry-text').value = '';
});
$('group-select').addEventListener('change', (event) => {
  selectedGroupId = event.target.value ? Number(event.target.value) : null;
  loadState();
});
updateConnectionDisplays();
loadState();
setInterval(loadState, REFRESH_INTERVAL_MS);
</script>
</body>
</html>
"""
