# PlatformIO pre-script: inject FIRMWARE_VERSION from git describe / tag.
Import("env")  # type: ignore[name-defined]  # noqa: F821 — PlatformIO

import subprocess


def _resolve_version() -> str:
    try:
        out = subprocess.check_output(
            ["git", "describe", "--tags", "--always"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        if out:
            return out
    except (OSError, subprocess.CalledProcessError):
        pass
    return "0.0.0-unknown"


version = _resolve_version()
# Escape for -D string macro: FIRMWARE_VERSION="v0.4.0"
escaped = version.replace("\\", "\\\\").replace('"', '\\"')
env.Append(CPPDEFINES=[("FIRMWARE_VERSION", f'\\"{escaped}\\"')])  # type: ignore[name-defined]  # noqa: F821
print(f"pio_firmware_version: FIRMWARE_VERSION={version}")
