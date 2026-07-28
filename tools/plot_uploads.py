#!/usr/bin/env python3
"""Fetch Meter Buddy uploads by dump ID and plot their readings.

Example:
    python tools/plot_uploads.py 1 25 --base-url http://127.0.0.1:8000
    python tools/plot_uploads.py 100 150 --output uploads.png
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class Reading:
    timestamp: datetime
    pulses: int
    dump_id: int
    impulses_per_kwh: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("start_id", type=int, help="First upload ID, inclusive")
    parser.add_argument("end_id", type=int, help="Last upload ID, inclusive")
    parser.add_argument(
        "--base-url",
        default=os.getenv("METER_BUDDY_URL", "http://127.0.0.1:8000"),
        help="Backend URL (default: METER_BUDDY_URL or http://127.0.0.1:8000)",
    )
    parser.add_argument("--username", help="Optional HTTP Basic Auth username")
    parser.add_argument("--password", help="Optional HTTP Basic Auth password")
    parser.add_argument(
        "--output",
        type=Path,
        help="Save the plot to this image file instead of using the default filename",
    )
    parser.add_argument("--show", action="store_true", help="Show the plot interactively")
    parser.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout in seconds")
    return parser.parse_args()


def parse_timestamp(value: str) -> datetime:
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)


def fetch_upload(base_url: str, dump_id: int, username: str | None,
                 password: str | None, timeout: float) -> dict:
    url = f"{base_url.rstrip('/')}/dumps/{dump_id}.json"
    request = Request(url)
    if username is not None:
        credentials = f"{username}:{password or ''}".encode()
        token = base64.b64encode(credentials).decode("ascii")
        request.add_header("Authorization", f"Basic {token}")

    with urlopen(request, timeout=timeout) as response:
        return json.load(response)


def collect_readings(args: argparse.Namespace) -> list[Reading]:
    if args.start_id < 1 or args.end_id < args.start_id:
        raise ValueError("require 1 <= start_id <= end_id")

    readings: list[Reading] = []
    for dump_id in range(args.start_id, args.end_id + 1):
        try:
            upload = fetch_upload(
                args.base_url, dump_id, args.username, args.password, args.timeout
            )
        except HTTPError as exc:
            if exc.code == 404:
                print(f"warning: upload ID {dump_id} was not found", file=sys.stderr)
                continue
            raise RuntimeError(f"upload ID {dump_id}: HTTP {exc.code}") from exc
        except URLError as exc:
            raise RuntimeError(f"upload ID {dump_id}: {exc.reason}") from exc

        impulses_per_kwh = int(upload.get("meter_impulses_per_kwh", 1))
        if impulses_per_kwh <= 0:
            raise RuntimeError(f"upload ID {dump_id}: invalid meter_impulses_per_kwh")
        for item in upload.get("readings", []):
            readings.append(
                Reading(
                    timestamp=parse_timestamp(item["timestamp"]),
                    pulses=int(item["pulses"]),
                    dump_id=dump_id,
                    impulses_per_kwh=impulses_per_kwh,
                )
            )

    readings.sort(key=lambda item: item.timestamp)
    return readings


def plot_readings(readings: list[Reading], output: Path | None, show: bool) -> None:
    if not readings:
        raise RuntimeError("the selected uploads contain no readings")

    try:
        import matplotlib.dates as mdates
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError(
            "matplotlib is required; install it with: python -m pip install matplotlib"
        ) from exc

    timestamps = [item.timestamp for item in readings]
    pulses = [item.pulses for item in readings]
    energy_kwh = [item.pulses / item.impulses_per_kwh for item in readings]
    cumulative_kwh: list[float] = []
    total = 0.0
    for value in energy_kwh:
        total += value
        cumulative_kwh.append(total)

    figure, axes = plt.subplots(2, 1, figsize=(12, 7), sharex=True, constrained_layout=True)
    axes[0].plot(timestamps, pulses, marker=".", linestyle="-", linewidth=0.8)
    axes[0].set_ylabel("Pulses / period")
    axes[0].set_title(f"Meter Buddy readings ({len(readings)} records)")
    axes[0].grid(True, alpha=0.3)

    axes[1].plot(timestamps, cumulative_kwh, color="tab:green", marker=".", linestyle="-", linewidth=0.8)
    axes[1].set_ylabel("Cumulative kWh")
    axes[1].set_xlabel("UTC time")
    axes[1].grid(True, alpha=0.3)
    axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d\n%H:%M", tz=timezone.utc))

    if output is None:
        output = Path(f"meter_uploads_{readings[0].dump_id}_{readings[-1].dump_id}.png")
    figure.savefig(output, dpi=150)
    print(f"saved {output} ({len(readings)} readings, {total:.3f} kWh)")
    if show:
        plt.show()
    plt.close(figure)


def main() -> int:
    args = parse_args()
    try:
        readings = collect_readings(args)
        plot_readings(readings, args.output, args.show)
    except (ValueError, RuntimeError, KeyError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
