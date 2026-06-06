import json
from pathlib import Path

from qq_hermes_bridge import content_analysis_log


def test_enabled_from_env_and_parse_group_ids():
    assert content_analysis_log.enabled_from_env("true") is True
    assert content_analysis_log.enabled_from_env("1") is True
    assert content_analysis_log.enabled_from_env("false") is False
    assert content_analysis_log.parse_group_ids("123, bad;456") == {123, 456}


def test_sanitize_text_redacts_obvious_secrets_and_clamps():
    text = "Authorization: Bearer abcdefghijklmnop token=secretvalue Cookie: p_skey=secret qrcode=https://x/login/qr-ticket " + "x" * 200

    result = content_analysis_log.sanitize_text(text, 40)

    assert result["truncated"] is True
    assert "abcdefghijklmnop" not in result["text"]
    assert "secretvalue" not in result["text"]
    assert "p_skey" not in result["text"]
    assert "qr-ticket" not in result["text"]
    assert "[REDACTED]" in result["text"]


def test_sanitize_record_drops_forbidden_keys_recursively():
    record = content_analysis_log.sanitize_record(
        {
            "kind": "direct_reply_sent",
            "prompt": "raw prompt",
            "stdout": "model output",
            "headers": {"Authorization": "Bearer secret"},
            "nested": {"reply": "正常回复", "token": "secret-token"},
        },
        max_chars=100,
    )

    rendered = repr(record)
    assert record["kind"] == "direct_reply_sent"
    assert "raw prompt" not in rendered
    assert "model output" not in rendered
    assert "Authorization" not in rendered
    assert "secret-token" not in rendered
    assert "正常回复" in rendered


def test_context_snapshot_bounds_and_avoids_raw_non_text_metadata():
    messages = [
        {"user_id": 1, "name": "甲", "text": "第一条", "image_url": "http://secret/image.jpg"},
        {"user_id": 2, "name": "乙", "role": "机器人", "text": "第二条", "message_id": "m2"},
        {"user_id": 3, "name": "丙", "text": "第三条"},
    ]

    snapshot = content_analysis_log.context_snapshot(messages, ["摘要A", "摘要B"], max_messages=2, max_chars=10)
    rendered = repr(snapshot)

    assert snapshot["message_count_total"] == 3
    assert snapshot["message_count_included"] == 2
    assert "第一条" not in rendered
    assert "第二条" in rendered
    assert "第三条" in rendered
    assert "image_url" not in rendered
    assert "http://secret" not in rendered
    assert len(snapshot["summaries"]) == 2


def test_append_jsonl_writes_without_printing(tmp_path):
    path = tmp_path / "nested" / "content_analysis.jsonl"

    content_analysis_log.append_jsonl(path, {"type": "content_analysis", "kind": "test", "message": {"text": "hello"}})

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["event"]["kind"] == "test"
    assert payload["event"]["message"]["text"] == "hello"
    assert path.stat().st_mode & 0o077 == 0
