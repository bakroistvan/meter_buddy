from __future__ import annotations

import sys
from pathlib import Path

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))


@pytest.fixture(autouse=True)
def _allow_insecure_auth_for_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("METER_BUDDY_ALLOW_INSECURE_AUTH", "1")
