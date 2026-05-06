"""Glue: parser callback → snapshot reducer → WebSocket broadcast."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from hslog.packets import Packet

from .buff_extractor import BuffExtractor
from .log_tailer import follow_async, replay_paced_async
from .perspective import Perspective
from .phase_detector import PhaseDetector
from .snapshot import Side, Snapshot
from .team_stats import TeamStatsTracker
from .tribe_tracker import TribeTracker
from .ws_server import DEFAULT_HOST, DEFAULT_PORT, SnapshotBroadcaster, serve_forever

log = logging.getLogger(__name__)


class Service:
    def __init__(self, broadcaster: SnapshotBroadcaster) -> None:
        self._broadcaster = broadcaster
        self._phase = PhaseDetector()
        self._buffs = BuffExtractor()
        self._team_stats = TeamStatsTracker()
        self._tribes = TribeTracker()
        self._perspective = Perspective()
        self._snapshot = Snapshot()

    def on_packet(self, packet: Packet) -> None:
        changed = False

        if self._phase.observe(packet):
            self._snapshot = self._snapshot.model_copy(update={"phase": self._phase.phase})
            changed = True

        # Perspective changes don't directly mutate the snapshot, but they
        # change which controller's buffs map to player vs ally.
        perspective_changed = self._perspective.observe(packet)
        team_changed = self._team_stats.observe(packet)

        if self._buffs.observe(packet) or perspective_changed or team_changed:
            self._snapshot = self._snapshot.model_copy(update=self._buff_snapshot_fields())
            changed = True

        if self._tribes.observe(packet):
            self._snapshot = self._snapshot.model_copy(update={"tribes": self._tribes.tribes()})
            changed = True

        if changed:
            asyncio.create_task(self._broadcaster.broadcast(self._snapshot))

    def _buff_snapshot_fields(self) -> dict[str, object]:
        our_pid = self._perspective.our_player_id
        ally_pid = self._perspective.ally_player_id

        if our_pid is not None:
            player_buffs = self._buffs.buffs(controller=our_pid)
            board = self._team_stats.buff_for(our_pid)
            if board is not None:
                player_buffs = [board] + player_buffs
        else:
            player_buffs = self._buffs.buffs()

        ally_side: Side | None = None
        if ally_pid is not None:
            ally_buffs = self._buffs.buffs(controller=ally_pid)
            ally_board = self._team_stats.buff_for(ally_pid)
            if ally_board is not None:
                ally_buffs = [ally_board] + ally_buffs
            ally_side = Side(buffs=ally_buffs)

        return {"player": Side(buffs=player_buffs), "ally": ally_side}


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
    """Drive the same WebSocket pipeline from a captured Power.log file."""
    broadcaster = SnapshotBroadcaster()
    service = Service(broadcaster)
    await asyncio.gather(
        serve_forever(broadcaster, host=host, port=port),
        replay_paced_async(replay_path, service.on_packet, speed=speed),
    )
