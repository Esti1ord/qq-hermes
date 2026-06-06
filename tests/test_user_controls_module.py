from qq_hermes_bridge import user_controls


def test_user_cooldown_key_rate_limit_and_mark_replied():
    replied_at = {}

    assert user_controls.cooldown_key(1, 2) == "1:2"
    assert user_controls.should_rate_limit(1, 2, replied_at=replied_at, cooldown_seconds=20.0, now=100.0) == (False, "")

    user_controls.mark_user_replied(1, 2, replied_at=replied_at, now=100.0)
    limited, message = user_controls.should_rate_limit(1, 2, replied_at=replied_at, cooldown_seconds=20.0, now=105.0)

    assert limited is True
    assert "15 秒" in message


def test_unclear_mention_detects_empty_after_at_and_punctuation():
    assert user_controls.should_skip_unclear_mention("@Esti ？？！")
    assert not user_controls.should_skip_unclear_mention("@Esti 讲讲论文")


def test_style_hint_is_stable_for_same_seed_and_uses_message_text_function():
    hints = ["a", "b", "c"]
    event = {"user_id": 42, "message": [{"type": "text", "data": {"text": "hello"}}]}

    first = user_controls.style_hint_for(event, style_hints=hints, message_to_text_fn=lambda message: "hello")
    second = user_controls.style_hint_for(event, style_hints=hints, message_to_text_fn=lambda message: "hello")

    assert first == second
    assert first in hints
