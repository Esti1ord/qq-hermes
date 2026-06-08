from pathlib import Path

from qq_hermes_bridge import hermes_runtime


def test_build_hermes_cmd_adds_group_session_model_provider_and_source():
    cmd = hermes_runtime.build_hermes_cmd(
        "prompt",
        group_id=781423661,
        hermes_bin="hermes",
        group_sessions_enabled=True,
        group_session_prefix="qq-group",
        target_group_id=975805598,
        hermes_model="chat-model",
        hermes_provider="chat-provider",
    )

    assert cmd[:4] == ["hermes", "chat", "-q", "prompt"]
    assert cmd[cmd.index("--continue") + 1] == "qq-group-781423661"
    assert cmd[cmd.index("--source") + 1] == "qq-bridge:781423661"
    assert cmd[cmd.index("--model") + 1] == "chat-model"
    assert cmd[cmd.index("--provider") + 1] == "chat-provider"


def test_build_hermes_cmd_removes_null_bytes_from_prompt():
    cmd = hermes_runtime.build_hermes_cmd(
        "前\x00后",
        group_id=781423661,
        hermes_bin="hermes",
        group_sessions_enabled=False,
        group_session_prefix="qq-group",
        target_group_id=975805598,
    )

    assert cmd[:4] == ["hermes", "chat", "-q", "前后"]
    assert "\x00" not in cmd[3]


def test_session_sqlite_inspection_reads_counts_chars_and_latest_title(tmp_path):
    import sqlite3

    db_path = tmp_path / "state.db"
    con = sqlite3.connect(db_path)
    try:
        con.execute("create table sessions (id text, title text, message_count integer, started_at integer, ended_at integer)")
        con.execute("create table messages (id integer primary key, session_id text, role text, content text)")
        con.execute("insert into sessions values ('old', 'qq-group-1', 2, 1, 1)")
        con.execute("insert into sessions values ('new', 'qq-group-1', 3, 2, 2)")
        con.execute("insert into messages (session_id, role, content) values ('new', 'user', '你好')")
        con.execute("insert into messages (session_id, role, content) values ('new', 'assistant', '回复')")
        con.commit()
    finally:
        con.close()

    assert hermes_runtime.sqlite_message_count_for_session("new", db_path=db_path) == 3
    assert hermes_runtime.session_id_by_title("qq-group-1", db_path=db_path) == "new"
    assert hermes_runtime.estimated_session_body_chars("new", db_path=db_path) == len("user") + len("你好") + 32 + len("assistant") + len("回复") + 32


def test_session_summary_prompt_is_clipped_and_mentions_group_reset():
    text = hermes_runtime.session_summary_prompt(
        781423661,
        summaries="摘要" * 20,
        recent="最近" * 20,
        max_chars=80,
    )

    assert text.startswith("这是 QQ 群 781423661 的桥接会话自动压缩摘要")
    assert len(text) == 80


def test_delete_session_cmd_uses_hermes_sessions_delete_yes():
    assert hermes_runtime.delete_session_cmd("hermes", "abc123") == [
        "hermes",
        "sessions",
        "delete",
        "--yes",
        "abc123",
    ]


def test_session_delete_log_event_summarizes_success_and_clips_output():
    event = hermes_runtime.session_delete_log_event(
        session_id="abc123",
        reason="autocompact_threshold",
        returncode=0,
        stdout="x" * 600,
        stderr="e" * 600,
    )

    assert event == {
        "type": "hermes_session_deleted",
        "session_id": "abc123",
        "reason": "autocompact_threshold",
        "returncode": 0,
        "stdout": "x" * 500,
        "stderr": "e" * 500,
    }


def test_session_delete_log_event_summarizes_failure():
    event = hermes_runtime.session_delete_log_event(
        session_id="abc123",
        reason="autocompact_threshold",
        returncode=1,
        stdout="nope",
        stderr="bad",
    )

    assert event["type"] == "hermes_session_delete_error"
    assert event["stdout"] == "nope"
    assert event["stderr"] == "bad"


def test_session_needs_compaction_uses_message_and_body_thresholds():
    needs, stats = hermes_runtime.session_needs_compaction(
        "session",
        max_messages=10,
        max_body_chars=100,
        message_count_fn=lambda session_id: 12,
        body_chars_fn=lambda session_id: 50,
    )

    assert needs is True
    assert stats == {"message_count": 12, "body_chars": 50}


def test_strip_session_footer_removes_cli_warning_lines():
    output = "Warning: Unknown toolsets: mcp-codegraph\n共工那波确实很东北\n\nsession_id: 20260608_132716_3e3e54"

    assert hermes_runtime.strip_session_footer(output) == "共工那波确实很东北"


def test_strip_session_footer_keeps_natural_warning_wording():
    output = "Warning: 这句是模型自然输出\n\nsession_id: 20260608_132716_3e3e54"

    assert hermes_runtime.strip_session_footer(output) == "Warning: 这句是模型自然输出"
