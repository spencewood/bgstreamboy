"""Tail Hearthstone's Power.log and feed lines into hslog's LogParser.

Hearthstone on macOS writes per-session log directories at
`/Applications/Hearthstone/Logs/Hearthstone_<timestamp>/Power.log`. The
follower auto-discovers the most recent session and switches to a fresh log
whenever Hearthstone restarts and creates a new session directory.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable
from pathlib import Path

from hslog import LogParser
from hslog.packets import (
    ChangeEntity,
    CreateGame,
    FullEntity,
    Packet,
    ShowEntity,
)
from watchfiles import awatch

from .log_rotator import LogRotator, TRUNCATION_MARKER

# Packet types whose `tags` list is populated on lines AFTER the packet is
# registered. We deliver these to the callback only when the *next* packet
# arrives (or on flush) so the tags are observable.
_DEFERRED_PACKET_TYPES = (CreateGame, FullEntity, ShowEntity, ChangeEntity)

# Player declarations are nested inside a CreateGame: hslog calls
# `register_packet` for them but their `tags` accumulate later, and the
# whole CreateGame is what consumers actually want. Suppress them from the
# user callback and keep the pending CreateGame alive across them.
_NESTED_IN_CREATE_GAME = (CreateGame.Player,)

from .platform_paths import discover_logs_dir

DEFAULT_LOGS_DIR: Path = discover_logs_dir()

PacketCallback = Callable[[Packet], None]


def find_latest_session_log(logs_dir: Path) -> Path | None:
    """Return the most recent session's Power.log, or None."""
    if not logs_dir.exists():
        return None
    candidates: list[tuple[float, Path]] = []
    for d in logs_dir.iterdir():
        if d.is_dir() and d.name.startswith("Hearthstone_"):
            log = d / "Power.log"
            if log.exists():
                candidates.append((d.stat().st_mtime, log))
    if not candidates:
        return None
    candidates.sort()
    return candidates[-1][1]


def _hook_register_packet(parser: LogParser, on_packet: PacketCallback) -> tuple[LogParser, Callable[[], None]]:
    """Install a per-packet callback.

    Multi-line packets (FullEntity, CreateGame, ShowEntity, ChangeEntity) get
    their `tags` populated on lines AFTER they're registered, so we hold them
    until the next packet arrives — by then their tags are complete.
    Single-line packets (TagChange, MetaData, etc.) are delivered immediately.

    Returns (parser, flush). Call flush() at end-of-stream (e.g. after replay)
    to deliver any deferred packet still held.
    """
    state = parser._parsing_state
    original = state.register_packet
    pending: list[Packet | None] = [None]

    def hooked(packet: Packet, node=None) -> None:
        original(packet, node)
        # Player declarations belong to the in-flight CreateGame — keep the
        # pending CreateGame alive so it can keep accumulating Players + tags.
        if isinstance(packet, _NESTED_IN_CREATE_GAME):
            return
        if pending[0] is not None:
            on_packet(pending[0])
            pending[0] = None
        if isinstance(packet, _DEFERRED_PACKET_TYPES):
            pending[0] = packet
        else:
            on_packet(packet)

    def flush() -> None:
        if pending[0] is not None:
            on_packet(pending[0])
            pending[0] = None

    state.register_packet = hooked
    return parser, flush


def _drain_complete_lines(f, parser: LogParser, rotator: LogRotator | None = None) -> None:
    while True:
        pos = f.tell()
        line = f.readline()
        if not line.endswith("\n"):
            f.seek(pos)
            return
        if rotator is not None and TRUNCATION_MARKER in line:
            rotator.observe_line(line)
        try:
            parser.read_line(line)
        except Exception as e:
            print(f"[hslog parse error] {e!r}: {line.rstrip()!r}", file=sys.stderr)


async def follow_async(logs_dir: Path, on_packet: PacketCallback) -> None:
    """Block forever (asyncio), auto-discovering and tailing the latest session.

    When Hearthstone restarts and creates a new session directory, we discard
    the old parser state and start fresh on the new Power.log.
    """
    while True:
        target = find_latest_session_log(logs_dir)
        if target is None:
            print(f"[bgstreamboy] no Hearthstone session under {logs_dir}; waiting...", file=sys.stderr)
            logs_dir.mkdir(parents=True, exist_ok=True)
            async for _ in awatch(str(logs_dir), recursive=True, debounce=200):
                if find_latest_session_log(logs_dir) is not None:
                    break
            continue

        print(f"[bgstreamboy] tailing {target}", file=sys.stderr)
        parser = LogParser()
        _hook_register_packet(parser, on_packet)
        try:
            await _consume_session(target, parser, logs_dir)
        except FileNotFoundError:
            continue
        # Session ended (rotated / truncated). Don't flush pending: that
        # packet's tags weren't completed before the file went away.


