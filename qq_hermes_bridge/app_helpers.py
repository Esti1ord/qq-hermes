"""Small FastAPI response helpers for the QQ/Hermes bridge."""
from __future__ import annotations

import hmac
from typing import Any, Mapping


def request_token(headers: Mapping[str, str]) -> str:
    bridge_token = str(headers.get("x-bridge-token") or headers.get("X-Bridge-Token") or "").strip()
    if bridge_token:
        return bridge_token
    authorization = str(headers.get("authorization") or headers.get("Authorization") or "").strip()
    prefix = "Bearer "
    if authorization.lower().startswith(prefix.lower()):
        return authorization[len(prefix):].strip()
    return ""


def request_is_authorized(headers: Mapping[str, str], configured_token: str) -> bool:
    token = str(configured_token or "").strip()
    if not token:
        return True
    supplied = request_token(headers)
    return bool(supplied) and hmac.compare_digest(supplied, token)


def health_response(
    *,
    target_group_id: int,
    allowed_group_ids: set[int],
    bot_qq: str,
    onebot_http_url: str,
    detailed: bool = False,
) -> dict[str, Any]:
    if not detailed:
        return {"ok": True}
    return {
        "ok": True,
        "target_group_id": target_group_id,
        "allowed_group_count": len(allowed_group_ids),
        "bot_qq_configured": bool(bot_qq),
        "onebot_http_configured": bool(onebot_http_url),
    }
