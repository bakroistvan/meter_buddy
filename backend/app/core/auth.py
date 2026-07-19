from __future__ import annotations

import os
import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials


security = HTTPBasic()


def expected_username() -> str:
    return os.getenv("METER_BUDDY_AUTH_USER", "meter-buddy")


def expected_password() -> str:
    return os.getenv("METER_BUDDY_AUTH_PASSWORD", "change-me")


def require_basic_auth(
    credentials: Annotated[HTTPBasicCredentials, Depends(security)],
) -> str:
    user_ok = secrets.compare_digest(credentials.username, expected_username())
    password_ok = secrets.compare_digest(credentials.password, expected_password())
    if user_ok and password_ok:
        return credentials.username

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials",
        headers={"WWW-Authenticate": "Basic"},
    )
