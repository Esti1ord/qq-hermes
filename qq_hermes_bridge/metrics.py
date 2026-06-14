"""Lightweight Prometheus text metrics for the QQ/Hermes bridge.

This module intentionally avoids the external ``prometheus_client`` dependency so
production deployments can expose basic metrics without changing install steps.
Only low-cardinality, content-safe labels are accepted. Raw message/reply/prompt
text, user hashes, tokens, URLs, and other opaque identifiers must never be
exported.
"""
from __future__ import annotations

import math
import threading
from dataclasses import dataclass, field
from typing import Any, Iterable

METRIC_PREFIX = "qq_hermes_"
CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"

_UNSAFE_LABEL_FRAGMENTS = {
    "message",
    "text",
    "reply",
    "prompt",
    "query",
    "user",
    "hash",
    "token",
    "authorization",
    "cookie",
    "secret",
    "password",
    "url",
    "uri",
    "host",
    "stdout",
    "stderr",
    "response",
    "body",
    "ocr_text",
}

_LOW_CARDINALITY_LABELS = {
    "route",
    "result",
    "type",
    "status",
    "component",
    "error_type",
    "group_id",
}

_DEFAULT_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0)


def parse_bool(value: Any, default: bool = False) -> bool:
    if value in (None, ""):
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _prefixed(name: str) -> str:
    clean = _sanitize_name(name)
    if clean.startswith(METRIC_PREFIX):
        return clean
    return f"{METRIC_PREFIX}{clean}"


def _sanitize_name(value: Any) -> str:
    text = str(value or "unknown").strip().lower()
    chars = [ch if ch.isalnum() or ch == "_" else "_" for ch in text]
    clean = "".join(chars).strip("_") or "unknown"
    if clean[0].isdigit():
        clean = f"_{clean}"
    return clean[:120]


def _sanitize_label_value(value: Any, *, default: str = "unknown") -> str:
    text = str(value if value not in (None, "") else default).strip()
    if len(text) > 64:
        return default
    if not text:
        return default
    lowered = text.lower()
    if any(marker in lowered for marker in ("http://", "https://", "bearer", "token", "secret", "password")):
        return default
    if not all(ch.isascii() and (ch.isalnum() or ch in {"_", "-", "."}) for ch in text):
        return default
    return lowered


def _label_name_is_safe(name: str) -> bool:
    clean = str(name or "").lower()
    if clean not in _LOW_CARDINALITY_LABELS:
        return False
    return not any(fragment in clean for fragment in _UNSAFE_LABEL_FRAGMENTS)


def _label_value_is_safe(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool, type(None)))


