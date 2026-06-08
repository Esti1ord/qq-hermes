"""Hermes CLI/session helpers for the QQ bridge."""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Callable


def subprocess_safe_text(text: str | None) -> str:
    """Remove NUL bytes that Python subprocess argv cannot carry."""
    return str(text or "").replace("\x00", "")


def hermes_session_name_for_group(
    group_id: int | None,
    *,
    target_group_id: int,
    group_session_prefix: str,
) -> str:
    gid = group_id if group_id is not None else target_group_id
    return f"{group_session_prefix}-{gid}"


def build_hermes_cmd(
    prompt: str,
    *,
    group_id: int | None = None,
    use_group_session: bool = True,
    model: str | None = None,
    provider: str | None = None,
    hermes_bin: str,
    group_sessions_enabled: bool,
    group_session_prefix: str,
    target_group_id: int,
    hermes_model: str = "",
    hermes_provider: str = "",
) -> list[str]:
    safe_prompt = subprocess_safe_text(prompt)
    cmd = [hermes_bin, "chat", "-q", safe_prompt, "--quiet"]
    gid = group_id if group_id is not None else target_group_id
    if group_sessions_enabled and use_group_session:
        session_name = hermes_session_name_for_group(
            group_id,
            target_group_id=target_group_id,
            group_session_prefix=group_session_prefix,
        )
        cmd.extend(["--continue", session_name, "--source", f"qq-bridge:{gid}"])
    selected_model = hermes_model if model is None else model
    selected_provider = hermes_provider if provider is None else provider
    if selected_model:
        cmd.extend(["--model", selected_model])
    if selected_provider:
        cmd.extend(["--provider", selected_provider])
    return cmd


HERMES_CLI_WARNING_PREFIXES = (
    "Warning: Unknown toolsets:",
)


def strip_cli_warning_lines(output: str) -> str:
    """Remove Hermes CLI diagnostic warning lines that can appear on stdout."""
    lines = []
    for line in str(output or "").splitlines():
        clean = line.strip()
        if any(clean.startswith(prefix) for prefix in HERMES_CLI_WARNING_PREFIXES):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def output_indicates_missing_session(output: str) -> bool:
    return "No session found matching" in output or "Use 'hermes sessions list'" in output


def extract_session_id(output: str) -> str:
    match = re.search(r"session_id:\s*([A-Za-z0-9_\-]+)", output or "")
    return match.group(1) if match else ""


def strip_session_footer(output: str) -> str:
    clean = strip_cli_warning_lines(output)
    return re.sub(r"\n+session_id:\s*[A-Za-z0-9_\-]+\s*$", "", clean).strip()


def sqlite_message_count_for_session(session_id: str, *, db_path: Path) -> int:
    if not db_path.exists():
        return 0
    con = sqlite3.connect(str(db_path))
    try:
        row = con.execute("select message_count from sessions where id = ?", (session_id,)).fetchone()
        return int(row[0] or 0) if row else 0
    finally:
        con.close()


def estimated_session_body_chars(session_id: str, *, db_path: Path) -> int:
    if not db_path.exists():
        return 0
    con = sqlite3.connect(str(db_path))
    try:
        rows = con.execute("select role, content from messages where session_id = ? order by id", (session_id,)).fetchall()
    finally:
        con.close()
    total = 0
    for role, content in rows:
        total += len(str(role or "")) + len(str(content or "")) + 32
    return total


def session_id_by_title(session_name: str, *, db_path: Path) -> str:
    if not db_path.exists():
        return ""
    con = sqlite3.connect(str(db_path))
    try:
        row = con.execute(
            "select id from sessions where title = ? order by coalesce(ended_at, started_at) desc limit 1",
            (session_name,),
        ).fetchone()
        return str(row[0]) if row else ""
    finally:
        con.close()


def session_needs_compaction(
    session_id: str,
    *,
    max_messages: int,
    max_body_chars: int,
    message_count_fn: Callable[[str], int],
    body_chars_fn: Callable[[str], int],
) -> tuple[bool, dict[str, int]]:
    if not session_id:
        return False, {"message_count": 0, "body_chars": 0}
    message_count = message_count_fn(session_id)
    body_chars = body_chars_fn(session_id)
    needs = False
    if max_messages > 0 and message_count >= max_messages:
        needs = True
    if max_body_chars > 0 and body_chars >= max_body_chars:
        needs = True
    return needs, {"message_count": message_count, "body_chars": body_chars}


def session_summary_prompt(group_id: int, *, summaries: str, recent: str, max_chars: int) -> str:
    text = f"""这是 QQ 群 {group_id} 的桥接会话自动压缩摘要。旧 Hermes 对话会话已因上下文过长重置；后续回复只需要参考下面这些本地缓存，不要假装看过更完整历史。

群聊近况摘要：
{summaries}

最近群聊上下文：
{recent}"""
    return text[:max_chars]


def delete_session_cmd(hermes_bin: str, session_id: str) -> list[str]:
    return [hermes_bin, "sessions", "delete", "--yes", session_id]


def session_delete_log_event(
    *,
    session_id: str,
    reason: str,
    returncode: int,
    stdout: str,
    stderr: str,
) -> dict[str, object]:
    return {
        "type": "hermes_session_deleted" if returncode == 0 else "hermes_session_delete_error",
        "session_id": session_id,
        "reason": reason,
        "returncode": returncode,
        "stdout": (stdout or "")[-500:],
        "stderr": (stderr or "")[-500:],
    }
