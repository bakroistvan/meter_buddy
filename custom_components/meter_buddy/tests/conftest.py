"""Pytest path bootstrap for Meter Buddy HA component tests."""

from __future__ import annotations

import sys
from pathlib import Path

# Repo root so `custom_components.meter_buddy` imports resolve.
_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
