from qq_hermes_bridge import reply_queue


def test_reply_queue_capacity_separates_direct_and_proactive():
    queues = {}

    direct = reply_queue.queue_for_group(1, queues=queues, max_pending_replies=3, proactive_rate_limit_max_replies=6, max_pending_direct_replies=20)
    proactive = reply_queue.queue_for_group(1, queues=queues, max_pending_replies=3, proactive_rate_limit_max_replies=6, kind="proactive", max_pending_direct_replies=20)

    assert direct.maxlen == 20
    assert proactive.maxlen == 6
    assert reply_queue.size(1, queues=queues, max_pending_replies=3, proactive_rate_limit_max_replies=6, max_pending_direct_replies=20) == 0


def test_enqueue_dequeue_prioritizes_direct_fifo_over_proactive():
    queues = {}

    assert reply_queue.enqueue(1, {"kind": "proactive", "id": "p1"}, queues=queues, max_pending_replies=2, proactive_rate_limit_max_replies=2) == {"queued": True, "kind": "proactive", "queue_size": 1, "queue_limit": 2}
    assert reply_queue.enqueue(1, {"kind": "direct", "id": "d1"}, queues=queues, max_pending_replies=2, proactive_rate_limit_max_replies=2) == {"queued": True, "kind": "direct", "queue_size": 1, "queue_limit": 2}
    assert reply_queue.enqueue(1, {"kind": "direct", "id": "d2"}, queues=queues, max_pending_replies=2, proactive_rate_limit_max_replies=2) == {"queued": True, "kind": "direct", "queue_size": 2, "queue_limit": 2}
    assert reply_queue.enqueue(1, {"kind": "direct", "id": "d3"}, queues=queues, max_pending_replies=2, proactive_rate_limit_max_replies=2) == {"queued": False, "reason": "reply_queue_full", "kind": "direct", "queue_size": 2, "queue_limit": 2}

    assert reply_queue.dequeue(1, queues=queues, max_pending_replies=2, proactive_rate_limit_max_replies=2) == {"kind": "direct", "id": "d1"}
    assert reply_queue.dequeue(1, queues=queues, max_pending_replies=2, proactive_rate_limit_max_replies=2) == {"kind": "direct", "id": "d2"}
    assert reply_queue.dequeue(1, queues=queues, max_pending_replies=2, proactive_rate_limit_max_replies=2) == {"kind": "proactive", "id": "p1"}
    assert reply_queue.dequeue(1, queues=queues, max_pending_replies=2, proactive_rate_limit_max_replies=2) is None


def test_enqueue_replaces_oldest_proactive_when_proactive_queue_is_full():
    queues = {}

    assert reply_queue.enqueue(1, {"kind": "proactive", "id": "p1"}, queues=queues, max_pending_replies=2, proactive_rate_limit_max_replies=2)["queued"] is True
    assert reply_queue.enqueue(1, {"kind": "proactive", "id": "p2"}, queues=queues, max_pending_replies=2, proactive_rate_limit_max_replies=2)["queued"] is True
    replaced = reply_queue.enqueue(1, {"kind": "proactive", "id": "p3"}, queues=queues, max_pending_replies=2, proactive_rate_limit_max_replies=2)

    assert replaced == {
        "queued": True,
        "reason": "proactive_replaced_oldest",
        "kind": "proactive",
        "queue_size": 2,
        "queue_limit": 2,
        "dropped_oldest": True,
    }
    assert reply_queue.dequeue(1, queues=queues, max_pending_replies=2, proactive_rate_limit_max_replies=2) == {"kind": "proactive", "id": "p2"}
    assert reply_queue.dequeue(1, queues=queues, max_pending_replies=2, proactive_rate_limit_max_replies=2) == {"kind": "proactive", "id": "p3"}


def make_direct_intent(*, group_id=1, user_id=11, text="Esti 问题", trigger="at", message=None, media_context="", enqueued_at=1.0, ocr_task=None):
    if message is None:
        message = [
            {"type": "at", "data": {"qq": "3975680980"}},
            {"type": "text", "data": {"text": text}},
        ]
    intent = {
        "kind": "direct",
        "event": {"group_id": group_id, "user_id": user_id, "message": message},
        "user_text": text,
        "trigger": trigger,
        "media_context": media_context,
        "_perf_enqueued_at": enqueued_at,
    }
    if ocr_task is not None:
        intent["ocr_task"] = ocr_task
    return intent


def enqueue_for_test(queues, intent, *, window_ms=0, now=None, group_id=1):
    return reply_queue.enqueue(
        group_id,
        intent,
        queues=queues,
        max_pending_replies=3,
        proactive_rate_limit_max_replies=3,
        max_pending_direct_replies=3,
        direct_coalesce_window_ms=window_ms,
        now=now,
    )


def test_direct_coalescing_disabled_by_default_keeps_separate_items():
    queues = {}

    first = enqueue_for_test(queues, make_direct_intent(text="Esti 第一条", enqueued_at=1.0), window_ms=0, now=1.0)
    second = enqueue_for_test(queues, make_direct_intent(text="Esti 第二条", enqueued_at=1.1), window_ms=0, now=1.1)

    assert first == {"queued": True, "kind": "direct", "queue_size": 1, "queue_limit": 3}
    assert second == {"queued": True, "kind": "direct", "queue_size": 2, "queue_limit": 3}
    assert reply_queue.size_by_kind(1, "direct", queues=queues, max_pending_replies=3, proactive_rate_limit_max_replies=3, max_pending_direct_replies=3) == 2


