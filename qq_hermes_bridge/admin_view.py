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
_URLISH_RE = re.compile(r"(?i)\b[a-z0-9.-]+\.[a-z]{2,}(?:/|:)")
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
    if _SECRET_TOKEN_RE.search(text) or _URLISH_RE.search(text):
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
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_counters(counters: Mapping[str, Any]) -> dict[str, int]:
    """Return runtime counters with controlled names and integer values only."""
    safe: dict[str, int] = {}
    for key, value in counters.items():
        name = re.sub(r"[^a-zA-Z0-9_:-]", "_", str(key or "unknown"))[:80]
        if not name:
            continue
        safe[name] = _safe_int(value)
    return dict(sorted(safe.items()))


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


def safe_proactive_state(state: Mapping[str, Any], *, now: float) -> dict[str, Any]:
    sensitive_until = _safe_float(state.get("sensitive_until"), 0.0)
    return {
        "score": round(_safe_float(state.get("score"), 0.0), 3),
        "daily_count": _safe_int(state.get("daily_count"), 0),
        "sensitive_active": bool(sensitive_until and sensitive_until > now),
    }


def _request_for_kind(kind: str, *, group_id: int | None, max_prompt_chars: int) -> prompt_service.PromptRequest:
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
) -> dict[str, Any]:
    request = _request_for_kind(kind, group_id=group_id, max_prompt_chars=max_prompt_chars)
    sections: list[dict[str, Any]] = []
    for section in request.sections:
        budget = prompt_service._budget_for_section(request.kind, section)  # noqa: SLF001 - prompt metadata only; no body exposed.
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
        ),
        "proactive": _prompt_kind_overview(
            "proactive",
            group_id=group_id,
            context_stats=context_stats,
            max_prompt_chars=max_prompt_chars,
            ocr_enabled=ocr_enabled,
            self_learning_enabled=self_learning_enabled,
        ),
    }


