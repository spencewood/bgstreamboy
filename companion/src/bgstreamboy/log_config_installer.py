"""Manage Hearthstone's log.config file.

Hearthstone reads its ``log.config`` on startup and only writes the log
channels listed there. Without this file, Power.log is empty and the
companion has nothing to read. After installing or modifying the file,
Hearthstone must be restarted for it to take effect.

Path is platform-dependent — see ``platform_paths.discover_config_path``.
"""

from pathlib import Path

from .platform_paths import discover_config_path

CONFIG_PATH: Path = discover_config_path()
CONFIG_DIR: Path = CONFIG_PATH.parent

REQUIRED_CHANNELS = ("Power",)

# Both `FilePrinting` and `ConsolePrinting` are enabled. ConsolePrinting
# pipes events to stdout (captured by macOS's unified log, no size cap),
# which is the durable channel — Hearthstone's per-session 10 MB Power.log
# cap means file tailing alone goes silent on long sessions. The file write
# is kept enabled so existing tools keep working and as a backup if the
# console pipe is unavailable.
CANONICAL_CONFIG = """\
[Power]
LogLevel=1
FilePrinting=true
ConsolePrinting=true
ScreenPrinting=false

[LoadingScreen]
LogLevel=1
FilePrinting=true
ConsolePrinting=true
ScreenPrinting=false
"""


def is_installed() -> bool:
    if not CONFIG_PATH.exists():
        return False
    text = CONFIG_PATH.read_text()
    if not all(f"[{channel}]" in text for channel in REQUIRED_CHANNELS):
        return False
    # We require ConsolePrinting=true so console-streaming works around the
    # 10 MB file cap. An older config without this needs to be upgraded.
    return "ConsolePrinting=true" in text


def install() -> Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(CANONICAL_CONFIG)
    return CONFIG_PATH
