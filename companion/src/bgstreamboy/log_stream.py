"""Tail Hearthstone's consolidated `Hearthstone.log`.

When ``log.config`` has ``ConsolePrinting=true`` for the Power channel,
Hearthstone duplicates events into a second file alongside ``Power.log``:

    /Applications/Hearthstone/Logs/Hearthstone_<ts>/Hearthstone.log

Each session writes to its own copy. Format differs slightly from
``Power.log``:

    Power.log     : ``D 19:13:45.864 GameState.DebugPrintPower() - CREATE_GAME``
    Hearthstone.log: ``I 21:04:30.268 [Power] GameState.DebugPrintPower() - CREATE_GAME``

We strip the ``[Power]`` channel tag and feed the line straight into hslog,
which accepts ``I``/``D``/``E``/``W``/``V`` as level prefixes. We filter to
just the Power and LoadingScreen channels — other channels (Net, Decks,
etc.) carry no data we care about.

Why bother with this when Power.log has the same content?

  - Power.log is hard-capped at 10 MB per session. Once Hearthstone hits
    the cap, it stops writing — period — until app restart. Hearthstone.log
    is a different file that *may* roll separately or have a higher cap.
    Whichever way it caps, our `LogRotator` also covers it.
  - When ConsolePrinting is on, Hearthstone.log is the broader source of
    truth — it captures the same events as Power.log plus other channels
    we may want later.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable
from pathlib import Path

from hslog import LogParser
from hslog.packets import Packet
from watchfiles import awatch

from .log_rotator import LogRotator
from .log_tailer import (
    _drain_complete_lines,
    _hook_register_packet,
    find_latest_session_log,
)
from .platform_paths import discover_logs_dir

PacketCallback = Callable[[Packet], None]

# Only the Power channel is parseable by hslog. Other channels (LoadingScreen,
# Net, Decks…) use different formats hslog doesn't understand. We filter
# everything else out before forwarding.
ACCEPTED_CHANNELS = ("Power",)

# Capture: level, timestamp, channel, body.
_CHANNEL_LINE_RE = re.compile(
    r"^([DEWVI])\s+(\d{2}:\d{2}:\d{2}\.\d+)\s+\[(\w+)\]\s+(.+)$"
)


def transform_console_line(line: str) -> str | None:
    """Convert a Hearthstone.log line into something hslog can parse, or
    None if the line isn't a tracked-channel event.

    Hearthstone.log uses an `I` (Info) level prefix; hslog's `TIMESTAMP_RE`
    only accepts `[DWE]`, so we always rewrite the level to `D` regardless
    of what the source had — these are all the same Power-channel events
    that Power.log writes with `D`.
    """
    if not line:
        return None
    rstripped = line.rstrip("\n")
    m = _CHANNEL_LINE_RE.match(rstripped)
    if m is None:
        return None
    _level, ts, channel, body = m.groups()
    if channel not in ACCEPTED_CHANNELS:
        return None
    return f"D {ts} {body}\n"


def find_latest_hearthstone_log(logs_dir: Path) -> Path | None:
    """Return the most recent session's Hearthstone.log, or None.

    Mirrors `find_latest_session_log` but for the consolidated log file.
    """
    if not logs_dir.exists():
        return None
    candidates: list[tuple[float, Path]] = []
    for d in logs_dir.iterdir():
        if d.is_dir() and d.name.startswith("Hearthstone_"):
            log = d / "Hearthstone.log"
            if log.exists():
                candidates.append((d.stat().st_mtime, log))
    if not candidates:
        return None
    candidates.sort()
    return candidates[-1][1]


async def follow_console_async(
    on_packet: PacketCallback,
    logs_dir: Path | None = None,
) -> None:
    """Block forever, parsing the latest Hearthstone.log as it grows.

    Auto-discovers the latest session and switches when a new session
    directory appears. Rotates if the file approaches the 10 MB cap.
    """
    if logs_dir is None:
        logs_dir = discover_logs_dir()

    while True:
        target = find_latest_hearthstone_log(logs_dir)
        if target is None:
            print(f"[bgstreamboy] no Hearthstone.log under {logs_dir}; waiting…", file=sys.stderr)
            logs_dir.mkdir(parents=True, exist_ok=True)
            async for _ in awatch(str(logs_dir), recursive=True, debounce=200):
                if find_latest_hearthstone_log(logs_dir) is not None:
                    break
            continue

        print(f"[bgstreamboy] tailing {target}", file=sys.stderr)
        parser = LogParser()
        _hook_register_packet(parser, on_packet)
        try:
            await _consume_console_session(target, parser, logs_dir)
        except FileNotFoundError:
            continue


async def _consume_console_session(
    log_path: Path, parser: LogParser, logs_dir: Path
) -> None:
    rotator = LogRotator(log_path)
    with log_path.open("r", encoding="utf-8", errors="replace") as f:
        f.seek(0)
        _drain_console_lines(f, parser, rotator)
        last_size = log_path.stat().st_size
        async for _ in awatch(str(logs_dir), recursive=True, debounce=200):
            latest = find_latest_hearthstone_log(logs_dir)
            if latest is not None and latest != log_path:
                print(f"[bgstreamboy] new session detected, switching: {latest}", file=sys.stderr)
                return
            try:
                current_size = log_path.stat().st_size
            except FileNotFoundError:
                return
            if current_size < last_size:
                return  # truncation
            _drain_console_lines(f, parser, rotator)
            last_size = log_path.stat().st_size
            if rotator.maybe_rotate():
                return


def _drain_console_lines(f, parser: LogParser, rotator: LogRotator) -> None:
    """Read newline-terminated lines, applying the channel transform before
    forwarding to hslog. Reuses the rotator's truncation-marker detection
    against the original (untransformed) lines."""
    while True:
        pos = f.tell()
        line = f.readline()
        if not line.endswith("\n"):
            f.seek(pos)
            return
        rotator.observe_line(line)
        transformed = transform_console_line(line)
        if transformed is None:
            continue
        try:
            parser.read_line(transformed)
        except Exception as e:
            print(f"[hslog parse error] {e!r}: {transformed.rstrip()!r}", file=sys.stderr)
