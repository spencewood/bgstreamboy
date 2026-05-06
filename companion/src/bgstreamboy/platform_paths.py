"""Cross-platform discovery of Hearthstone's log paths.

Hearthstone runs on macOS and Windows (and on Linux via Wine, with the
Windows install layout). Each puts its session logs and ``log.config`` in
a different place. We probe a list of candidates per platform and use the
first that exists; falling back to the canonical location otherwise.

Public API:

  - ``discover_logs_dir()``: directory containing per-session
    ``Hearthstone_<ts>/Power.log`` subdirs.
  - ``discover_config_path()``: full path to ``log.config``.
  - ``default_source()``: which streaming backend to use by default
    ("console" on macOS, "file" elsewhere).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _mac_logs_candidates() -> list[Path]:
    return [Path("/Applications/Hearthstone/Logs")]


def _windows_logs_candidates() -> list[Path]:
    candidates: list[Path] = []
    for env in ("PROGRAMFILES(X86)", "PROGRAMFILES", "ProgramW6432"):
        base = os.environ.get(env)
        if base:
            candidates.append(Path(base) / "Hearthstone" / "Logs")
    # Common literal fallback.
    candidates.append(Path("C:/Program Files (x86)/Hearthstone/Logs"))
    return candidates


def _linux_logs_candidates() -> list[Path]:
    home = Path.home()
    return [
        home / ".wine/drive_c/Program Files (x86)/Hearthstone/Logs",
        home / ".local/share/Hearthstone/Logs",  # speculative future native
    ]


def _logs_candidates() -> list[Path]:
    if sys.platform == "darwin":
        return _mac_logs_candidates()
    if sys.platform == "win32":
        return _windows_logs_candidates()
    return _linux_logs_candidates()


def _mac_config_candidates() -> list[Path]:
    return [Path.home() / "Library/Preferences/Blizzard/Hearthstone/log.config"]


def _windows_config_candidates() -> list[Path]:
    candidates: list[Path] = []
    for env in ("LOCALAPPDATA", "APPDATA"):
        base = os.environ.get(env)
        if base:
            candidates.append(Path(base) / "Blizzard" / "Hearthstone" / "log.config")
    return candidates


def _linux_config_candidates() -> list[Path]:
    home = Path.home()
    user = os.environ.get("USER", "user")
    return [
        home / f".wine/drive_c/users/{user}/AppData/Local/Blizzard/Hearthstone/log.config",
        home / ".config/Blizzard/Hearthstone/log.config",
    ]


def _config_candidates() -> list[Path]:
    if sys.platform == "darwin":
        return _mac_config_candidates()
    if sys.platform == "win32":
        return _windows_config_candidates()
    return _linux_config_candidates()


def discover_logs_dir() -> Path:
    """Return the Hearthstone Logs directory, picking the first candidate
    that exists; falls back to the canonical-for-platform location if none
    are present yet (so installers can pre-create it)."""
    candidates = _logs_candidates()
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


def discover_config_path() -> Path:
    """Return the path where Hearthstone reads its ``log.config``."""
    candidates = _config_candidates()
    for c in candidates:
        if c.parent.exists():
            return c
    return candidates[0]


def default_source() -> str:
    """Default streaming backend.

    macOS has the unified-log `log stream` plumbing, so we prefer console.
    Windows / Linux fall back to file-tailing with rotation; the rotator
    handles Hearthstone's 10 MB cap as best it can.
    """
    if sys.platform == "darwin":
        return "console"
    return "file"
