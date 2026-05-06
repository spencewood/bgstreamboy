"""Stream Hearthstone Power events from macOS unified log.

When ``log.config`` has ``ConsolePrinting=true`` for the Power channel,
Hearthstone duplicates every Power.log event to stdout. macOS captures
GUI-app stdout into its unified log (`log stream` / Console.app), which has
no per-session file-size cap — unlike Power.log's 10 MB ceiling.

This module spawns ``log stream`` as a subprocess filtered to Hearthstone's
PID, peels off macOS's metadata wrappers, and forwards just the original
``D HH:MM:SS.fffffff GameState.DebugPrintPower()`` lines to the same
``hslog`` parser the file-tailer uses.

Tradeoffs vs file tailing:

  + No cap. Long sessions stay live.
  + No file-rotation choreography needed.
  + Captures events even after Hearthstone hits its file cap and stops
    writing the file.
  - Requires `ConsolePrinting=true` in log.config (one-time install change).
  - Requires Hearthstone be running so we can locate its PID.
  - macOS-specific (Linux/Windows would need different plumbing).
"""

from __future__ import annotations

import asyncio
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from hslog import LogParser
from hslog.packets import Packet

from .log_tailer import _hook_register_packet

PacketCallback = Callable[[Packet], None]


# Match `D HH:MM:SS.fffffff <prefix>.<method>() ...` anywhere on a line.
# macOS unified log prefixes its own timestamp/source columns; we tolerate
# anything before the Hearthstone-format timestamp.
_HS_LINE_RE = re.compile(
    r"(D \d{2}:\d{2}:\d{2}\.\d+ \S+\.[A-Za-z]+\(\) .+)$"
)


def hearthstone_pids() -> list[int]:
    """Return PIDs of any running Hearthstone process(es)."""
    try:
        out = subprocess.run(
            ["pgrep", "-x", "Hearthstone"],
            capture_output=True, text=True, check=False,
        )
        return [int(p) for p in out.stdout.split() if p.strip()]
    except FileNotFoundError:
        return []


def _have_log_command() -> bool:
    return shutil.which("log") is not None


async def follow_console_async(on_packet: PacketCallback) -> None:
    """Block forever, parsing Hearthstone Power events from `log stream`.

    Auto-discovers Hearthstone's PID at start; if Hearthstone isn't running
    yet, waits for it to launch. If `log stream` exits (e.g. Hearthstone
    quits), reconnects when Hearthstone reappears.
    """
    if not _have_log_command():
        raise RuntimeError(
            "`log` CLI not found — console streaming requires macOS. "
            "Falling back to file tailing is recommended on other platforms."
        )

    while True:
        pids = hearthstone_pids()
        if not pids:
            print("[bgstreamboy] waiting for Hearthstone to launch…", file=sys.stderr)
            while not hearthstone_pids():
                await asyncio.sleep(2.0)
            pids = hearthstone_pids()

        pid = pids[0]
        print(f"[bgstreamboy] streaming Hearthstone console (pid={pid})", file=sys.stderr)
        await _stream_one(pid, on_packet)
        # `log stream` exited — Hearthstone probably quit. Loop reattaches.
        print("[bgstreamboy] log stream ended; will reattach when Hearthstone returns", file=sys.stderr)


async def _stream_one(pid: int, on_packet: PacketCallback) -> None:
    parser = LogParser()
    _, flush = _hook_register_packet(parser, on_packet)

    # `--style ndjson` would give structured output but the message body
    # would still be the raw log line. `--style compact` is simpler — we
    # just regex the `D HH:MM:SS` Hearthstone format off the end.
    cmd = [
        "log", "stream",
        "--style", "compact",
        "--predicate", f"processIdentifier == {pid}",
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )

    try:
        assert proc.stdout is not None
        async for raw in proc.stdout:
            line = raw.decode("utf-8", errors="replace")
            extracted = _extract_hs_line(line)
            if extracted is None:
                continue
            try:
                parser.read_line(extracted)
            except Exception as e:
                print(f"[hslog parse error] {e!r}: {extracted.rstrip()!r}", file=sys.stderr)
    finally:
        try:
            proc.terminate()
        except ProcessLookupError:
            pass
        await proc.wait()
        flush()


def _extract_hs_line(line: str) -> str | None:
    """Pick the `D HH:MM:SS.fff <prefix>.<method>() …` payload out of a
    `log stream --style compact` line.

    macOS prepends its own timestamp + sender columns; we don't care about
    those. Returns None for any line that doesn't look like a Hearthstone
    Power event (e.g. unrelated Hearthstone log noise, OS chatter)."""
    if not line:
        return None
    m = _HS_LINE_RE.search(line)
    if m is None:
        return None
    payload = m.group(1)
    if not payload.endswith("\n"):
        payload += "\n"
    return payload
