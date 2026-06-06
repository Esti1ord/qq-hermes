"""Result builders for queued direct/proactive reply processing."""
from __future__ import annotations

from typing import Any


def direct_reply_success_result(*, trigger: str, queue_remaining: int, search_notice_sent: bool) -> dict[str, Any]:
    return {
        "ok": True,
        "replied": True,
        "trigger": trigger,
        "queue_remaining": queue_remaining,
        "search_notice_sent": search_notice_sent,
    }


def direct_reply_duplicate_result(*, trigger: str, queue_remaining: int) -> dict[str, Any]:
    return {
        "ok": True,
        "replied": False,
        "trigger": trigger,
        "ignored": "duplicate_outbound",
        "queue_remaining": queue_remaining,
    }


def direct_reply_send_failed_result(*, trigger: str, response: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": False,
        "replied": False,
        "trigger": trigger,
        "error": "send_failed",
        "response": response,
    }


def direct_reply_generation_failed_result(*, trigger: str, reason: str, queue_remaining: int, failure_notice_sent: bool, response: dict[str, Any] | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ok": False,
        "replied": False,
        "trigger": trigger,
        "error": reason,
        "generation_failed": True,
        "failure_notice_sent": failure_notice_sent,
        "queue_remaining": queue_remaining,
    }
    if response is not None:
        result["response"] = response
    return result


def proactive_sent_result(proactive: dict[str, Any], *, queue_remaining: int, search_notice_sent: bool) -> dict[str, Any]:
    return {
        "ok": True,
        "proactive_replied": True,
        "score": proactive.get("score"),
        "reasons": proactive.get("reasons", []),
        "queue_remaining": queue_remaining,
        "search_notice_sent": search_notice_sent,
    }


def proactive_duplicate_result(proactive: dict[str, Any], *, queue_remaining: int) -> dict[str, Any]:
    return {
        "ok": True,
        "proactive_replied": False,
        "ignored": "duplicate_outbound",
        "score": proactive.get("score"),
        "reasons": proactive.get("reasons", []),
        "queue_remaining": queue_remaining,
    }


def proactive_skipped_result(proactive: dict[str, Any], *, queue_remaining: int) -> dict[str, Any]:
    return {
        "ok": True,
        "ignored": "proactive_model_skipped",
        "score": proactive.get("score"),
        "queue_remaining": queue_remaining,
    }


def proactive_send_failed_result(response: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": False,
        "proactive_replied": False,
        "error": "send_failed",
        "response": response,
    }