async def _consume_session(log_path: Path, parser: LogParser, logs_dir: Path) -> None:
    """Tail log_path. Return when a newer session appears or the file is truncated.

    Reads from the beginning of the file so we don't miss CREATE_GAME (which
    typically lands moments before we attach to a freshly-created session log).

    Also runs a `LogRotator` that proactively rolls the file when it
    approaches Hearthstone's 10 MB cap. Hearthstone closes the log handle
    permanently once it hits the cap, so without rotation a long session
    goes silent.
    """
    rotator = LogRotator(log_path)
    with log_path.open("r", encoding="utf-8", errors="replace") as f:
        f.seek(0)
        _drain_complete_lines(f, parser, rotator)
        last_size = log_path.stat().st_size
        if rotator.maybe_rotate():
            return  # attached to an already-oversized file
        async for _ in awatch(str(logs_dir), recursive=True, debounce=200):
            latest = find_latest_session_log(logs_dir)
            if latest is not None and latest != log_path:
                print(f"[bgstreamboy] new session detected, switching: {latest}", file=sys.stderr)
                return
            try:
                current_size = log_path.stat().st_size
            except FileNotFoundError:
                return
            if current_size < last_size:
                return  # truncation (either ours via rotation or Hearthstone's)
            _drain_complete_lines(f, parser, rotator)
            last_size = log_path.stat().st_size
            # Pre-empt Hearthstone's 10 MB cap. If we rotate, the file shrinks
            # and the next loop iteration's truncation check returns us to
            # follow_async, which will reattach to the same path.
            if rotator.maybe_rotate():
                return


def follow_file(log_path: Path, on_packet: PacketCallback) -> None:
    """Synchronous one-shot tail of a specific file (useful for tests/debugging).

    Does not handle session switching.
    """
    import asyncio

    async def _run():
        parser = LogParser()
        _hook_register_packet(parser, on_packet)
        await _consume_single(log_path, parser)

    asyncio.run(_run())


async def follow_file_async(log_path: Path, on_packet: PacketCallback) -> None:
    """Async one-shot tail of a specific file. Used by the smoke test."""
    parser = LogParser()
    _hook_register_packet(parser, on_packet)
    await _consume_single(log_path, parser)


async def _consume_single(log_path: Path, parser: LogParser) -> None:
    with log_path.open("r", encoding="utf-8", errors="replace") as f:
        f.seek(0, 2)
        last_size = f.tell()
        _drain_complete_lines(f, parser)
        async for _ in awatch(str(log_path), debounce=200):
            try:
                current_size = log_path.stat().st_size
            except FileNotFoundError:
                return
            if current_size < last_size:
                return
            _drain_complete_lines(f, parser)
            last_size = log_path.stat().st_size


def replay(path: Path, on_packet: PacketCallback) -> None:
    """Feed an existing log file through the parser end-to-end (for testing)."""
    parser = LogParser()
    _, flush = _hook_register_packet(parser, on_packet)
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                parser.read_line(line)
            except Exception as e:
                print(f"[hslog parse error] {e!r}: {line.rstrip()!r}", file=sys.stderr)
    flush()


async def replay_paced_async(
    path: Path,
    on_packet: PacketCallback,
    *,
    speed: float = 5.0,
    max_gap_seconds: float = 5.0,
) -> None:
    """Replay a captured Power.log over time, pacing by its embedded timestamps.

    `speed` is a multiplier on real time (5x = compressed by 5; 1x = real time).
    `max_gap_seconds` caps long idle stretches in the log so the replay
    doesn't sit silently for minutes.
    """
    parser = LogParser()
    _, flush = _hook_register_packet(parser, on_packet)

    prev_ts: float | None = None
    line_count = 0

    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            this_ts = _parse_line_ts(line)
            if this_ts is not None and prev_ts is not None:
                delta = (this_ts - prev_ts) / speed
                if delta > 0:
                    await asyncio.sleep(min(delta, max_gap_seconds))
            try:
                parser.read_line(line)
            except Exception as e:
                print(f"[hslog parse error] {e!r}: {line.rstrip()!r}", file=sys.stderr)
            if this_ts is not None:
                prev_ts = this_ts
            line_count += 1
            if line_count % 5000 == 0:
                print(f"[bgstreamboy replay] {line_count} lines processed", file=sys.stderr)

    flush()
    print(f"[bgstreamboy replay] done ({line_count} lines)", file=sys.stderr)


def _parse_line_ts(line: str) -> float | None:
    """Extract seconds-of-day from a Power.log line: 'D HH:MM:SS.fffffff ...'."""
    if len(line) < 18 or line[0] not in "DEWVI":
        return None
    parts = line.split(None, 2)
    if len(parts) < 2:
        return None
    try:
        h, m, s = parts[1].split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)
    except (ValueError, IndexError):
        return None