def build_admin_html() -> str:
    """Return a dependency-free admin page that renders /admin/state safely."""
    return """<!doctype html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>QQ Hermes 本地状态</title>
  <style>
    :root { color-scheme: light dark; font-family: system-ui, -apple-system, BlinkMacSystemFont, \"Segoe UI\", sans-serif; }
    body { margin: 0; background: #0f172a; color: #e2e8f0; }
    header { padding: 24px; background: linear-gradient(135deg, #1e293b, #111827); border-bottom: 1px solid #334155; }
    h1 { margin: 0 0 8px; font-size: 24px; }
    h2 { margin: 0 0 12px; font-size: 18px; }
    p { margin: 4px 0; color: #94a3b8; }
    button { margin-top: 12px; padding: 8px 12px; border: 1px solid #475569; border-radius: 8px; background: #1e293b; color: #e2e8f0; cursor: pointer; }
    button:hover { background: #334155; }
    main { padding: 16px; display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); }
    section { border: 1px solid #334155; border-radius: 12px; padding: 16px; background: #111827; box-shadow: 0 10px 30px rgba(0, 0, 0, .18); }
    dl { display: grid; grid-template-columns: minmax(120px, 42%) 1fr; gap: 8px 12px; margin: 0; }
    dt { color: #94a3b8; }
    dd { margin: 0; overflow-wrap: anywhere; }
    table { width: 100%; border-collapse: collapse; font-size: 14px; }
    th, td { border-bottom: 1px solid #334155; padding: 8px 6px; text-align: left; vertical-align: top; }
    th { color: #cbd5e1; font-weight: 600; }
    .muted { color: #94a3b8; }
    .ok { color: #86efac; }
    .warn { color: #fcd34d; }
    .full { grid-column: 1 / -1; }
    .section-card { border-top: 1px solid #334155; padding-top: 10px; margin-top: 10px; }
    code { background: #020617; border: 1px solid #334155; border-radius: 4px; padding: 1px 4px; }
  </style>
</head>
<body>
  <header>
    <h1>QQ Hermes 本地数据查看</h1>
    <p>实时查看运行状态、当前模型路由，以及模型输入上下文组成概览。</p>
    <p>安全策略：本页不展示原始聊天、完整 prompt、模型输出、OCR 文本、Provider URL、Token/Cookie 或本地密钥路径。</p>
    <button id=\"refresh\" type=\"button\">立即刷新</button>
    <span id=\"status\" class=\"muted\"></span>
  </header>
  <main>
    <section><h2>运行状态</h2><div id=\"runtime\"></div></section>
    <section><h2>模型 / Provider</h2><div id=\"model\"></div></section>
    <section><h2>OCR / 媒体</h2><div id=\"ocr\"></div></section>
    <section class=\"full\"><h2>群状态</h2><div id=\"groups\"></div></section>
    <section class=\"full\"><h2>模型输入上下文组成</h2><div id=\"composition\"></div></section>
  </main>
<script>
const $ = (id) => document.getElementById(id);
function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }
function text(value) { return value === null || value === undefined || value === '' ? '（空）' : String(value); }
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
function renderModel(state) {
  const routing = state.model_routing || {};
  const primary = routing.primary || {};
  const fallback = routing.fallback || {};
  renderKV($('model'), [
    ['主模型', primary.model],
    ['主 Provider', primary.provider],
    ['主模型已配置', primary.model_configured],
    ['主 Provider 已配置', primary.provider_configured],
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
  renderKV($('ocr'), [
    ['OCR 启用', ocr.enabled],
    ['外部 Provider 允许', ocr.external_provider_allowed],
    ['Provider', ocr.provider],
    ['模型', ocr.model],
    ['结果进入 prompt', ocr.include_in_prompt],
    ['结果进入上下文', ocr.include_in_context],
    ['Fallback 启用', fallback.enabled],
    ['Fallback Provider', fallback.provider],
    ['Fallback 模型', fallback.model],
  ]);
}
function renderGroups(state) {
  const target = $('groups');
  clear(target);
  const table = document.createElement('table');
  const head = document.createElement('tr');
  ['群', '模型', 'Provider', '最近消息', '摘要', '队列', '主动分'].forEach((name) => {
    const th = document.createElement('th'); th.textContent = name; head.appendChild(th);
  });
  table.appendChild(head);
  (state.groups || []).forEach((group) => {
    const tr = document.createElement('tr');
    const ctx = group.context || {};
    const queues = group.queues || {};
    const proactive = group.proactive || {};
    [
      String(group.group_id) + (group.is_target_group ? '（目标）' : ''),
      group.model && group.model.model,
      group.model && group.model.provider,
      `${ctx.recent_message_count || 0} 条（人 ${ctx.human_message_count || 0} / 机器人 ${ctx.bot_message_count || 0}）`,
      `${ctx.summary_count || 0} 条 / ${ctx.summary_total_chars || 0} 字`,
      `direct ${queues.direct || 0} / proactive ${queues.proactive || 0}`,
      proactive.score || 0,
    ].forEach((value) => { const td = document.createElement('td'); td.textContent = text(value); tr.appendChild(td); });
    table.appendChild(tr);
  });
  target.appendChild(table);
}
function sectionBlock(section) {
  const wrap = document.createElement('div');
  wrap.className = 'section-card';
  const title = document.createElement('div');
  title.textContent = `${section.title} (${section.key})`;
  const meta = document.createElement('p');
  meta.textContent = `来源 ${section.source} / 优先级 ${section.priority} / 预算 ${section.budget_chars === null ? '不限' : section.budget_chars}`;
  const summary = document.createElement('p');
  summary.textContent = section.summary;
  wrap.append(title, meta, summary);
  return wrap;
}
function renderCompositionKind(parent, label, data) {
  const h = document.createElement('h3');
  h.textContent = `${label}：${data.section_count || 0} 个 section，${data.rules_count || 0} 条规则`;
  parent.appendChild(h);
  (data.sections || []).forEach((section) => parent.appendChild(sectionBlock(section)));
}
function renderComposition(state) {
  const target = $('composition');
  clear(target);
  const comp = state.context_composition || {};
  const note = document.createElement('p');
  note.className = 'muted';
  note.textContent = `当前查看群：${text(comp.selected_group_id)}。所有原文内容均隐藏，仅展示组成、优先级、预算和安全计数。`;
  target.appendChild(note);
  renderCompositionKind(target, 'Direct 回复', comp.direct || {});
  renderCompositionKind(target, 'Proactive 主动发言', comp.proactive || {});
}
async function loadState() {
  const status = $('status');
  status.textContent = ' 正在刷新…';
  try {
    const response = await fetch('/admin/state', { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const state = await response.json();
    renderRuntime(state);
    renderModel(state);
    renderOcr(state);
    renderGroups(state);
    renderComposition(state);
    status.textContent = ' 已更新';
    status.className = 'ok';
  } catch (error) {
    status.textContent = ` 刷新失败：${error && error.message ? error.message : error}`;
    status.className = 'warn';
  }
}
$('refresh').addEventListener('click', loadState);
loadState();
setInterval(loadState, 5000);
</script>
</body>
</html>
"""
