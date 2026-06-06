import json

from qq_hermes_bridge import logging_utils


def test_pick_template_is_stable_within_same_minute_and_varies_by_key():
    templates = {"empty": ["a", "b", "c"]}

    first = logging_utils.pick_template("empty", key="x", templates=templates, minute_bucket=123)
    second = logging_utils.pick_template("empty", key="x", templates=templates, minute_bucket=123)
    other = logging_utils.pick_template("empty", key="y", templates=templates, minute_bucket=123)

    assert first == second
    assert first in templates["empty"]
    assert other in templates["empty"]


def test_json_log_line_contains_timestamp_and_event():
    line = logging_utils.json_log_line({"type": "event"}, now_fn=lambda fmt: "2026-06-03 12:00:00")

    data = json.loads(line)
    assert data == {"ts": "2026-06-03 12:00:00", "event": {"type": "event"}}
