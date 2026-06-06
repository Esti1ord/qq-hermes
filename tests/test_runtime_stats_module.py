from qq_hermes_bridge import runtime_stats


def test_safe_event_record_excludes_raw_message_and_sender_names():
    event = {
        "post_type": "message",
        "message_type": "group",
        "group_id": 123,
        "user_id": 456,
        "sender": {"nickname": "SensitiveNick"},
        "message": [
            {"type": "reply", "data": {"text": "quoted secret"}},
            {"type": "at", "data": {"qq": "3975680980"}},
            {"type": "text", "data": {"text": "super secret body"}},
            {"type": "image", "data": {"url": "http://secret"}},
        ],
    }

    record = runtime_stats.safe_event_record(
        event,
        message_to_text_fn=lambda message: "super secret body",
        is_allowed_group_fn=lambda event: True,
        is_at_me_fn=lambda event: True,
        is_reply_to_me_fn=lambda event: False,
        user_hash_salt="salt",
    )
    rendered = repr(record)

    assert "super secret body" not in rendered
    assert "quoted secret" not in rendered
    assert "SensitiveNick" not in rendered
    assert record["text_len"] == len("super secret body")
    assert record["text_len_bucket"] == "1-20"
    assert record["segment_types"] == {"reply": 1, "at": 1, "text": 1, "image": 1}
    assert record["has_non_text"] is True
    assert record["user_hash"] == runtime_stats.safe_user_hash(456, salt="salt")


def test_safe_user_hash_is_stable_and_salted():
    assert runtime_stats.safe_user_hash(123, salt="a") == runtime_stats.safe_user_hash(123, salt="a")
    assert runtime_stats.safe_user_hash(123, salt="a") != runtime_stats.safe_user_hash(123, salt="b")


def test_text_len_bucket_ranges():
    assert runtime_stats.text_len_bucket(0) == "0"
    assert runtime_stats.text_len_bucket(20) == "1-20"
    assert runtime_stats.text_len_bucket(80) == "21-80"
    assert runtime_stats.text_len_bucket(200) == "81-200"
    assert runtime_stats.text_len_bucket(500) == "201-500"
    assert runtime_stats.text_len_bucket(501) == "501-1200"
    assert runtime_stats.text_len_bucket(1201) == "1200+"


def test_duration_bucket_ranges():
    assert runtime_stats.duration_bucket(0) == "0ms"
    assert runtime_stats.duration_bucket(100) == "1-100ms"
    assert runtime_stats.duration_bucket(500) == "101-500ms"
    assert runtime_stats.duration_bucket(1000) == "501-1000ms"
    assert runtime_stats.duration_bucket(3000) == "1-3s"
    assert runtime_stats.duration_bucket(10000) == "3-10s"
    assert runtime_stats.duration_bucket(30000) == "10-30s"
    assert runtime_stats.duration_bucket(30001) == "30s+"


def test_safe_hash_and_interaction_hash_are_stable_and_salted():
    assert runtime_stats.safe_hash("abc", salt="a") == runtime_stats.safe_hash("abc", salt="a")
    assert runtime_stats.safe_hash("abc", salt="a") != runtime_stats.safe_hash("abc", salt="b")
    assert runtime_stats.safe_interaction_hash([123, "m1"], salt="a") == runtime_stats.safe_interaction_hash([123, "m1"], salt="a")
    assert runtime_stats.safe_interaction_hash([123, "m1"], salt="a") != runtime_stats.safe_interaction_hash([123, "m1"], salt="b")


def test_sanitize_stat_fields_drops_unsafe_keys_and_keeps_safe_scalars():
    stat = runtime_stats.sanitize_stat_fields(
        "route_decision",
        {
            "group_id": 123,
            "message": "secret",
            "reply_text": "secret reply",
            "prompt_len": 99,
            "query": "secret query",
            "image_url": "https://secret.example/image.png",
            "url_host": "secret.example",
            "ocr_text": "secret ocr",
            "token": "secret token",
            "nested": {"safe_count": 2, "prompt": "nested secret", "response_body": "secret response"},
            "reasons": ["message", "topic:精神状态"],
            "segment_types": {"text": 1, "image": 2},
        },
    )

    rendered = repr(stat)
    assert stat["type"] == "runtime_stat"
    assert stat["stat"] == "route_decision"
    assert stat["group_id"] == 123
    assert "secret" not in rendered
    assert "message" not in stat
    assert "reply_text" not in stat
    assert "prompt_len" not in stat
    assert "query" not in stat
    assert "image_url" not in stat
    assert "url_host" not in stat
    assert "ocr_text" not in stat
    assert "token" not in stat
    assert stat["nested"] == {"safe_count": 2}
    assert stat["reasons"] == ["message", "topic:精神状态"]
    assert stat["segment_types"] == {"text": 1, "image": 2}


def test_runtime_perf_fields_survive_without_content():
    stat = runtime_stats.sanitize_stat_fields(
        "interaction_finished",
        {
            "interaction_id": "abc123",
            "route": "direct",
            "kind": "direct",
            "phase": "send",
            "purpose": "direct_reply",
            "provider": "hermes",
            "backend": "curl",
            "duration_ms": 1234,
            "duration_bucket": runtime_stats.duration_bucket(1234),
            "queue_wait_ms": 50,
            "e2e_ms": 2222,
            "input_chars": 100,
            "output_len": 20,
            "result_len": 30,
            "media_count": 1,
            "cache_hit": True,
            "inflight_joined": False,
            "duplicate_suppressed": False,
            "query_len": 12,
            "query_len_bucket": runtime_stats.length_bucket(12),
        },
    )

    assert stat["interaction_id"] == "abc123"
    assert stat["route"] == "direct"
    assert stat["duration_ms"] == 1234
    assert stat["duration_bucket"] == "1-3s"
    assert stat["queue_wait_ms"] == 50
    assert stat["e2e_ms"] == 2222


def test_runtime_summary_contains_only_counters_and_uptime():
    summary = runtime_stats.runtime_summary({"events_total": 2, "send_errors": 1}, started_at=100.0, now=130.0)

    assert summary == {"uptime_s": 30, "counters": {"events_total": 2, "send_errors": 1}}
