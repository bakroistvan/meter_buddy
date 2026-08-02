#!/usr/bin/env python3
"""Compare Meter Buddy reading battery samples to a theoretical LiPo OCV curve.

Pulls per-reading battery_v / battery_pct_est from a remote backend SQLite DB
(or a local .sqlite3), then plots:

  - real data (scatter)
  - polynomial fit through the real points
  - theoretical LiPo resting OCV curve
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


DEFAULT_REMOTE = "http://192.168.40.222:8000"

# Approximate single-cell LiPo resting OCV -> SoC (V, %).
LIPO_OCV_CURVE: list[tuple[float, float]] = [
    (4.20, 100.0),
    (4.15, 95.0),
    (4.11, 90.0),
    (4.08, 85.0),
    (4.02, 80.0),
    (3.98, 75.0),
    (3.95, 70.0),
    (3.91, 65.0),
    (3.87, 60.0),
    (3.85, 55.0),
    (3.84, 50.0),
    (3.82, 45.0),
    (3.80, 40.0),
    (3.79, 35.0),
    (3.77, 30.0),
    (3.75, 25.0),
    (3.73, 20.0),
    (3.71, 15.0),
    (3.69, 10.0),
    (3.61, 5.0),
    (3.30, 0.0),
]

V_EMPTY = 3.30
V_FULL = 4.20


@dataclass(frozen=True)
class ReadingSample:
    timestamp: datetime
    volts: float
    pct_reported: float | None
    dump_id: int | None


def download_db(remote: str, dest: Path) -> Path:
    url = f"{remote.rstrip('/')}/db"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            dest.write_bytes(resp.read())
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", errors="replace")
        raise SystemExit(f"GET {url} failed: HTTP {err.code}\n{detail}") from err
    except urllib.error.URLError as err:
        raise SystemExit(f"GET {url} failed: {err.reason}") from err
    print(f"Downloaded {dest.stat().st_size} bytes from {url}")
    return dest


def parse_timestamp(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def load_reading_samples(db_path: Path) -> list[ReadingSample]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT timestamp, battery_v, battery_pct_est, dump_id
            FROM meter_readings
            WHERE battery_v IS NOT NULL
            ORDER BY timestamp ASC, id ASC
            """
        ).fetchall()
    finally:
        conn.close()

    samples: list[ReadingSample] = []
    for timestamp, volts, pct, dump_id in rows:
        try:
            v = float(volts)
        except (TypeError, ValueError):
            continue
        pct_reported = None if pct is None else float(pct)
        samples.append(
            ReadingSample(
                timestamp=parse_timestamp(str(timestamp)),
                volts=v,
                pct_reported=pct_reported,
                dump_id=None if dump_id is None else int(dump_id),
            )
        )
    return samples


def interpolate_pct(volts: float, curve: list[tuple[float, float]]) -> float:
    if volts >= curve[0][0]:
        return curve[0][1]
    if volts <= curve[-1][0]:
        return curve[-1][1]
    for (v_hi, p_hi), (v_lo, p_lo) in zip(curve, curve[1:]):
        if v_lo <= volts <= v_hi:
            if v_hi == v_lo:
                return p_hi
            t = (volts - v_lo) / (v_hi - v_lo)
            return p_lo + t * (p_hi - p_lo)
    return 0.0


def firmware_linear_pct(volts: np.ndarray | float) -> np.ndarray | float:
    return np.clip((np.asarray(volts) - V_EMPTY) * 100.0 / (V_FULL - V_EMPTY), 0.0, 100.0)


def fit_pct_vs_volts(volts: np.ndarray, pct: np.ndarray, degree: int) -> np.polynomial.Polynomial:
    degree = max(1, min(degree, max(1, len(volts) - 1)))
    coeffs = np.polyfit(volts, pct, degree)
    return np.polynomial.Polynomial(coeffs[::-1])


