"""Unit tests for sparse generation and upload batch chunking."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from tools.ha_catchup.generate import chunk_upload_batches, generate_sparse_readings


def test_chunking_300_readings_three_batches():
    base = datetime(2026, 7, 1, tzinfo=timezone.utc)
    readings = [
        {
            "timestamp": (base + timedelta(minutes=i + 1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "period_start": (base + timedelta(minutes=i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "pulses": 10,
            "battery_v": 3.775,
            "battery_pct_est": 50,
        }
        for i in range(300)
    ]

    batches = chunk_upload_batches(readings, session_id="sess-fixed")

    assert len(batches) == 3
    assert [len(b["readings"]) for b in batches] == [128, 128, 44]
    assert [b["last_batch"] for b in batches] == [False, False, True]
    assert {b["upload_session_id"] for b in batches} == {"sess-fixed"}
    assert "battery_v" in batches[0] and "battery_pct_est" in batches[0]
    assert "battery_v" not in batches[1] and "battery_pct_est" not in batches[1]
    assert "battery_v" not in batches[2] and "battery_pct_est" not in batches[2]
    assert all(b["upload_trigger"] == "button" for b in batches)


def test_sparsity_omits_zero_pulse_minutes():
    start = datetime(2026, 7, 1, 0, 0, tzinfo=timezone.utc)
    end = start + timedelta(minutes=100)

    readings = generate_sparse_readings(
        start,
        end,
        pulse_probability=0.3,
        pulses_when_active=10,
        seed=42,
    )

    assert 0 < len(readings) < 100
    assert all(r["pulses"] > 0 for r in readings)
    assert all("timestamp" in r and "period_start" in r for r in readings)


def test_empty_readings_single_heartbeat_last_batch():
    batches = chunk_upload_batches([], session_id="hb-1")

    assert len(batches) == 1
    body = batches[0]
    assert body["readings"] == []
    assert body["last_batch"] is True
    assert body["upload_session_id"] == "hb-1"
    assert body["battery_v"] == 3.775
    assert body["battery_pct_est"] == 50
