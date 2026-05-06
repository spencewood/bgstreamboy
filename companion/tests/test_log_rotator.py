"""Unit-ish tests for the log rotator's behavior under various scenarios.

Run with: cd companion && uv run python tests/test_log_rotator.py
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from bgstreamboy.log_rotator import (
    HEARTHSTONE_HARD_CAP_BYTES,
    ROTATE_THRESHOLD_BYTES,
    STALL_SECONDS,
    TRUNCATION_MARKER,
    LogRotator,
)


def _capture_status() -> tuple[list, callable]:
    events: list = []
    def cb(status, detail):
        events.append((status, detail))
    return events, cb


def t_no_rotation_under_threshold() -> None:
    print("=== no_rotation_under_threshold ===")
    with tempfile.TemporaryDirectory() as d:
        log = Path(d) / "Power.log"
        log.write_bytes(b"x" * (ROTATE_THRESHOLD_BYTES // 2))
        events, cb = _capture_status()
        r = LogRotator(log, on_status=cb)
        assert not r.maybe_rotate()
        assert log.stat().st_size == ROTATE_THRESHOLD_BYTES // 2
        assert not r.archives()
        print("  PASS\n")


def t_rotates_above_threshold() -> None:
    print("=== rotates_above_threshold ===")
    with tempfile.TemporaryDirectory() as d:
        log = Path(d) / "Power.log"
        log.write_bytes(b"x" * (ROTATE_THRESHOLD_BYTES + 100))
        events, cb = _capture_status()
        r = LogRotator(log, on_status=cb)

        assert r.maybe_rotate(), "should have rotated"
        assert log.stat().st_size == 0, "log should be truncated"
        archives = r.archives()
        assert len(archives) == 1, f"expected 1 archive, got {len(archives)}"
        assert archives[0].exists(), "archive missing"
        assert archives[0].stat().st_size == ROTATE_THRESHOLD_BYTES + 100, "archive size mismatch"
        statuses = [s for s, _ in events]
        assert "rotated" in statuses, f"never reported 'rotated': {statuses}"
        print(f"  archived → {archives[0].name}, status events: {statuses}")
        print("  PASS\n")


def t_multiple_rotations_numbered() -> None:
    print("=== multiple_rotations_numbered ===")
    with tempfile.TemporaryDirectory() as d:
        log = Path(d) / "Power.log"
        events, cb = _capture_status()
        r = LogRotator(log, on_status=cb)

        for _ in range(3):
            log.write_bytes(b"x" * (ROTATE_THRESHOLD_BYTES + 1))
            assert r.maybe_rotate()

        archives = r.archives()
        assert len(archives) == 3, f"expected 3 archives, got {len(archives)}"
        names = [a.name for a in archives]
        assert "part-001" in names[0]
        assert "part-002" in names[1]
        assert "part-003" in names[2]
        print(f"  archives: {names}")
        print("  PASS\n")


def t_truncation_marker_detected() -> None:
    print("=== truncation_marker_detected ===")
    with tempfile.TemporaryDirectory() as d:
        log = Path(d) / "Power.log"
        log.write_bytes(b"")
        events, cb = _capture_status()
        r = LogRotator(log, on_status=cb)

        r.observe_line(f"D 12:34:56.789 {TRUNCATION_MARKER} of 10000KB\n")
        assert r.status() == "hearthstone_capped", r.status()
        statuses = [s for s, _ in events]
        assert "hearthstone_capped" in statuses
        print(f"  detected via line; status events: {statuses}")
        print("  PASS\n")


def t_recovery_after_capped() -> None:
    """If Hearthstone resumes writing somehow (rare but possible), status
    should clear back to 'ok'."""
    print("=== recovery_after_capped ===")
    with tempfile.TemporaryDirectory() as d:
        log = Path(d) / "Power.log"
        log.write_bytes(b"")
        events, cb = _capture_status()
        r = LogRotator(log, on_status=cb)
        r.observe_line(f"D 12:34:56.789 {TRUNCATION_MARKER} of 10000KB\n")
        assert r.status() == "hearthstone_capped"

        # Now Hearthstone writes new content (file size grows).
        log.write_bytes(b"new content")
        r.maybe_rotate()
        assert r.status() == "ok"
        statuses = [s for s, _ in events]
        assert statuses[-1] == "ok"
        print(f"  recovered; status events: {statuses}")
        print("  PASS\n")


def t_stall_detection() -> None:
    print("=== stall_detection (uses time-travel; ~no actual wait) ===")
    with tempfile.TemporaryDirectory() as d:
        log = Path(d) / "Power.log"
        log.write_bytes(b"x" * (ROTATE_THRESHOLD_BYTES + 100))
        events, cb = _capture_status()
        r = LogRotator(log, on_status=cb)
        r.maybe_rotate()  # rotates; status -> rotated
        # Backdate the rotator's growth clock so stall detection fires.
        r._state.last_growth_at = time.monotonic() - (STALL_SECONDS + 5)  # noqa: SLF001
        r.maybe_rotate()  # should observe stall (file is 0 bytes, not above threshold)
        assert r.status() == "rotation_stalled", r.status()
        print(f"  stall detected; status: {r.status()}")
        print("  PASS\n")


def t_rotation_failed_when_path_unwritable() -> None:
    print("=== rotation_failed_when_unwritable ===")
    with tempfile.TemporaryDirectory() as d:
        log = Path(d) / "Power.log"
        log.write_bytes(b"x" * (ROTATE_THRESHOLD_BYTES + 100))
        # Make parent dir read-only so archive creation fails.
        log.parent.chmod(0o555)
        try:
            events, cb = _capture_status()
            r = LogRotator(log, on_status=cb)
            r.maybe_rotate()
            statuses = [s for s, _ in events]
            assert "rotation_failed" in statuses, f"expected failure, got {statuses}"
            print(f"  status events: {statuses}")
            print("  PASS\n")
        finally:
            log.parent.chmod(0o755)  # restore so cleanup works


def main() -> int:
    tests = [
        t_no_rotation_under_threshold,
        t_rotates_above_threshold,
        t_multiple_rotations_numbered,
        t_truncation_marker_detected,
        t_recovery_after_capped,
        t_stall_detection,
        t_rotation_failed_when_path_unwritable,
    ]
    fails = 0
    for t in tests:
        try:
            t()
        except AssertionError as e:
            print(f"  FAIL: {e}\n", file=sys.stderr)
            fails += 1
    total = len(tests)
    print(f"--- {total - fails}/{total} passed ---")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