def test_direct_coalescing_merges_same_group_sender_and_route_with_ordered_prompt_text():
    queues = {}
    first_intent = make_direct_intent(text="Esti 第一条", enqueued_at=10.0)
    second_intent = make_direct_intent(text="Esti 第二条", enqueued_at=10.2)

    first = enqueue_for_test(queues, first_intent, window_ms=500, now=10.0)
    second = enqueue_for_test(queues, second_intent, window_ms=500, now=10.2)

    assert first["queued"] is True
    assert second["queued"] is True
    assert second["coalesced"] is True
    assert second["queue_size"] == 1
    assert second["merged_count"] == 1
    assert second["coalesced_count"] == 2
    queued = reply_queue.dequeue(1, queues=queues, max_pending_replies=3, proactive_rate_limit_max_replies=3, max_pending_direct_replies=3)
    assert queued is first_intent
    assert queued["event"] is second_intent["event"]
    assert queued["user_text"] == "Esti 第二条"
    prompt_text = reply_queue.coalesced_user_text_for_prompt(queued, default=queued["user_text"])
    assert prompt_text.index("1. Esti 第一条") < prompt_text.index("2. Esti 第二条")
    assert "主要回复最后一条" in prompt_text


def test_direct_coalescing_skips_different_sender_and_route():
    queues = {}

    enqueue_for_test(queues, make_direct_intent(user_id=1, text="Esti 第一条", trigger="at", enqueued_at=1.0), window_ms=500, now=1.0)
    different_sender = enqueue_for_test(queues, make_direct_intent(user_id=2, text="Esti 第二条", trigger="at", enqueued_at=1.1), window_ms=500, now=1.1)
    different_route = enqueue_for_test(queues, make_direct_intent(user_id=2, text="Esti 第三条", trigger="name", message=[{"type": "text", "data": {"text": "Esti 第三条"}}], enqueued_at=1.2), window_ms=500, now=1.2)

    assert different_sender.get("coalesced") is not True
    assert different_sender["queue_size"] == 2
    assert different_route.get("coalesced") is not True
    assert different_route["queue_size"] == 3


def test_direct_coalescing_skips_proactive_reply_media_command_ocr_and_started_items():
    unsafe_cases = [
        make_direct_intent(text="Esti 回复", message=[{"type": "reply", "data": {"id": "abc"}}, {"type": "text", "data": {"text": "Esti 回复"}}], enqueued_at=2.1),
        make_direct_intent(text="Esti 图片", message=[{"type": "image", "data": {"file": "x"}}, {"type": "text", "data": {"text": "Esti 图片"}}], enqueued_at=2.1),
        make_direct_intent(text="Esti OCR", media_context="识别到了文字", enqueued_at=2.1),
        make_direct_intent(text="Esti OCR task", ocr_task=object(), enqueued_at=2.1),
        make_direct_intent(text="/context", message=[{"type": "text", "data": {"text": "/context"}}], enqueued_at=2.1),
        {**make_direct_intent(text="Esti started", enqueued_at=2.1), "_reply_started": True},
    ]

    queues = {}
    enqueue_for_test(queues, make_direct_intent(text="Esti 第一条", enqueued_at=2.0), window_ms=500, now=2.0)
    proactive = enqueue_for_test(queues, {"kind": "proactive", "event": {"group_id": 1, "user_id": 11}, "proactive": {"score": 20}}, window_ms=500, now=2.1)
    assert proactive.get("coalesced") is not True
    assert proactive["queue_size"] == 1
    assert reply_queue.size_by_kind(1, "direct", queues=queues, max_pending_replies=3, proactive_rate_limit_max_replies=3, max_pending_direct_replies=3) == 1

    for unsafe in unsafe_cases:
        queues = {}
        enqueue_for_test(queues, make_direct_intent(text="Esti 第一条", enqueued_at=2.0), window_ms=500, now=2.0)
        result = enqueue_for_test(queues, unsafe, window_ms=500, now=2.1)
        assert result.get("coalesced") is not True
        assert result["queue_size"] == 2


def test_direct_coalescing_respects_window_ms():
    queues = {}

    enqueue_for_test(queues, make_direct_intent(text="Esti 第一条", enqueued_at=1.0), window_ms=100, now=1.0)
    result = enqueue_for_test(queues, make_direct_intent(text="Esti 太晚了", enqueued_at=1.2), window_ms=100, now=1.2)

    assert result.get("coalesced") is not True
    assert result["queue_size"] == 2


def test_direct_coalescing_can_merge_matching_tail_when_queue_is_at_capacity():
    queues = {}

    enqueue_for_test(queues, make_direct_intent(text="Esti 第一条", enqueued_at=1.0), window_ms=500, now=1.0)
    enqueue_for_test(queues, make_direct_intent(user_id=22, text="Esti 别人的问题", enqueued_at=1.1), window_ms=500, now=1.1)
    enqueue_for_test(queues, make_direct_intent(user_id=33, text="Esti 队列满", enqueued_at=1.2), window_ms=500, now=1.2)
    result = enqueue_for_test(queues, make_direct_intent(user_id=33, text="Esti 继续问", enqueued_at=1.3), window_ms=500, now=1.3)

    assert result["queued"] is True
    assert result["coalesced"] is True
    assert result["queue_size"] == 3