def plot_curves(
    samples: list[ReadingSample],
    *,
    degree: int,
    out_path: Path,
    show: bool,
) -> None:
    volts = np.array([s.volts for s in samples], dtype=float)
    with_pct = [s for s in samples if s.pct_reported is not None]
    if len(with_pct) < 2:
        raise SystemExit("Need at least 2 readings with battery_pct_est to fit a curve")

    real_v = np.array([s.volts for s in with_pct], dtype=float)
    real_pct = np.array([s.pct_reported for s in with_pct], dtype=float)

    fit = fit_pct_vs_volts(real_v, real_pct, degree)
    v_grid = np.linspace(min(V_EMPTY, real_v.min()), max(V_FULL, real_v.max()), 300)
    theory_pct = np.array([interpolate_pct(v, LIPO_OCV_CURVE) for v in v_grid])
    fit_pct = np.clip(fit(v_grid), 0.0, 100.0)
    linear_pct = firmware_linear_pct(v_grid)

    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5), constrained_layout=True)

    ax = axes[0]
    ax.scatter(real_v, real_pct, s=12, alpha=0.35, color="#0f766e", label=f"readings (n={len(with_pct)})")
    ax.plot(v_grid, theory_pct, color="#b45309", linewidth=2.2, label="firmware / theory LiPo OCV")
    ax.plot(v_grid, fit_pct, color="#1d4ed8", linewidth=2.2, label=f"fit poly deg {fit.degree()}")
    ax.plot(v_grid, linear_pct, color="#6b7280", linewidth=1.4, linestyle="--", label="legacy linear 3.30–4.20")
    ax.set_xlabel("Battery voltage (V)")
    ax.set_ylabel("State of charge (%)")
    ax.set_title("SoC vs voltage")
    ax.set_xlim(v_grid.min() - 0.02, v_grid.max() + 0.02)
    ax.set_ylim(-5, 105)
    ax.grid(True, linestyle="--", alpha=0.45)
    ax.legend(loc="best")

    ax = axes[1]
    times = [s.timestamp for s in with_pct]
    ax.scatter(times, real_v, s=12, alpha=0.35, color="#0f766e", label="reading voltage")
    # Smooth voltage vs time with a low-degree fit in epoch seconds.
    t0 = times[0].timestamp()
    t_sec = np.array([(t.timestamp() - t0) for t in times], dtype=float)
    v_time_fit = fit_pct_vs_volts(t_sec, real_v, min(degree, 3))
    t_grid = np.linspace(t_sec.min(), t_sec.max(), 300)
    t_grid_dt = [datetime.fromtimestamp(t0 + x, tz=timezone.utc) for x in t_grid]
    ax.plot(t_grid_dt, v_time_fit(t_grid), color="#1d4ed8", linewidth=2.2, label=f"V(t) fit deg {v_time_fit.degree()}")
    # Theory voltage for each reading's reported SoC (invert OCV roughly via nearest).
    theory_v_for_pct = []
    for pct in real_pct:
        # Find V on theory curve for this SoC by inverse interpolation.
        theory_v_for_pct.append(invert_curve_pct(pct, LIPO_OCV_CURVE))
    ax.plot(times, theory_v_for_pct, color="#b45309", linewidth=1.6, alpha=0.85, label="theory V at reported %")
    ax.set_xlabel("Reading timestamp (UTC)")
    ax.set_ylabel("Battery voltage (V)")
    ax.set_title("Voltage over time")
    ax.grid(True, linestyle="--", alpha=0.45)
    ax.legend(loc="best")
    fig.autofmt_xdate()

    residual = real_pct - np.array([interpolate_pct(v, LIPO_OCV_CURVE) for v in real_v])
    fit_residual = real_pct - np.clip(fit(real_v), 0.0, 100.0)
    fig.suptitle(
        f"Battery curve check  |  V range {volts.min():.2f}-{volts.max():.2f} V  |  "
        f"mean (real-theory) {residual.mean():+.1f} pt  |  "
        f"RMSE fit {np.sqrt(np.mean(fit_residual**2)):.2f} pt",
        fontsize=11,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=140)
    print(f"Wrote plot: {out_path}")
    if show:
        plt.show()
    else:
        plt.close(fig)


def invert_curve_pct(pct: float, curve: list[tuple[float, float]]) -> float:
    """Map SoC % -> voltage on the theory curve (descending V, descending %)."""
    pts = sorted(((p, v) for v, p in curve), key=lambda x: x[0])
    if pct <= pts[0][0]:
        return pts[0][1]
    if pct >= pts[-1][0]:
        return pts[-1][1]
    for (p_lo, v_lo), (p_hi, v_hi) in zip(pts, pts[1:]):
        if p_lo <= pct <= p_hi:
            if p_hi == p_lo:
                return v_lo
            t = (pct - p_lo) / (p_hi - p_lo)
            return v_lo + t * (v_hi - v_lo)
    return pts[-1][1]


def print_summary(samples: list[ReadingSample]) -> None:
    with_pct = [s for s in samples if s.pct_reported is not None]
    volts = np.array([s.volts for s in samples], dtype=float)
    print(f"Readings with battery_v: {len(samples)}")
    print(f"Readings with battery_pct_est: {len(with_pct)}")
    print(f"Voltage range: {volts.min():.3f} .. {volts.max():.3f} V")
    print(f"Time range: {samples[0].timestamp.isoformat()} .. {samples[-1].timestamp.isoformat()}")
    if with_pct:
        latest = with_pct[-1]
        theory = interpolate_pct(latest.volts, LIPO_OCV_CURVE)
        print(
            f"Latest: {latest.volts:.3f} V, reported {latest.pct_reported:.0f}%, "
            f"theory {theory:.1f}%, delta {latest.pct_reported - theory:+.1f} pt"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--remote",
        default=DEFAULT_REMOTE,
        help=f"Remote backend base URL (default: {DEFAULT_REMOTE})",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Use an existing SQLite DB instead of downloading /db",
    )
    parser.add_argument(
        "--degree",
        type=int,
        default=3,
        help="Polynomial degree for the SoC-vs-V fit (default: 3)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parent / "battery_curve_compare.png",
        help="Output plot path",
    )
    parser.add_argument(
        "--no-show",
        action="store_true",
        help="Only save the plot; do not open an interactive window",
    )
    args = parser.parse_args()

    if args.db is not None:
        db_path = args.db
        if not db_path.exists():
            raise SystemExit(f"DB not found: {db_path}")
    else:
        tmp = Path(tempfile.gettempdir()) / "meter_buddy_curve.sqlite3"
        db_path = download_db(args.remote, tmp)

    samples = load_reading_samples(db_path)
    if not samples:
        raise SystemExit("No meter_readings with battery_v found")

    print_summary(samples)
    plot_curves(samples, degree=args.degree, out_path=args.out, show=not args.no_show)
    return 0


if __name__ == "__main__":
    sys.exit(main())
