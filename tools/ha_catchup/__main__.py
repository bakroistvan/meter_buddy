"""CLI: print JSON upload batches to stdout."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from .generate import chunk_upload_batches, generate_sparse_readings


def _parse_utc(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate sparse Meter Buddy upload batches (JSON to stdout).",
    )
    parser.add_argument("--start", required=True, help="UTC start ISO-8601")
    parser.add_argument("--end", required=True, help="UTC end ISO-8601")
    parser.add_argument("--impulses-per-kwh", type=int, default=1000)
    parser.add_argument("--pulse-probability", type=float, default=0.3)
    parser.add_argument("--pulses-when-active", type=int, default=10)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--device-id", default="meter-buddy-001")
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--max-records", type=int, default=128)
    args = parser.parse_args(argv)

    readings = generate_sparse_readings(
        _parse_utc(args.start),
        _parse_utc(args.end),
        impulses_per_kwh=args.impulses_per_kwh,
        pulse_probability=args.pulse_probability,
        pulses_when_active=args.pulses_when_active,
        seed=args.seed,
    )
    batches = chunk_upload_batches(
        readings,
        device_id=args.device_id,
        impulses_per_kwh=args.impulses_per_kwh,
        session_id=args.session_id,
        max_records=args.max_records,
    )
    json.dump(batches, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
