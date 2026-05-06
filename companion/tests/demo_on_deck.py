"""Animate the test scenarios on a connected Stream Deck.

Each scene prints its name to the console and then drives the deck through
a deliberate state. Pauses are long enough to read each frame.

Run with:
    cd companion && uv run python tests/demo_on_deck.py
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.WARNING, format="%(message)s")

sys.path.insert(0, str(Path(__file__).parent))
from log_builder import LogBuilder, _PlayerSpec  # type: ignore[import-not-found]

from bgstreamboy.log_tailer import _hook_register_packet
from bgstreamboy.service import Service
from bgstreamboy.ws_server import DEFAULT_HOST, DEFAULT_PORT, SnapshotBroadcaster, serve_forever
from hslog import LogParser


HOLD = 3.5  # seconds to hold each scene visible on the deck
QUICK = 0.8  # for incremental updates within a scene


class _SceneRunner:
    """Wraps a Service + LogParser so scenes can stream lines and the deck
    sees them as they arrive (vs. queuing all up front)."""

    def __init__(self, broadcaster: SnapshotBroadcaster) -> None:
        self.service = Service(broadcaster)
        self.parser = LogParser()
        _, self.flush = _hook_register_packet(self.parser, self.service.on_packet)

    def feed(self, log_text: str) -> None:
        for line in log_text.splitlines(keepends=True):
            try:
                self.parser.read_line(line)
            except Exception as e:
                print(f"parse: {e!r}", file=sys.stderr)
        self.flush()


async def _scene(name: str, runner: _SceneRunner, builder: LogBuilder, hold: float = HOLD) -> None:
    print(f"  ▸ {name}")
    runner.feed(builder.build())
    builder.lines.clear()  # reuse the builder for the next scene's increment
    await asyncio.sleep(hold)


async def run_demo(broadcaster: SnapshotBroadcaster) -> None:
    runner = _SceneRunner(broadcaster)
    b = LogBuilder()

    print()
    print("== bgstreamboy on-deck demo ==")
    print()

    # Lobby init: us=1, ally=2 (duos team)
    b.create_game([
        _PlayerSpec(player_id=1, team_id=1, teammate_player_id=2),
        _PlayerSpec(player_id=2, team_id=1),
    ])
    # Add an initial pool right at lobby start so tribes appear quickly.
    for race, count in [("DRAGON", 20), ("MURLOC", 18), ("BEAST", 16),
                        ("MECHANICAL", 14), ("ELEMENTAL", 22)]:
        b.add_pool_minion(race, count=count)
    b.turn()
    await _scene("lobby init: 5 tribes appear (all green)", runner, b, hold=HOLD)

    # ---- player builds up a varied buff set ----
    b.cast_bloodgem(controller=1, attack=18, health=6)
    b.turn()
    await _scene("player: bloodgem +18/+6", runner, b, hold=QUICK)

    b.player_tracker("BG25_008pe", controller=1, num1=5)
    b.turn()
    await _scene("player: + eternal knight (×5)", runner, b, hold=QUICK)

    b.player_tracker("BG28_168pe", controller=1, num1=8, num2=8)
    b.turn()
    await _scene("player: + jewelry box +8/+8", runner, b, hold=QUICK)

    b.player_tracker("BG34_402pe", controller=1, num1=4, num2=4)
    b.turn()
    await _scene("player: + whelp buff +4/+4", runner, b, hold=HOLD)

    # ---- pool depletes (color shift) ----
    b.deplete_pool("ELEMENTAL", 18)  # 22 → 4 (red)
    b.deplete_pool("DRAGON", 13)     # 20 → 7 (yellow)
    b.turn()
    await _scene("pool depletes: elementals red, dragons yellow", runner, b, hold=HOLD)

    # ---- ally builds up a DIFFERENT buff set ----
    b.player_tracker("BGS_028pe", controller=2, num1=7)  # pogos played
    b.turn()
    await _scene("ally: pogos played (×7)", runner, b, hold=QUICK)

    b.player_tracker("BG31_816pe", controller=2, num1=4)  # ballers sold
    b.turn()
    await _scene("ally: + ballers sold (×4)", runner, b, hold=QUICK)

    b.cast_bloodgem(controller=2, attack=24, health=12)
    b.turn()
    await _scene("ally: + bloodgem +24/+12", runner, b, hold=HOLD)

    # ---- THE SWAP: combat enters, deck flips to ally's buffs ----
    print()
    print("  *** combat enters — deck flips to ALLY's buffs ***")
    b.enter_combat(1)
    b.turn()
    await _scene("(combat: ally buffs visible — pogos, ballers, bloodgem)", runner, b, hold=HOLD * 1.5)

    # combat exits — back to player buffs
    print()
    print("  *** combat exits — deck flips back to YOUR buffs ***")
    b.exit_combat(1)
    b.turn()
    await _scene("(recruit: your 4 buffs return)", runner, b, hold=HOLD * 1.5)

    # ---- one more swap to make the round-trip clear ----
    print()
    print("  *** combat enters again — back to ally ***")
    b.enter_combat(1)
    b.turn()
    await _scene("(combat: ally buffs again)", runner, b, hold=HOLD)

    b.exit_combat(1)
    b.turn()
    await _scene("(recruit: your buffs)", runner, b, hold=HOLD)

    print()
    print("== demo complete — final state held on deck. Ctrl-C to exit. ==")


async def _wait_for_client(broadcaster: SnapshotBroadcaster, timeout: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if broadcaster._clients:  # noqa: SLF001
            return True
        await asyncio.sleep(0.2)
    return False


async def main() -> None:
    broadcaster = SnapshotBroadcaster()
    server_task = asyncio.create_task(
        serve_forever(broadcaster, host=DEFAULT_HOST, port=DEFAULT_PORT)
    )
    print(f"ws server up on ws://{DEFAULT_HOST}:{DEFAULT_PORT}; waiting for plugin to connect...")
    if not await _wait_for_client(broadcaster):
        print("ERROR: no plugin connected within 30s.", file=sys.stderr)
        server_task.cancel()
        return
    print("plugin connected.")
    await asyncio.sleep(0.5)  # let connect handshake settle

    try:
        await run_demo(broadcaster)
        await server_task
    except KeyboardInterrupt:
        pass
    finally:
        server_task.cancel()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
