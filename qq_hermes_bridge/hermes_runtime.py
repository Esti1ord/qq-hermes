"""Hermes CLI/session helpers for the QQ bridge."""
from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Callable

import httpx

from . import openai_compat


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


OPENAI_COMPATIBLE_TEXT_PROVIDER_ALIASES = {
    "model",
    "openai",
    "openai_compatible",
    "openai-gpt",
    "custom",
    "axonhub",
    "siliconflow",
    "silicon-flow",
}

HERMES_PROVIDER_ALIASES = {
    "官方": "deepseek",
}


def normalize_provider_for_hermes(provider: str | None) -> str:
    clean = str(provider or "").strip()
    return HERMES_PROVIDER_ALIASES.get(clean, clean)


def provider_supports_direct_http(provider: str | None) -> bool:
    return str(provider or "").strip().lower() in OPENAI_COMPATIBLE_TEXT_PROVIDER_ALIASES


def normalize_chat_completions_url(base_url: str) -> str:
    return openai_compat.normalize_chat_completions_url(base_url)


def max_tokens_for_text_response(max_reply_chars: int = 0) -> int:
    try:
        chars = int(max_reply_chars)
    except (TypeError, ValueError):
        chars = 0
    if chars <= 0:
        return 1024
    return max(64, min(4096, int(chars * 0.75) + 128))


def build_openai_compatible_chat_request(*, model: str, prompt: str, max_reply_chars: int = 0) -> dict[str, Any]:
    return {
        "model": str(model or "").strip(),
        "messages": [{"role": "user", "content": subprocess_safe_text(prompt)}],
        "max_tokens": max_tokens_for_text_response(max_reply_chars),
    }


def extract_openai_compatible_text(payload: Any) -> str:
    return openai_compat.extract_chat_text(payload)


def run_openai_compatible_chat_completion(
    prompt: str,
    *,
    base_url: str,
    model: str,
    api_key_env: str,
    timeout: float,
    max_reply_chars: int = 0,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    url = normalize_chat_completions_url(base_url)
    if not url:
        return {"ok": False, "text": "", "reason": "missing_base_url"}
    if not str(model or "").strip():
        return {"ok": False, "text": "", "reason": "missing_model"}
    clean_api_key_env = str(api_key_env or "").strip()
    if not clean_api_key_env:
        return {"ok": False, "text": "", "reason": "missing_api_key_env"}
    api_key = os.getenv(clean_api_key_env, "").strip()
    if not api_key:
        return {"ok": False, "text": "", "reason": "missing_api_key"}

    body = build_openai_compatible_chat_request(model=model, prompt=prompt, max_reply_chars=max_reply_chars)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    try:
        with httpx.Client(timeout=timeout, trust_env=False, transport=transport) as client:
            response = client.post(url, headers=headers, json=body)
    except httpx.TimeoutException:
        return {"ok": False, "text": "", "reason": "timeout"}
    except httpx.HTTPError:
        return {"ok": False, "text": "", "reason": "http_error"}
    except Exception as exc:
        return {"ok": False, "text": "", "reason": type(exc).__name__}

    if response.status_code < 200 or response.status_code >= 300:
        return {"ok": False, "text": "", "reason": "http_status", "status_code": response.status_code}
    try:
        payload = response.json()
    except ValueError:
        return {"ok": False, "text": "", "reason": "invalid_json"}
    text = extract_openai_compatible_text(payload)
    return {"ok": bool(text), "text": text, "reason": "" if text else "malformed_response"}


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
    selected_provider = normalize_provider_for_hermes(hermes_provider if provider is None else provider)
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


_XML_TOOL_CALL_TAGS = (
    "function_calls",
    "antml:function_calls",
    "invoke",
    "antml:invoke",
    "parameter",
    "antml:parameter",
)


def strip_tool_call_xml(output: str) -> str:
    """Remove XML tool-call markup that may leak from Hermes raw output."""
    clean = output
    # Remove matched pairs first (most specific)
    for tag in _XML_TOOL_CALL_TAGS:
        pattern = re.compile(rf"<{re.escape(tag)}[^>]*>.*?</{re.escape(tag)}>", re.DOTALL | re.IGNORECASE)
        clean = pattern.sub("", clean)
    # Then remove any remaining standalone tags (opening or closing)
    for tag in _XML_TOOL_CALL_TAGS:
        pattern = re.compile(rf"</?{re.escape(tag)}[^>]*>", re.IGNORECASE)
        clean = pattern.sub("", clean)
    return clean.strip()


def strip_session_footer(output: str) -> str:
    clean = strip_cli_warning_lines(output)
    clean = strip_tool_call_xml(clean)
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
