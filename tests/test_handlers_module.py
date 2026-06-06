from qq_hermes_bridge import handlers


def test_event_log_record_keeps_route_relevant_fields_only():
    event = {
        "post_type": "message",
        "message_type": "group",
        "group_id": 123,
        "user_id": 456,
        "self_id": 789,
        "message": "secret body",
    }

    assert handlers.event_log_record(event) == {
        "type": "event",
        "post_type": "message",
        "message_type": "group",
        "group_id": 123,
        "user_id": 456,
        "self_id": 789,
    }


def test_precheck_group_message_ignores_non_group_and_other_group():
    non_group = {"post_type": "notice", "message_type": "group", "group_id": 1}
    other_group = {"post_type": "message", "message_type": "group", "group_id": 2}

    assert handlers.precheck_group_message(non_group, is_allowed_group_fn=lambda event: True) == {
        "ok": True,
        "ignored": "not_group_message",
    }
    assert handlers.precheck_group_message(other_group, is_allowed_group_fn=lambda event: False) == {
        "ok": True,
        "ignored": "other_group",
    }
    assert handlers.precheck_group_message({"post_type": "message", "message_type": "group", "group_id": 1}, is_allowed_group_fn=lambda event: True) is None


def test_command_action_selects_first_matching_command():
    event = {"group_id": 123}
    calls = []

    action = handlers.command_action_for_text(
        "/search 河海土木",
        event=event,
        group_id=123,
        is_context_command_fn=lambda text: False,
        is_search_command_fn=lambda text: text.startswith("/search"),
        search_command_query_fn=lambda text: text.removeprefix("/search").strip(),
        is_deepseek_command_fn=lambda text: False,
        deepseek_command_query_fn=lambda text: "",
        is_jrrp_command_fn=lambda text: False,
        sender_name_fn=lambda event: "甲",
        build_context_reply_fn=lambda group_id: "context",
        build_search_reply_fn=lambda query, group_id=None: calls.append(("search", query, group_id)) or "search reply",
        build_deepseek_reply_fn=lambda query, group_id=None: "deepseek reply",
        build_jrrp_reply_fn=lambda user_id, name: ("jrrp reply", True),
    )

    assert action == {
        "kind": "threaded_immediate",
        "command": "search",
        "query": "河海土木",
        "trigger": "search_command",
        "log_type": "search_command",
        "remember_context": False,
        "extra": {"query": "河海土木"},
    }
    assert calls == []


def test_command_action_handles_context_and_jrrp_metadata():
    event = {"user_id": 456, "group_id": 123}

    context_action = handlers.command_action_for_text(
        "/context",
        event=event,
        group_id=123,
        is_context_command_fn=lambda text: True,
        is_search_command_fn=lambda text: False,
        search_command_query_fn=lambda text: "",
        is_deepseek_command_fn=lambda text: False,
        deepseek_command_query_fn=lambda text: "",
        is_jrrp_command_fn=lambda text: False,
        sender_name_fn=lambda event: "甲",
        build_context_reply_fn=lambda group_id: "context reply",
        build_search_reply_fn=lambda query, group_id=None: "search reply",
        build_deepseek_reply_fn=lambda query, group_id=None: "deepseek reply",
        build_jrrp_reply_fn=lambda user_id, name: ("jrrp reply", True),
    )
    assert context_action["trigger"] == "context_command"
    assert context_action["remember_context"] is True

    jrrp_action = handlers.command_action_for_text(
        "jrrp",
        event=event,
        group_id=123,
        is_context_command_fn=lambda text: False,
        is_search_command_fn=lambda text: False,
        search_command_query_fn=lambda text: "",
        is_deepseek_command_fn=lambda text: False,
        deepseek_command_query_fn=lambda text: "",
        is_jrrp_command_fn=lambda text: True,
        sender_name_fn=lambda event: "甲",
        build_context_reply_fn=lambda group_id: "context reply",
        build_search_reply_fn=lambda query, group_id=None: "search reply",
        build_deepseek_reply_fn=lambda query, group_id=None: "deepseek reply",
        build_jrrp_reply_fn=lambda user_id, name: ("jrrp reply", False),
    )
    assert jrrp_action["reply"] == "jrrp reply"
    assert jrrp_action["extra"] == {"first_draw": False}


def test_command_action_returns_none_for_plain_chat():
    action = handlers.command_action_for_text(
        "普通聊天",
        event={"group_id": 123},
        group_id=123,
        is_context_command_fn=lambda text: False,
        is_search_command_fn=lambda text: False,
        search_command_query_fn=lambda text: "",
        is_deepseek_command_fn=lambda text: False,
        deepseek_command_query_fn=lambda text: "",
        is_jrrp_command_fn=lambda text: False,
        sender_name_fn=lambda event: "甲",
        build_context_reply_fn=lambda group_id: "context reply",
        build_search_reply_fn=lambda query, group_id=None: "search reply",
        build_deepseek_reply_fn=lambda query, group_id=None: "deepseek reply",
        build_jrrp_reply_fn=lambda user_id, name: ("jrrp reply", True),
    )
    assert action is None


