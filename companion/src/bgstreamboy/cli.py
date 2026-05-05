"""Companion service entry point."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from . import service
from .log_config_installer import (
    CONFIG_PATH,
    install as install_log_config,
    is_installed as log_config_is_installed,
)
from .log_tailer import DEFAULT_LOGS_DIR, find_latest_session_log
from .ws_server import DEFAULT_HOST, DEFAULT_PORT


def main() -> None:
    parser = argparse.ArgumentParser(prog="bgstreamboy")
    parser.add_argument(
        "--logs-dir",
        type=Path,
        default=DEFAULT_LOGS_DIR,
        help="Hearthstone Logs/ directory; auto-discovers latest session under it.",
    )
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--install-log-config",
        action="store_true",
        help="Write Hearthstone's log.config and exit. Restart Hearthstone afterward.",
    )
    parser.add_argument(
        "--replay",
        type=Path,
        help="Replay a captured Power.log over WebSocket instead of tailing live. "
        "The plugin sees identical traffic; useful for demos / development without Hearthstone.",
    )
    parser.add_argument(
        "--replay-speed",
        type=float,
        default=5.0,
        help="Replay speed multiplier (default 5x real time). 1.0 = real time. Higher = faster.",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )

    if args.install_log_config:
        path = install_log_config()
        print(f"Wrote {path}.")
        print("Restart Hearthstone for it to take effect.")
        return

    if args.replay is not None:
        if not args.replay.exists():
            print(f"Replay file not found: {args.replay}", file=sys.stderr)
            sys.exit(1)
        print(
            f"Replaying {args.replay} at {args.replay_speed}x onto ws://{args.host}:{args.port}",
            file=sys.stderr,
        )
        try:
            asyncio.run(
                service.run_replay(args.replay, host=args.host, port=args.port, speed=args.replay_speed)
            )
        except KeyboardInterrupt:
            pass
        return

    if not log_config_is_installed():
        print(f"Hearthstone log.config missing or incomplete at {CONFIG_PATH}.", file=sys.stderr)
        print("Run `bgstreamboy --install-log-config`, then restart Hearthstone.", file=sys.stderr)
        sys.exit(1)

    latest = find_latest_session_log(args.logs_dir)
    if latest is None:
        print(
            f"No Hearthstone session log under {args.logs_dir}; will wait for one to appear.",
            file=sys.stderr,
        )
    else:
        print(f"Latest existing session log: {latest}", file=sys.stderr)

    try:
        asyncio.run(service.run(args.logs_dir, host=args.host, port=args.port))
    except KeyboardInterrupt:
        pass
