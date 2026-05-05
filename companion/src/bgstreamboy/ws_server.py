"""Local WebSocket broadcast for state snapshots.

Plugin clients subscribe; service pushes the latest snapshot whenever it
changes. Snapshots are also sent immediately on connect so a freshly-launched
plugin gets the current state without waiting for the next change.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Iterable

from websockets.asyncio.server import ServerConnection, serve

from .snapshot import Snapshot

log = logging.getLogger(__name__)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


class SnapshotBroadcaster:
    def __init__(self) -> None:
        self._clients: set[ServerConnection] = set()
        self._latest_json: str | None = None
        self._lock = asyncio.Lock()

    async def handle_client(self, ws: ServerConnection) -> None:
        self._clients.add(ws)
        log.info("client connected: %s (total=%d)", ws.remote_address, len(self._clients))
        try:
            if self._latest_json is not None:
                await ws.send(self._latest_json)
            async for _ in ws:
                pass  # we don't expect inbound messages; drain to keep the connection alive
        finally:
            self._clients.discard(ws)
            log.info("client disconnected (remaining=%d)", len(self._clients))

    async def broadcast(self, snapshot: Snapshot) -> None:
        payload = snapshot.model_dump_json()
        async with self._lock:
            if payload == self._latest_json:
                return
            self._latest_json = payload
        await self._fanout(payload, list(self._clients))

    @staticmethod
    async def _fanout(payload: str, targets: Iterable[ServerConnection]) -> None:
        await asyncio.gather(
            *(_safe_send(ws, payload) for ws in targets),
            return_exceptions=True,
        )


async def _safe_send(ws: ServerConnection, payload: str) -> None:
    try:
        await ws.send(payload)
    except Exception as e:
        log.debug("send failed for %s: %r", ws.remote_address, e)


async def serve_forever(
    broadcaster: SnapshotBroadcaster,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> None:
    async with serve(broadcaster.handle_client, host, port):
        log.info("websocket server listening on ws://%s:%d", host, port)
        await asyncio.Future()  # run forever