def test_proactive_action_for_non_direct_reply_queues_when_threshold_met():
    logs = []
    queued_payloads = []
    event = {"group_id": 123}
    proactive = {"should_trigger": True, "score": 20.0, "reasons": ["message"]}

    action = handlers.proactive_action_for_non_direct_reply(
        event,
        proactive=proactive,
        group_id=123,
        enqueue_reply_intent_fn=lambda group_id, payload: queued_payloads.append((group_id, payload)) or {"queued": True, "queue_size": 1},
        log_fn=logs.append,
    )

    assert action == {"kind": "process_reply_intent", "group_id": 123, "intent": {"kind": "proactive"}}
    assert queued_payloads == [(123, {"kind": "proactive", "event": event, "proactive": proactive})]
    assert logs == []


def test_proactive_action_reports_not_at_or_queue_failure():
    skipped = handlers.proactive_action_for_non_direct_reply(
        {"group_id": 123},
        proactive={"should_trigger": False, "score": 3.0, "blocked": "cooldown"},
        group_id=123,
        enqueue_reply_intent_fn=lambda group_id, payload: {"queued": True},
        log_fn=lambda event: None,
    )
    assert skipped == {"ok": True, "ignored": "not_at_me", "proactive_score": 3.0, "blocked": "cooldown"}

    logs = []
    failed = handlers.proactive_action_for_non_direct_reply(
        {"group_id": 123},
        proactive={"should_trigger": True, "score": 20.0},
        group_id=123,
        enqueue_reply_intent_fn=lambda group_id, payload: {"queued": False, "reason": "reply_queue_full", "queue_size": 3, "queue_limit": 3},
        log_fn=logs.append,
    )
    assert failed["ignored"] == "reply_queue_full"
    assert failed["score"] == 20.0
    assert logs[0]["reason"] == "reply_queue_full"


def test_direct_action_validates_unclear_cooldown_and_queue():
    event = {"group_id": 123, "user_id": 456}

    unclear = handlers.direct_action_for_event(
        event,
        user_text="？",
        skip_unclear_mentions=True,
        should_skip_unclear_mention_fn=lambda text: True,
        should_rate_limit_fn=lambda group_id, user_id: (False, ""),
        group_id_fn=lambda event: 123,
        is_reply_to_me_fn=lambda event: False,
        is_at_me_fn=lambda event: True,
        enqueue_reply_intent_fn=lambda group_id, payload: {"queued": True},
        log_fn=lambda event: None,
    )
    assert unclear == {"ok": True, "ignored": "unclear_mention"}

    limited = handlers.direct_action_for_event(
        event,
        user_text="hi",
        skip_unclear_mentions=True,
        should_skip_unclear_mention_fn=lambda text: False,
        should_rate_limit_fn=lambda group_id, user_id: (True, "等等"),
        group_id_fn=lambda event: 123,
        is_reply_to_me_fn=lambda event: False,
        is_at_me_fn=lambda event: True,
        enqueue_reply_intent_fn=lambda group_id, payload: {"queued": True},
        log_fn=lambda event: None,
    )
    assert limited == {"ok": True, "ignored": "user_cooldown", "message": "等等"}

    queued_payloads = []
    queued = handlers.direct_action_for_event(
        event,
        user_text="hi",
        skip_unclear_mentions=True,
        should_skip_unclear_mention_fn=lambda text: False,
        should_rate_limit_fn=lambda group_id, user_id: (False, ""),
        group_id_fn=lambda event: 123,
        is_reply_to_me_fn=lambda event: True,
        is_at_me_fn=lambda event: False,
        enqueue_reply_intent_fn=lambda group_id, payload: queued_payloads.append((group_id, payload)) or {"queued": True},
        log_fn=lambda event: None,
    )
    assert queued == {"kind": "process_reply_intent", "group_id": 123, "intent": {"kind": "direct"}}
    assert queued_payloads[0][1]["trigger"] == "reply_to_bot"


def test_prepare_direct_text_and_trigger_name():
    assert handlers.prepare_direct_user_text("") == "（对方只 @ 了我，没有附加文本）"
    assert handlers.prepare_direct_user_text("  hi  ") == "  hi  "
    assert handlers.direct_trigger_name(is_reply_to_bot=True, is_at_bot=False) == "reply_to_bot"
    assert handlers.direct_trigger_name(is_reply_to_bot=True, is_at_bot=True) == "at"
