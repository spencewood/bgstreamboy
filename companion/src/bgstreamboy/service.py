"""Glue: parser callback → snapshot reducer → WebSocket broadcast."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from hslog.packets import Packet

from .buff_extractor import BuffExtractor
from .log_tailer import follow_async, replay_paced_async
from .phase_detector import PhaseDetector
from .snapshot import Side, Snapshot
from .tribe_tracker import TribeTracker
from .ws_server import DEFAULT_HOST, DEFAULT_PORT, SnapshotBroadcaster, serve_forever

log = logging.getLogger(__name__)


class Service:
    def __init__(self, broadcaster: SnapshotBroadcaster) -> None:
        self._broadcaster = broadcaster
        self._phase = PhaseDetector()
        self._buffs = BuffExtractor()
        self._tribes = TribeTracker()
        self._snapshot = Snapshot()

    def on_packet(self, packet: Packet) -> None:
        changed = False

        if self._phase.observe(packet):
            self._snapshot = self._snapshot.model_copy(update={"phase": self._phase.phase})
            changed = True

        if self._buffs.observe(packet):
            self._snapshot = self._snapshot.model_copy(
                update={"player": Side(buffs=self._buffs.buffs())}
            )
            changed = True

        if self._tribes.observe(packet):
            self._snapshot = self._snapshot.model_copy(update={"tribes": self._tribes.tribes()})
            changed = True

        if changed:
            asyncio.create_task(self._broadcaster.broadcast(self._snapshot))


async def run(logs_dir: Path, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    broadcaster = SnapshotBroadcaster()
    service = Service(broadcaster)
    await asyncio.gather(
        serve_forever(broadcaster, host=host, port=port),
        follow_async(logs_dir, service.on_packet),
    )


async def run_replay(
    replay_path: Path,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    speed: float = 5.0,
) -> None:
    """Drive the same WebSocket pipeline from a captured Power.log file.

    The plugin sees identical traffic to a live session — useful when you
    don't have Hearthstone running but want to demo the deck.
    """
    broadcaster = SnapshotBroadcaster()
    service = Service(broadcaster)
    await asyncio.gather(
        serve_forever(broadcaster, host=host, port=port),
        replay_paced_async(replay_path, service.on_packet, speed=speed),
    )
