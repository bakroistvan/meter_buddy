#!/usr/bin/env python3
"""Download ISRG Root X1/X2 and regenerate include/certs/isrg_roots.h."""

from __future__ import annotations

import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "include" / "certs" / "isrg_roots.h"

SOURCES = [
    ("ISRG Root X1", "https://letsencrypt.org/certs/isrgrootx1.pem"),
    ("ISRG Root X2", "https://letsencrypt.org/certs/isrg-root-x2.pem"),
]


def main() -> int:
    parts: list[str] = []
    for name, url in SOURCES:
        print(f"Fetching {name}: {url}")
        with urllib.request.urlopen(url, timeout=30) as resp:
            pem = resp.read().decode("ascii").strip() + "\n"
        if "BEGIN CERTIFICATE" not in pem:
            raise SystemExit(f"Unexpected response for {name}")
        parts.append(pem)

    body = "".join(parts)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        "#pragma once\n"
        "\n"
        "// Vendored Let's Encrypt ISRG Root X1 + X2 (public CAs).\n"
        "// Refresh with: python script/refresh_isrg_roots.py\n"
        "// Source: https://letsencrypt.org/certificates/\n"
        "\n"
        "constexpr const char *IsrgRootCerts = R\"EOF(\n"
        f"{body}"
        ")EOF\";\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
