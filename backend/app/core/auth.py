from __future__ import annotations

import base64
import os
import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, WebSocket, WebSocketException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials


security = HTTPBasic()

_INSECURE_DEFAULT_PASSWORD = "change-me"


def expected_username() -> str:
    return os.getenv("METER_BUDDY_AUTH_USER", "meter-buddy")


def expected_password() -> str:
    return os.getenv("METER_BUDDY_AUTH_PASSWORD", "change-me")


def allow_insecure_auth() -> bool:
    return os.getenv("METER_BUDDY_ALLOW_INSECURE_AUTH", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def validate_auth_config() -> None:
    """Refuse weak/default passwords unless explicitly allowed for local/tests."""
    if allow_insecure_auth():
        return
    password = os.getenv("METER_BUDDY_AUTH_PASSWORD")
    if password is None or password.strip() == "" or password == _INSECURE_DEFAULT_PASSWORD:
        raise RuntimeError(
            "METER_BUDDY_AUTH_PASSWORD must be set to a non-default value. "
            "For local/tests only, set METER_BUDDY_ALLOW_INSECURE_AUTH=1."
        )


def credentials_match(username: str, password: str) -> bool:
    user_ok = secrets.compare_digest(username, expected_username())
    password_ok = secrets.compare_digest(password, expected_password())
    return user_ok and password_ok


def require_basic_auth(
    credentials: Annotated[HTTPBasicCredentials, Depends(security)],
) -> str:
    if credentials_match(credentials.username, credentials.password):
        return credentials.username

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials",
        headers={"WWW-Authenticate": "Basic"},
    )


def _parse_basic_authorization(header: str | None) -> tuple[str, str] | None:
    if header is None or not header.startswith("Basic "):
        return None
    try:
        decoded = base64.b64decode(header[6:]).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None
    if ":" not in decoded:
        return None
    username, password = decoded.split(":", 1)
    return username, password


async def require_websocket_basic_auth(websocket: WebSocket) -> str:
    parsed = _parse_basic_authorization(websocket.headers.get("authorization"))
    if parsed is None or not credentials_match(parsed[0], parsed[1]):
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Invalid authentication credentials",
        )
    return parsed[0]
