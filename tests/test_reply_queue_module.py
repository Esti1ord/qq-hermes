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
