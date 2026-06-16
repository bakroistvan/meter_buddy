#!/usr/bin/env python3
"""Small Windows-friendly PlatformIO task runner for Meter Buddy."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import venv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VENV_DIR = ROOT / ".venv"
CORE_DIR = ROOT / ".platformio-core"
ENV_NAME = "seeed_xiao_esp32c3"


def venv_python() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def run(command: list[str], *, check: bool = True) -> int:
    env = os.environ.copy()
    env["PLATFORMIO_CORE_DIR"] = str(CORE_DIR)
    print("+ " + " ".join(command))
    completed = subprocess.run(command, cwd=ROOT, env=env, check=check)
    return completed.returncode


def ensure_platformio() -> Path:
    py = venv_python()
    if not py.exists():
        print(f"Creating virtual environment: {VENV_DIR}")
        venv.create(VENV_DIR, with_pip=True)

    probe = subprocess.run(
        [str(py), "-m", "platformio", "--version"],
        cwd=ROOT,
        env={**os.environ, "PLATFORMIO_CORE_DIR": str(CORE_DIR)},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if probe.returncode != 0:
        run([str(py), "-m", "pip", "install", "platformio"])

    return py


def platformio(args: list[str]) -> int:
    py = ensure_platformio()
    return run([str(py), "-m", "platformio", *args])


def cmd_build(_: argparse.Namespace) -> int:
    return platformio(["run", "-e", ENV_NAME])


def cmd_flash(args: argparse.Namespace) -> int:
    pio_args = ["run", "-e", ENV_NAME, "-t", "upload"]
    if args.port:
        pio_args.extend(["--upload-port", args.port])
    return platformio(pio_args)


def cmd_upload(args: argparse.Namespace) -> int:
    return cmd_flash(args)


def cmd_monitor(args: argparse.Namespace) -> int:
    pio_args = ["device", "monitor", "-e", ENV_NAME]
    if args.port:
        pio_args.extend(["--port", args.port])
    if args.baud:
        pio_args.extend(["--baud", str(args.baud)])
    return platformio(pio_args)


def cmd_flash_monitor(args: argparse.Namespace) -> int:
    result = cmd_flash(args)
    if result != 0:
        return result
    return cmd_monitor(args)


def cmd_clean(_: argparse.Namespace) -> int:
    return platformio(["run", "-e", ENV_NAME, "-t", "clean"])


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Compile, flash, and monitor the Meter Buddy ESP32-C3 firmware.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", aliases=["compile"], help="Compile firmware.")
    build.set_defaults(func=cmd_build)

    flash = sub.add_parser("flash", help="Build and flash firmware to the board.")
    flash.add_argument("--port", help="Serial port, for example COM5.")
    flash.set_defaults(func=cmd_flash)

    upload = sub.add_parser("upload", help="Alias for flash.")
    upload.add_argument("--port", help="Serial port, for example COM5.")
    upload.set_defaults(func=cmd_upload)

    monitor = sub.add_parser("monitor", help="Open the serial monitor.")
    monitor.add_argument("--port", help="Serial port, for example COM5.")
    monitor.add_argument("--baud", type=int, default=115200, help="Serial baud rate.")
    monitor.set_defaults(func=cmd_monitor)

    fm = sub.add_parser("flash-monitor", help="Flash firmware, then open serial monitor.")
    fm.add_argument("--port", help="Serial port, for example COM5.")
    fm.add_argument("--baud", type=int, default=115200, help="Serial baud rate.")
    fm.set_defaults(func=cmd_flash_monitor)

    clean = sub.add_parser("clean", help="Clean PlatformIO build output.")
    clean.set_defaults(func=cmd_clean)

    return p


def main() -> int:
    args = parser().parse_args()
    try:
        return args.func(args)
    except subprocess.CalledProcessError as exc:
        return exc.returncode


if __name__ == "__main__":
    raise SystemExit(main())

