from collections import deque
from datetime import datetime

from qq_hermes_bridge import proactive


def test_proactive_message_score_collects_name_topic_question_and_media_reasons():
    score, reasons = proactive.message_score(
        "Esti 论文怎么办？[图片]",
        name_triggers=["esti"],
        topic_keywords=["论文"],
        light_keywords=[],
        score_name_trigger=3.0,
        score_topic_keyword=2.0,
        score_light_keyword=0.5,
        score_question=1.5,
        score_open_question=2.5,
    )

    assert score == 1.0 + 3.0 + 2.0 + 1.5 + 2.5 + 1.0
    assert reasons == ["message", "name:esti", "topic:论文", "question", "open_question", "media"]


def test_update_score_core_uses_bounded_heat_and_night_scaling():
    state = {"score": 1.0, "last_decay_at": 100.0}
    result = proactive.update_score_core(
        state,
        activity=[{"user_id": 1}, {"user_id": 2}, {"user_id": 3}],
        base_add=2.0,
        reasons=["message"],
        now=100.0,
        blocked="",
        burst_message_threshold=3,
        burst_user_threshold=2,
        score_burst=4.0,
        score_multi_user=5.0,
        night_score_multiplier=0.5,
        is_night=True,
        threshold=6.0,
    )

    assert round(result["score"], 2) == 26.17
    assert state["score"] == result["score"]
    assert result["heat"] > 0
    assert result["opening_score"] == 0.0
    assert result["should_trigger"] is True
    assert result["reasons"] == ["message", "heat:activity", "heat:back_and_forth", "night_scaled"]
    assert result["threshold"] == 6.0


def test_update_score_core_marks_direct_name_trigger_without_threshold_bypass():
    state = {"score": 0.0}
    result = proactive.update_score_core(
        state,
        activity=[],
        base_add=1.0,
        reasons=["message", "name:esti"],
        now=100.0,
        blocked="",
        burst_message_threshold=99,
        burst_user_threshold=99,
        score_burst=4.0,
        score_multi_user=5.0,
        night_score_multiplier=1.0,
        is_night=False,
        threshold=99.0,
    )

    assert result["should_trigger"] is False
    assert result["direct_name_trigger"] is True


def test_rate_limit_prunes_old_proactive_reply_times():
    times = deque([10.0, 71.0, 90.0])

    assert proactive.can_send_now(times, now=100.0, window_seconds=30.0, max_replies=2) == "rate_limit"
    assert list(times) == [71.0, 90.0]

    assert proactive.can_send_now(times, now=101.0, window_seconds=30.0, max_replies=3) == ""

def test_daily_limit_blocks_when_configured_and_can_be_disabled():
    state = {"daily_count": 8, "last_proactive_at": 0.0, "sensitive_until": 0.0}

    assert proactive.block_reason(state, now=1000.0, group_cooldown_seconds=0.0, daily_limit=8) == "daily_limit"
    assert proactive.block_reason(state, now=1000.0, group_cooldown_seconds=0.0, daily_limit=0) == ""


def test_night_time_handles_cross_midnight_ranges():
    assert proactive.is_night_time(23 * 3600, night_start="22:30", night_end="07:00", fromtimestamp=lambda ts: datetime(2026, 1, 1, 23, 0))
    assert proactive.is_night_time(2 * 3600, night_start="22:30", night_end="07:00", fromtimestamp=lambda ts: datetime(2026, 1, 1, 2, 0))
    assert not proactive.is_night_time(12 * 3600, night_start="22:30", night_end="07:00", fromtimestamp=lambda ts: datetime(2026, 1, 1, 12, 0))
