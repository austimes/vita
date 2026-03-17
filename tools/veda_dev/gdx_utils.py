"""Shared GDX helper utilities for veda-dev result extraction tools."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def find_gdxdump() -> str | None:
    """Find gdxdump executable."""
    default_path = "/Library/Frameworks/GAMS.framework/Resources/gdxdump"
    if os.path.exists(default_path):
        return default_path

    env_path = os.environ.get("GDXDUMP")
    if env_path and os.path.exists(env_path):
        return env_path

    return shutil.which("gdxdump")


def dump_symbol_csv(gdx_path: Path, symbol: str, gdxdump: str) -> str | None:
    """Dump a symbol from GDX to CSV format."""
    cmd = [gdxdump, str(gdx_path), f"Symb={symbol}", "Format=csv", "EpsOut=0"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if proc.returncode == 0:
            return proc.stdout
        return None
    except Exception:  # noqa: BLE001 — gdxdump may be missing; return None
        return None
