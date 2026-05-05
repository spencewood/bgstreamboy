"""Manage Hearthstone's log.config file.

Hearthstone reads ~/Library/Preferences/Blizzard/Hearthstone/log.config on
startup and only writes the log channels listed there. Without this file,
Power.log is empty and the companion has nothing to read. After installing
or modifying the file, Hearthstone must be restarted for it to take effect.
"""

from pathlib import Path

CONFIG_DIR = Path.home() / "Library/Preferences/Blizzard/Hearthstone"
CONFIG_PATH = CONFIG_DIR / "log.config"

REQUIRED_CHANNELS = ("Power",)

CANONICAL_CONFIG = """\
[Power]
LogLevel=1
FilePrinting=true
ConsolePrinting=false
ScreenPrinting=false

[LoadingScreen]
LogLevel=1
FilePrinting=true
ConsolePrinting=false
ScreenPrinting=false
"""


def is_installed() -> bool:
    if not CONFIG_PATH.exists():
        return False
    text = CONFIG_PATH.read_text()
    return all(f"[{channel}]" in text for channel in REQUIRED_CHANNELS)


def install() -> Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(CANONICAL_CONFIG)
    return CONFIG_PATH
