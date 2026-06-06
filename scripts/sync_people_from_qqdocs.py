#!/usr/bin/env python3
"""Sync QQ Docs markdown people document to local people.md when changed.

Reads the currently logged-in Firefox docs.qq.com cookies from the user's snap
Firefox profile, fetches the Tencent Docs markdown API, and updates a configured
QQ group people.md only when the remote content hash changes.

Designed for cron/no_agent usage: prints a short message only when it synced
or when an error occurs; stays silent when no update is needed.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))
from qq_hermes_bridge import config_utils  # noqa: E402

config_utils.load_dotenv(BASE_DIR / ".env")

DEFAULT_DOC_URL = "https://docs.qq.com/markdown/DV3ZkWmV3bFRidnhj?"
DEFAULT_TARGET = BASE_DIR / "groups" / "975805598" / "people.md"
API_URL = "https://docs.qq.com/api/markdown/read/data"


def file_id_from_doc_url(doc_url: str) -> str:
    match = re.search(r"/markdown/([^/?#]+)", doc_url or "")
    if not match:
        raise ValueError("QQ Docs markdown URL must contain /markdown/<doc_id>")
    token = match.group(1)
    encoded = token[1:] if token.startswith("D") else token
    padded = encoded + "=" * (-len(encoded) % 4)
    decoded = base64.b64decode(padded).decode("utf-8")
    if not decoded:
        raise ValueError("QQ Docs markdown URL has an empty decoded file id")
    return f"300000000${decoded}"


DOC_URL = os.getenv("QQ_DOCS_PEOPLE_DOC_URL", DEFAULT_DOC_URL).strip() or DEFAULT_DOC_URL
FILE_ID = os.getenv("QQ_DOCS_PEOPLE_FILE_ID", "").strip() or file_id_from_doc_url(DOC_URL)
FIREFOX_COOKIES = Path(os.getenv("QQ_DOCS_FIREFOX_COOKIES", str(Path.home() / "snap/firefox/common/.mozilla/firefox/oc6jt8qq.default/cookies.sqlite")))
TARGET = Path(os.getenv("QQ_DOCS_PEOPLE_TARGET", str(DEFAULT_TARGET)))
STATE = Path(os.getenv("QQ_DOCS_PEOPLE_STATE", str(TARGET.with_name(".people-doc-sync-state.json"))))
BACKUP_DIR = Path(os.getenv("QQ_DOCS_PEOPLE_BACKUP_DIR", str(TARGET.parent / "backups")))


def fail(msg: str, code: int = 1) -> None:
    print(f"people.md 自动同步失败：{msg}")
    raise SystemExit(code)


def load_cookie_header() -> str:
    if not FIREFOX_COOKIES.exists():
        fail(f"找不到 Firefox cookie 数据库：{FIREFOX_COOKIES}")
    try:
        with tempfile.TemporaryDirectory(prefix="qq-docs-people-sync-") as tmpdir:
            tmp_cookie = Path(tmpdir) / "cookies.sqlite"
            shutil.copy2(FIREFOX_COOKIES, tmp_cookie)
            os.chmod(tmp_cookie, 0o600)
            with sqlite3.connect(tmp_cookie) as con:
                rows = con.execute(
                    """
                    select host, name, value
                    from moz_cookies
                    where host like '%docs.qq.com%'
                       or host = '.qq.com'
                       or host like '%.qq.com'
                    """
                ).fetchall()
    except Exception as exc:  # noqa: BLE001 - script should report concise cron error
        fail(f"读取 Firefox cookie 失败：{exc}")
    if not rows:
        fail("Firefox 中没有 docs.qq.com/qq.com 登录 cookie，请先用 Firefox 打开腾讯文档并登录")
    return "; ".join(f"{name}={value}" for _host, name, value in rows)


def fetch_markdown() -> tuple[str, dict]:
    cookie = load_cookie_header()
    body = json.dumps({"file_id": FILE_ID}).encode("utf-8")
    req = urllib.request.Request(
        API_URL,
        data=body,
        method="POST",
        headers={
            "User-Agent": "Mozilla/5.0",
            "Cookie": cookie,
            "Referer": DOC_URL,
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        fail(f"请求腾讯文档失败：{exc}")
    if payload.get("retcode") != 0:
        fail(f"腾讯文档返回错误：{payload}")
    result = payload.get("result") or {}
    md = result.get("mark_down")
    if not isinstance(md, str) or not md.strip():
        fail("腾讯文档返回内容为空")
    return md, result.get("meta") or {}


def normalize(md: str) -> str:
    md = md.replace("\r\n", "\n").replace("\r", "\n").strip() + "\n"
    # bridge 优先识别“标签”，腾讯文档里如果写“关键词”则自动兼容。
    md = re.sub(r"(?m)^- 关键词[：:]", "- 标签：", md)
    return md


def load_state() -> dict:
    if not STATE.exists():
        return {}
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state: dict) -> None:
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    md, meta = fetch_markdown()
    md = normalize(md)
    digest = hashlib.sha256(md.encode("utf-8")).hexdigest()
    old_state = load_state()
    current = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
    current_digest = hashlib.sha256(current.encode("utf-8")).hexdigest() if current else ""

    if old_state.get("sha256") == digest and current_digest == digest:
        return

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup = None
    if TARGET.exists() and current_digest != digest:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        backup = BACKUP_DIR / f"people.md.{stamp}.autosync.bak"
        shutil.copy2(TARGET, backup)

    TARGET.write_text(md, encoding="utf-8")
    sections = len(re.findall(r"(?m)^##\s+", md))
    save_state(
        {
            "sha256": digest,
            "synced_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "source_url": DOC_URL,
            "file_id": FILE_ID,
            "meta": meta,
            "target": str(TARGET),
            "chars": len(md),
            "sections": sections,
        }
    )
    print(
        "people.md 已从腾讯文档同步："
        f"sections={sections} chars={len(md)} version={meta.get('version')} "
        f"modify_time={meta.get('modify_time')} backup={backup or 'none'}"
    )


if __name__ == "__main__":
    main()
