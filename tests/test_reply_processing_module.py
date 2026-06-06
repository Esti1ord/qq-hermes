from qq_hermes_bridge import reply_processing


def test_direct_reply_success_result_includes_queue_and_search_notice():
    result = reply_processing.direct_reply_success_result(
        trigger="reply_to_bot",
        queue_remaining=2,
        search_notice_sent=False,
    )

    assert result == {
        "ok": True,
        "replied": True,
        "trigger": "reply_to_bot",
        "queue_remaining": 2,
        "search_notice_sent": False,
    }


def test_direct_reply_duplicate_and_send_failure_results():
    duplicate = reply_processing.direct_reply_duplicate_result(trigger="at", queue_remaining=1)
    assert duplicate == {
        "ok": True,
        "replied": False,
        "trigger": "at",
        "ignored": "duplicate_outbound",
        "queue_remaining": 1,
    }

    failed = reply_processing.direct_reply_send_failed_result(
        trigger="at",
        response={"status": "failed"},
    )
    assert failed == {
        "ok": False,
        "replied": False,
        "trigger": "at",
        "error": "send_failed",
        "response": {"status": "failed"},
    }


def test_direct_reply_generation_failure_notice_result():
    failed = reply_processing.direct_reply_generation_failed_result(
        trigger="at",
        reason="direct_hermes_empty",
        queue_remaining=2,
        failure_notice_sent=True,
        response={"ok": True},
    )
    assert failed == {
        "ok": False,
        "replied": False,
        "trigger": "at",
        "error": "direct_hermes_empty",
        "generation_failed": True,
        "failure_notice_sent": True,
        "queue_remaining": 2,
        "response": {"ok": True},
    }


def test_proactive_results_for_sent_duplicate_skipped_and_failure():
    proactive = {"score": 12.5, "reasons": ["message"], "direct_name_trigger": True}

    assert reply_processing.proactive_sent_result(proactive, queue_remaining=0, search_notice_sent=False) == {
        "ok": True,
        "proactive_replied": True,
        "score": 12.5,
        "reasons": ["message"],
        "queue_remaining": 0,
        "search_notice_sent": False,
    }
    assert reply_processing.proactive_duplicate_result(proactive, queue_remaining=2)["ignored"] == "duplicate_outbound"
    assert reply_processing.proactive_skipped_result(proactive, queue_remaining=3) == {
        "ok": True,
        "ignored": "proactive_model_skipped",
        "score": 12.5,
        "queue_remaining": 3,
    }
    assert reply_processing.proactive_send_failed_result({"bad": True}) == {
        "ok": False,
        "proactive_replied": False,
        "error": "send_failed",
        "response": {"bad": True},
    }