def _label_tuple(labels: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    safe: list[tuple[str, str]] = []
    for raw_name, raw_value in labels.items():
        name = _sanitize_name(raw_name)
        if not _label_name_is_safe(name) or not _label_value_is_safe(raw_value):
            continue
        safe.append((name, _sanitize_label_value(raw_value)))
    return tuple(sorted(safe))


def _format_labels(labels: tuple[tuple[str, str], ...]) -> str:
    if not labels:
        return ""
    rendered = []
    for key, value in labels:
        escaped = value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')
        rendered.append(f'{key}="{escaped}"')
    return "{" + ",".join(rendered) + "}"


def _format_number(value: float) -> str:
    if math.isinf(value):
        return "+Inf" if value > 0 else "-Inf"
    if math.isnan(value):
        return "NaN"
    return f"{float(value):.12g}"


@dataclass
class _Counter:
    name: str
    documentation: str
    values: dict[tuple[tuple[str, str], ...], float] = field(default_factory=dict)


@dataclass
class _Gauge:
    name: str
    documentation: str
    values: dict[tuple[tuple[str, str], ...], float] = field(default_factory=dict)


@dataclass
class _Histogram:
    name: str
    documentation: str
    buckets: tuple[float, ...] = _DEFAULT_BUCKETS
    counts: dict[tuple[tuple[str, str], ...], list[int]] = field(default_factory=dict)
    sums: dict[tuple[tuple[str, str], ...], float] = field(default_factory=dict)
    totals: dict[tuple[tuple[str, str], ...], int] = field(default_factory=dict)

    def observe(self, labels: tuple[tuple[str, str], ...], value: float) -> None:
        value = max(0.0, float(value or 0.0))
        bucket_counts = self.counts.setdefault(labels, [0 for _ in self.buckets])
        for index, upper_bound in enumerate(self.buckets):
            if value <= upper_bound:
                bucket_counts[index] += 1
        self.totals[labels] = self.totals.get(labels, 0) + 1
        self.sums[labels] = self.sums.get(labels, 0.0) + value


class MetricsRegistry:
    """In-memory Prometheus text registry with content-safe labels only."""

    def __init__(self, *, enabled: bool = True, include_group_id_label: bool = False) -> None:
        self.enabled = bool(enabled)
        self.include_group_id_label = bool(include_group_id_label)
        self._lock = threading.RLock()
        self._counters: dict[str, _Counter] = {}
        self._gauges: dict[str, _Gauge] = {}
        self._histograms: dict[str, _Histogram] = {}

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()

    def configure(self, *, enabled: bool | None = None, include_group_id_label: bool | None = None) -> None:
        with self._lock:
            if enabled is not None:
                self.enabled = bool(enabled)
            if include_group_id_label is not None:
                self.include_group_id_label = bool(include_group_id_label)

    def counter(self, name: str, documentation: str, amount: float = 1.0, **labels: Any) -> None:
        if not self.enabled:
            return
        metric_name = _prefixed(name)
        label_values = self._labels(labels)
        with self._lock:
            metric = self._counters.setdefault(metric_name, _Counter(metric_name, documentation))
            metric.values[label_values] = metric.values.get(label_values, 0.0) + max(0.0, float(amount or 0.0))

    def gauge(self, name: str, documentation: str, value: float, **labels: Any) -> None:
        if not self.enabled:
            return
        metric_name = _prefixed(name)
        label_values = self._labels(labels)
        with self._lock:
            metric = self._gauges.setdefault(metric_name, _Gauge(metric_name, documentation))
            metric.values[label_values] = float(value or 0.0)

    def histogram(self, name: str, documentation: str, value: float, *, buckets: Iterable[float] | None = None, **labels: Any) -> None:
        if not self.enabled:
            return
        metric_name = _prefixed(name)
        label_values = self._labels(labels)
        with self._lock:
            metric = self._histograms.get(metric_name)
            if metric is None:
                raw_buckets = tuple(float(x) for x in (buckets or _DEFAULT_BUCKETS))
                metric = _Histogram(metric_name, documentation, tuple(sorted(set(raw_buckets))))
                self._histograms[metric_name] = metric
            metric.observe(label_values, float(value or 0.0))

    def render(self) -> str:
        lines: list[str] = []
        with self._lock:
            for name in sorted(self._counters):
                metric = self._counters[name]
                lines.append(f"# HELP {name} {metric.documentation}")
                lines.append(f"# TYPE {name} counter")
                for labels, value in sorted(metric.values.items()):
                    lines.append(f"{name}{_format_labels(labels)} {_format_number(value)}")
            for name in sorted(self._gauges):
                metric = self._gauges[name]
                lines.append(f"# HELP {name} {metric.documentation}")
                lines.append(f"# TYPE {name} gauge")
                for labels, value in sorted(metric.values.items()):
                    lines.append(f"{name}{_format_labels(labels)} {_format_number(value)}")
            for name in sorted(self._histograms):
                metric = self._histograms[name]
                lines.append(f"# HELP {name} {metric.documentation}")
                lines.append(f"# TYPE {name} histogram")
                for labels in sorted(metric.totals):
                    bucket_counts = metric.counts.get(labels, [])
                    for upper_bound, count in zip(metric.buckets, bucket_counts):
                        bucket_labels = tuple(sorted(labels + (("le", _format_number(upper_bound)),)))
                        lines.append(f"{name}_bucket{_format_labels(bucket_labels)} {count}")
                    inf_labels = tuple(sorted(labels + (("le", "+Inf"),)))
                    lines.append(f"{name}_bucket{_format_labels(inf_labels)} {metric.totals.get(labels, 0)}")
                    lines.append(f"{name}_count{_format_labels(labels)} {metric.totals.get(labels, 0)}")
                    lines.append(f"{name}_sum{_format_labels(labels)} {_format_number(metric.sums.get(labels, 0.0))}")
        return "\n".join(lines) + "\n"

    def _labels(self, labels: dict[str, Any]) -> tuple[tuple[str, str], ...]:
        filtered = dict(labels)
        if not self.include_group_id_label:
            filtered.pop("group_id", None)
        return _label_tuple(filtered)


_registry = MetricsRegistry()


def configure(*, enabled: bool = True, include_group_id_label: bool = False) -> None:
    _registry.configure(enabled=enabled, include_group_id_label=include_group_id_label)


def reset() -> None:
    _registry.reset()


def generate_latest() -> str:
    return _registry.render()


def observe_runtime_counter(name: str, amount: int = 1) -> None:
    """Expose existing internal runtime counters as safe low-cardinality metrics."""
    normalized = _sanitize_label_value(name)
    _registry.counter(
        "runtime_counters_total",
        "Internal bridge runtime counters.",
        amount,
        type=normalized,
    )


def observe_runtime_stat(stat: str, fields: dict[str, Any]) -> None:
    """Map existing runtime_stat/emit_perf_stat records to Prometheus metrics."""
    safe_fields = dict(fields or {})
    stat_name = _sanitize_label_value(stat)

    if stat_name == "route_decision":
        route = _sanitize_label_value(safe_fields.get("route") or "unknown")
        result = _route_result(route, safe_fields)
        _registry.counter(
            "messages_total",
            "Message routing decisions by route and result.",
            1,
            route=route,
            result=result,
            group_id=safe_fields.get("group_id"),
        )
        return

    if stat_name in {"direct_reply_result", "proactive_reply_result", "command_result"}:
        reply_type = _reply_type(stat_name, safe_fields)
        status = _reply_status(stat_name, safe_fields)
        _registry.counter(
            "replies_total",
            "Reply attempts and outcomes by type and status.",
            1,
            type=reply_type,
            status=status,
        )
        duration_ms = safe_fields.get("e2e_ms") or safe_fields.get("duration_ms")
        if duration_ms not in (None, ""):
            _registry.histogram(
                "reply_duration_seconds",
                "End-to-end reply latency in seconds.",
                _milliseconds_to_seconds(duration_ms),
                type=reply_type,
                status=status,
            )
        queue_wait_ms = safe_fields.get("queue_wait_ms")
        if queue_wait_ms not in (None, ""):
            _registry.histogram(
                "queue_wait_seconds",
                "Reply queue wait latency in seconds.",
                _milliseconds_to_seconds(queue_wait_ms),
                type=reply_type,
            )
        _observe_reply_stage(reply_type, status, "prompt_build", safe_fields.get("prompt_build_ms"))
        _observe_reply_stage(reply_type, status, "generation", safe_fields.get("generation_ms"))
        if reply_type == "proactive" and status not in {"ok", "sent"}:
            _registry.counter(
                "proactive_skips_total",
                "Proactive replies skipped or cancelled by status.",
                1,
                status=status,
            )
        if reply_type == "direct" and status == "duplicate_suppressed":
            _registry.counter(
                "direct_coalesced_total",
                "Direct replies suppressed by duplicate outbound coalescing.",
                1,
                status=status,
            )
        return

    if stat_name == "hermes_call":
        hermes_type = _hermes_call_type(safe_fields)
        status = _operation_status(safe_fields)
        _registry.histogram(
            "hermes_call_duration_seconds",
            "Hermes text generation call duration in seconds.",
            _milliseconds_to_seconds(safe_fields.get("duration_ms")),
            type=hermes_type,
            status=status,
        )
        if safe_fields.get("ok") is False:
            _registry.counter(
                "errors_total",
                "Errors observed by bridge component.",
                1,
                component="hermes",
                error_type=_sanitize_label_value(safe_fields.get("error") or "nonzero_returncode"),
            )
        return

    if stat_name == "prompt_rendered":
        prompt_type = _sanitize_label_value(safe_fields.get("kind") or safe_fields.get("type") or "unknown")
        _registry.histogram(
            "prompt_chars",
            "Rendered prompt size in characters.",
            _float_value(safe_fields.get("char_count")),
            buckets=(100, 250, 500, 1000, 2000, 4000, 8000, 16000),
            type=prompt_type,
        )
        _registry.histogram(
            "prompt_truncated_sections",
            "Rendered prompt truncated section count.",
            _float_value(safe_fields.get("truncated_count")),
            buckets=(0, 1, 2, 3, 5, 8, 13),
            type=prompt_type,
        )
        return

    if stat_name in {"ocr_fetch_result", "ocr_provider_result", "ocr_route_result"}:
        status = _ocr_status(stat_name, safe_fields)
        _registry.histogram(
            "ocr_duration_seconds",
            "OCR and image-processing duration in seconds.",
            _milliseconds_to_seconds(safe_fields.get("duration_ms")),
            type=_ocr_type(stat_name, safe_fields),
            status=status,
        )
        if safe_fields.get("ok") is False or int(float(safe_fields.get("error_count") or 0)) > 0:
            _registry.counter(
                "errors_total",
                "Errors observed by bridge component.",
                1,
                component="ocr",
                error_type=_sanitize_label_value(safe_fields.get("error") or status),
            )
        return

    if stat_name == "send_group_msg_rate_limited":
        status = _send_status(safe_fields)
        _registry.counter(
            "sends_total",
            "Outbound OneBot send attempts and suppressed duplicates by status.",
            1,
            status=status,
        )
        _registry.histogram(
            "send_duration_seconds",
            "Outbound OneBot send path duration in seconds.",
            _milliseconds_to_seconds(safe_fields.get("duration_ms")),
            status=status,
        )
        _registry.histogram(
            "send_rate_limit_wait_seconds",
            "Time spent waiting for the global send rate limit in seconds.",
            _milliseconds_to_seconds(safe_fields.get("rate_limit_wait_ms")),
            status=status,
        )
        if safe_fields.get("ok") is False:
            _registry.counter(
                "errors_total",
                "Errors observed by bridge component.",
                1,
                component="onebot",
                error_type=_sanitize_label_value(safe_fields.get("onebot_status") or safe_fields.get("status_code") or "send_failed"),
            )
        return

    if stat_name == "ocr_direct_prompt_wait":
        status = _sanitize_label_value(safe_fields.get("status") or "unknown")
        _registry.counter(
            "ocr_direct_prompt_waits_total",
            "Direct prompt OCR wait outcomes by status.",
            1,
            status=status,
        )
        _registry.histogram(
            "ocr_direct_prompt_wait_seconds",
            "Time direct prompt construction waited for OCR in seconds.",
            _milliseconds_to_seconds(safe_fields.get("wait_ms")),
            status=status,
        )
        _registry.histogram(
            "ocr_direct_prompt_timeout_seconds",
            "Configured direct prompt OCR wait deadline in seconds.",
            _milliseconds_to_seconds(safe_fields.get("timeout_ms")),
            status=status,
        )
        return

    if stat_name == "send_group_msg" and safe_fields.get("ok") is False:
        _registry.counter(
            "errors_total",
            "Errors observed by bridge component.",
            1,
            component="onebot",
            error_type=_sanitize_label_value(safe_fields.get("onebot_status") or safe_fields.get("status_code") or "send_failed"),
        )
        return

    if stat_name == "queue_event":
        _set_queue_gauges_from_fields(safe_fields)
        if safe_fields.get("coalesced"):
            try:
                merged_count = max(1.0, float(safe_fields.get("merged_count") or 1))
            except (TypeError, ValueError):
                merged_count = 1.0
            _registry.counter(
                "queue_events_total",
                "Reply queue events by type and status.",
                merged_count,
                type=_sanitize_label_value(safe_fields.get("kind") or "direct"),
                status="coalesced",
                group_id=safe_fields.get("group_id"),
            )
        if not safe_fields.get("queued", True):
            _registry.counter(
                "errors_total",
                "Errors observed by bridge component.",
                1,
                component="queue",
                error_type=_sanitize_label_value(safe_fields.get("reason") or "queue_rejected"),
            )
        return

    if stat_name in {"reply_intent_dequeued", "reply_worker_started", "reply_worker_drained"}:
        _set_queue_gauges_from_fields(safe_fields)
        if int(float(safe_fields.get("error_count") or 0)) > 0:
            _registry.counter(
                "errors_total",
                "Errors observed by bridge component.",
                int(float(safe_fields.get("error_count") or 1)),
                component="queue",
                error_type="worker_error",
            )
        return

    if stat_name == "context_compaction":
        set_context_messages(safe_fields.get("group_id"), safe_fields.get("recent_context_count") or 0)
        return


def record_queue_size(group_id: Any, kind: str, size: int | float) -> None:
    _registry.gauge(
        "queue_size",
        "Current reply queue depth by type.",
        float(size or 0),
        group_id=group_id,
        type=_sanitize_label_value(kind),
    )


def set_context_messages(group_id: Any, count: int | float) -> None:
    _registry.gauge(
        "context_messages",
        "Current recent-context message count.",
        float(count or 0),
        group_id=group_id,
    )


def _set_queue_gauges_from_fields(fields: dict[str, Any]) -> None:
    group_id = fields.get("group_id")
    if "direct_queue_size" in fields:
        record_queue_size(group_id, "direct", fields.get("direct_queue_size") or 0)
    if "proactive_queue_size" in fields:
        record_queue_size(group_id, "proactive", fields.get("proactive_queue_size") or 0)
    if "queue_size" in fields and "direct_queue_size" not in fields and "proactive_queue_size" not in fields:
        record_queue_size(group_id, fields.get("kind") or "unknown", fields.get("queue_size") or 0)


def _route_result(route: str, fields: dict[str, Any]) -> str:
    if fields.get("queued") is True:
        return "queued"
    if fields.get("queued") is False:
        return "not_queued"
    if route == "ignored":
        return _sanitize_label_value(fields.get("reason") or "ignored")
    if fields.get("ok") is False:
        return "error"
    return "selected"


def _reply_type(stat_name: str, fields: dict[str, Any]) -> str:
    if stat_name.startswith("direct"):
        return "direct"
    if stat_name.startswith("proactive"):
        return "proactive"
    return _sanitize_label_value(fields.get("command") or "command")


def _reply_status(stat_name: str, fields: dict[str, Any]) -> str:
    if fields.get("suppressed_duplicate") or fields.get("ignored") == "duplicate_outbound":
        return "duplicate_suppressed"
    if fields.get("generation_failed"):
        return "generation_failed"
    if fields.get("send_failed") or fields.get("error") == "send_failed":
        return "send_failed"
    if fields.get("replied") or fields.get("sent") or fields.get("proactive_replied"):
        return "sent"
    if fields.get("skipped") or fields.get("ignored"):
        return _skip_status(fields)
    if fields.get("ok") is False:
        return "error"
    return "ok"


def _skip_status(fields: dict[str, Any]) -> str:
    reason = _sanitize_label_value(fields.get("ignored") or fields.get("reason") or fields.get("blocked") or "skipped")
    known = {
        "direct_pending",
        "stale",
        "proactive_model_skipped",
        "proactive_revalidated_blocked",
        "proactive_revalidated_score_low",
        "duplicate_suppressed",
        "skipped",
    }
    return reason if reason in known else "skipped"


def _hermes_call_type(fields: dict[str, Any]) -> str:
    transport = _sanitize_label_value(fields.get("transport") or "cli")
    phase = _sanitize_label_value(fields.get("phase") or ("fallback" if "fallback" in str(fields.get("purpose") or "").lower() else "primary"))
    if phase not in {"primary", "fallback"}:
        phase = "primary"
    return _sanitize_label_value(f"{transport}_{phase}")


def _observe_reply_stage(reply_type: str, status: str, component: str, duration_ms: Any) -> None:
    if duration_ms in (None, ""):
        return
    _registry.histogram(
        "reply_stage_duration_seconds",
        "Reply pipeline stage duration in seconds.",
        _milliseconds_to_seconds(duration_ms),
        type=reply_type,
        status=status,
        component=component,
    )


def _send_status(fields: dict[str, Any]) -> str:
    if fields.get("suppressed_duplicate"):
        return "duplicate_suppressed"
    if fields.get("ok") is True:
        return "ok"
    if fields.get("ok") is False:
        return "error"
    return "unknown"


def _operation_status(fields: dict[str, Any]) -> str:
    if fields.get("ok") is True:
        return "ok"
    if fields.get("ok") is False:
        error = _sanitize_label_value(fields.get("error") or fields.get("reason") or "error")
        if error in {"timeout", "timeoutexpired"}:
            return "timeout"
        if error in {"hermes_empty_output", "malformed_response"}:
            return "empty"
        return "error"
    return "unknown"


def _ocr_type(stat_name: str, fields: dict[str, Any]) -> str:
    if stat_name == "ocr_route_result":
        route = _sanitize_label_value(fields.get("route") or "unknown")
        return _sanitize_label_value(f"route_{route}")
    if stat_name == "ocr_fetch_result":
        return "fetch"
    if stat_name == "ocr_provider_result":
        return "provider"
    return "unknown"


def _ocr_status(stat_name: str, fields: dict[str, Any]) -> str:
    if stat_name == "ocr_route_result" and not fields.get("enabled", True):
        return "disabled"
    if int(float(fields.get("skipped_count") or 0)) > 0 and int(float(fields.get("ok_count") or 0)) == 0:
        return "skipped"
    if int(float(fields.get("error_count") or 0)) > 0:
        return "error"
    return _sanitize_label_value(fields.get("status") or ("ok" if fields.get("ok", True) else "error"))


def _float_value(value: Any) -> float:
    try:
        return max(0.0, float(value or 0.0))
    except Exception:
        return 0.0


def _milliseconds_to_seconds(value: Any) -> float:
    return _float_value(value) / 1000.0
