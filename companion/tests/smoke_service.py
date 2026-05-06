"""End-to-end smoke test for the companion service.

Starts the service against a temp Hearthstone-shaped logs dir, bulk-writes
the synthetic Power.log fixture into a fresh session subdir, and verifies
that the websocket stream surfaces the expected phase transitions.

For richer integration testing against a real captured game (with bloodgems,
tribes, etc.) drop a captured `Power.log` into `tests/fixtures/` (gitignored
by default) and replay it with:

    uv run bgstreamboy --replay tests/fixtures/your_capture.power.log

Run with: cd companion && uv run python tests/smoke_service.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

import websockets

from bgstreamboy import service
from bgstreamboy.ws_server import DEFAULT_HOST

PORT = 18765

FIXTURE = Path(__file__).parent / "fixtures" / "spike_minimal.power.log"


async def main() -> int:
    tmpdir = tempfile.TemporaryDirectory()
    try:
        logs_dir = Path(tmpdir.name)
        session_dir = logs_dir / "Hearthstone_2026_05_05_12_00_00"
        session_dir.mkdir()
        log_path = session_dir / "Power.log"
        log_path.touch()

        service_task = asyncio.create_task(
            # Explicit source="file" — this test covers the file-tailing path.
            # Console streaming is exercised by run_log_stream_test instead.
            service.run(logs_dir, host=DEFAULT_HOST, port=PORT, source="file")
        )

        if not await _wait_for_service(service_task):
            return 1

        async with websockets.connect(f"ws://{DEFAULT_HOST}:{PORT}") as ws:
            try:
                await asyncio.wait_for(ws.recv(), timeout=0.2)
            except TimeoutError:
                pass

            received: list[str] = []

            async def collect():
                try:
                    async for msg in ws:
                        received.append(msg)
                except websockets.ConnectionClosed:
                    pass

            collector = asyncio.create_task(collect())

            with log_path.open("a") as out:
                out.write(FIXTURE.read_text())
                out.flush()

            await asyncio.sleep(2.5)
            collector.cancel()

        if not received:
            print("ERROR: no snapshots broadcast", file=sys.stderr)
            return 1

        latest = json.loads(received[-1])
        phases_seen = {json.loads(m)["phase"] for m in received}

        print(f"snapshots received: {len(received)}")
        print(f"phases seen: {phases_seen}")
        print(f"final: {latest}")

        assert "combat" in phases_seen, f"never saw combat phase; got {phases_seen}"
        assert "recruit" in phases_seen, f"never saw recruit phase; got {phases_seen}"

        print("OK")
        return 0
    finally:
        for task in asyncio.all_tasks() - {asyncio.current_task()}:
            task.cancel()
        tmpdir.cleanup()


async def _wait_for_service(service_task: asyncio.Task) -> bool:
    for attempt in range(50):
        if service_task.done():
            exc = service_task.exception()
            print(f"service crashed before probe: {exc!r}", file=sys.stderr)
            return False
        try:
            async with websockets.connect(f"ws://{DEFAULT_HOST}:{PORT}"):
                return True
        except (OSError, ConnectionRefusedError):
            await asyncio.sleep(0.1)
    print(f"ERROR: service didn't start after {attempt+1} attempts", file=sys.stderr)
    return False


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
