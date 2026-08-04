#!/usr/bin/env python3
"""Replace the local Meter Buddy SQLite DB with a copy from a remote backend.

Deletes the DB on localhost, downloads /db from the remote host, then uploads
it to localhost. Both endpoints require HTTP Basic Auth.

Auth defaults come from backend/.env (METER_BUDDY_AUTH_USER / METER_BUDDY_AUTH_PASSWORD).
"""

from __future__ import annotations

import argparse
import base64
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


DEFAULT_LOCAL = "http://127.0.0.1:8000"
DEFAULT_REMOTE = "http://192.168.40.222:8000"
BACKEND_ENV = Path(__file__).resolve().parent.parent / "backend" / ".env"


def load_env_file(path: Path) -> None:
    """Load KEY=VALUE pairs into os.environ without overwriting existing vars."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def auth_header(user: str, password: str) -> str:
    token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def request(
    method: str,
    url: str,
    *,
    authorization: str,
    data: bytes | None = None,
    content_type: str | None = None,
) -> bytes:
    headers: dict[str, str] = {"Authorization": authorization}
    if content_type is not None:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read()
            print(f"{method} {url} -> {resp.status} ({len(body)} bytes)")
            return body
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", errors="replace")
        raise SystemExit(f"{method} {url} failed: HTTP {err.code}\n{detail}") from err
    except urllib.error.URLError as err:
        raise SystemExit(f"{method} {url} failed: {err.reason}") from err


def main() -> int:
    load_env_file(BACKEND_ENV)

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--local",
        default=DEFAULT_LOCAL,
        help=f"Local backend base URL (default: {DEFAULT_LOCAL})",
    )
    parser.add_argument(
        "--remote",
        default=DEFAULT_REMOTE,
        help=f"Remote backend base URL (default: {DEFAULT_REMOTE})",
    )
    parser.add_argument(
        "--user",
        default=os.getenv("METER_BUDDY_AUTH_USER", "meter-buddy"),
        help="Basic Auth username (backend/.env or METER_BUDDY_AUTH_USER)",
    )
    parser.add_argument(
        "--password",
        default=os.getenv("METER_BUDDY_AUTH_PASSWORD"),
        help="Basic Auth password (backend/.env or METER_BUDDY_AUTH_PASSWORD)",
    )
    args = parser.parse_args()
    if not args.password:
        raise SystemExit(
            "Pass --password, set METER_BUDDY_AUTH_PASSWORD, or put it in backend/.env"
        )

    authorization = auth_header(args.user, args.password)
    local = args.local.rstrip("/")
    remote = args.remote.rstrip("/")

    print(f"1/3 Deleting DB on {local} ...")
    request("DELETE", f"{local}/db", authorization=authorization)

    print(f"2/3 Downloading DB from {remote} ...")
    db_bytes = request("GET", f"{remote}/db", authorization=authorization)
    if not db_bytes:
        raise SystemExit("Remote returned an empty database file")

    print(f"3/3 Uploading DB to {local} ({len(db_bytes)} bytes) ...")
    request(
        "POST",
        f"{local}/db",
        authorization=authorization,
        data=db_bytes,
        content_type="application/x-sqlite3",
    )

    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
