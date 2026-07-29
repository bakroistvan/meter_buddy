#!/usr/bin/env python3
"""Decode Meter Buddy LittleFS hexdumps captured from the diagnostics REPL."""

from __future__ import annotations

import argparse
import re
import struct
from datetime import datetime, timezone
from pathlib import Path


FILE_HEADER = re.compile(r"^(?P<path>/\S+) \((?P<size>\d+) bytes\):$")
HEX_LINE = re.compile(r"^\s*[0-9a-fA-F]{8}\s+(?P<hex>(?:[0-9a-fA-F]{2}\s+){1,16})\|")
RECORD = struct.Struct("<IIHHHH")


def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for value in data:
        crc ^= value
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def utc(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def parse_files(text: str) -> dict[str, tuple[int, bytes]]:
    result: dict[str, tuple[int, bytes]] = {}
    current_path: str | None = None
    expected_size = 0
    data = bytearray()

    for line in text.splitlines():
        header = FILE_HEADER.match(line.strip())
        if header:
            if current_path is not None:
                result[current_path] = (expected_size, bytes(data))
            current_path = header.group("path")
            expected_size = int(header.group("size"))
            data = bytearray()
            continue

        if current_path is not None:
            hex_line = HEX_LINE.match(line)
            if hex_line:
                data.extend(int(token, 16) for token in hex_line.group("hex").split())

    if current_path is not None:
        result[current_path] = (expected_size, bytes(data))
    return result


def decode_records(data: bytes) -> None:
    if len(data) % RECORD.size:
        print(f"warning: records data is {len(data)} bytes, not a multiple of {RECORD.size}")

    count = len(data) // RECORD.size
    print(f"records: {count} complete record(s), {len(data)} decoded bytes")
    print("seq  period_start              pulses  battery  flags  crc")
    print("---  -----------------------  ------  -------  -----  ---")

    for index in range(count):
        raw = data[index * RECORD.size : (index + 1) * RECORD.size]
        sequence, period_start, pulses, battery_mv, flags, stored_crc = RECORD.unpack(raw)
        calculated_crc = crc16(raw[:-2])
        crc_state = "OK" if stored_crc == calculated_crc else f"BAD ({calculated_crc:04x})"
        print(
            f"{sequence:3d}  {utc(period_start):23s}  "
            f"{pulses:6d}  {battery_mv:7d}  {flags:5d}  {crc_state}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path, default=Path(__file__).with_name("input.txt"))
    args = parser.parse_args()

    files = parse_files(args.input.read_text(encoding="utf-8"))
    if not files:
        parser.error("no hexdump file sections found")

    for path, (expected_size, data) in files.items():
        print(f"{path}: reported {expected_size} bytes, decoded {len(data)} bytes")
        if expected_size != len(data):
            print("warning: reported size does not match decoded byte count")
        if path == "/records.bin":
            decode_records(data)
        elif path == "/sync.dat" and len(data) >= 4:
            print(f"sync pointer: {int.from_bytes(data[:4], 'little')}")
        else:
            print(f"raw: {data.hex(' ')}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
