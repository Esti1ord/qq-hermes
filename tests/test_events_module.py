from collections import deque

from qq_hermes_bridge import events


def test_event_dedupe_key_prefers_message_id():
    event = {"group_id": 1, "message_id": 42, "user_id": 9, "time": 100, "message": "不同内容"}

    assert events.event_dedupe_key(event, message_to_text_fn=str) == "1:42"


def test_event_dedupe_key_falls_back_to_text_hash_and_seen_window():
    event = {"group_id": 1, "user_id": 9, "time": 100, "message": [{"type": "text", "data": {"text": "hi"}}]}
    keys = deque(maxlen=2)
    key_set = set()

    key = events.event_dedupe_key(event, message_to_text_fn=lambda message: "hi")

    assert key.startswith("1:9:100:")
    assert events.mark_event_seen(event, keys=keys, key_set=key_set, message_to_text_fn=lambda message: "hi")
    assert not events.mark_event_seen(event, keys=keys, key_set=key_set, message_to_text_fn=lambda message: "hi")

    events.mark_event_seen({"group_id": 1, "message_id": "a"}, keys=keys, key_set=key_set, message_to_text_fn=str)
    events.mark_event_seen({"group_id": 1, "message_id": "b"}, keys=keys, key_set=key_set, message_to_text_fn=str)
    assert key not in key_set
