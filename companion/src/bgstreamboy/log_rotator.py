"""Proactively rotate Hearthstone's Power.log to dodge its 10 MB cap.

Hearthstone enforces a hard 10 MB per-session limit on Power.log. When the
cap is hit, Hearthstone writes a "Truncating log..." marker, then stops
writing entirely for the rest of that game session — the file handle gets
closed and never reopened. Restarting Hearthstone is the only way to recover.

This module pre-empts that by rolling the log under Hearthstone's nose:

  - Watch the file size during normal tailing.
  - When it crosses ROTATE_THRESHOLD (well under the cap), copy current
    contents to a sibling archive file and truncate the original to 0 bytes.
  - If Hearthstone is checking file size before its internal cap-check, this
    resets its perception and it keeps writing. Our `_consume_session` already
    detects truncation and re-attaches.

The bet relies on Hearthstone polling file size rather than maintaining its
own monotonic counter. We can't tell which from the outside, so the rotator
also exposes status hooks so callers know when:

  - Rotation succeeded (writing resumed).
  - Rotation appears to have failed (no new writes for STALL_SECONDS).
  - The "Truncating log..." marker was observed in raw input (cap hit
    without our intervention — Hearthstone has gone silent).

The plan is "accommodate all possibilities" — preserve archive files,
report all states upward, never lose data, never silently fail.
"""

from __future__ import annotations

import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal

ROTATE_THRESHOLD_BYTES = 8 * 1024 * 1024     # 8 MB — well below HS's 10 MB cap
HEARTHSTONE_HARD_CAP_BYTES = 10 * 1024 * 1024  # for diagnostics
STALL_SECONDS = 25                            # if no growth this long after rotation, declare failed
TRUNCATION_MARKER = "Truncating log, which has reached the size limit"

LogStatus = Literal[
    "ok",
    "rotated",
    "rotation_stalled",     # rotated but Hearthstone hasn't resumed writing
    "hearthstone_capped",   # we saw the truncation marker before we could rotate
    "rotation_failed",      # an OS error stopped us copying / truncating
]


@dataclass
class _State:
    rotation_count: int = 0
    last_rotation_at: float = 0.0
    last_growth_at: float = 0.0
    last_size_seen: int = 0
    status: LogStatus = "ok"
    archive_dir: Path | None = None
    archives: list[Path] = field(default_factory=list)


class LogRotator:
    """Owns rotation lifecycle for a single session log file."""

    def __init__(
        self,
        log_path: Path,
        *,
        on_status: Callable[[LogStatus, str], None] | None = None,
        threshold: int = ROTATE_THRESHOLD_BYTES,
    ) -> None:
        self.log_path = log_path
        self.threshold = threshold
        self._on_status = on_status or _default_status_logger
        self._state = _State()
        self._state.last_growth_at = time.monotonic()

    # ---- public ----

    def maybe_rotate(self) -> bool:
        """Rotate if the log has grown past the threshold. Returns True if
        a rotation was performed."""
        try:
            size = self.log_path.stat().st_size
        except FileNotFoundError:
            return False

        # Track growth for stall detection.
        if size > self._state.last_size_seen:
            self._state.last_growth_at = time.monotonic()
            # Mark recovered if we were stalled.
            if self._state.status in ("rotation_stalled", "hearthstone_capped"):
                self._update_status("ok", f"writes resumed at {size} bytes")
        self._state.last_size_seen = size

        if size <= self.threshold:
            self._maybe_emit_stall()
            return False

        self._do_rotate(size)
        return True

    def observe_line(self, line: str) -> None:
        """Watch for Hearthstone's own truncation marker in parsed lines."""
        if TRUNCATION_MARKER in line:
            self._update_status(
                "hearthstone_capped",
                "Hearthstone wrote 'Truncating log…' — writes will stop until session restart",
            )

    def status(self) -> LogStatus:
        return self._state.status

    def archives(self) -> list[Path]:
        return list(self._state.archives)

    # ---- internals ----

    def _do_rotate(self, size_at_rotate: int) -> None:
        try:
            archive_dir = self._ensure_archive_dir()
            self._state.rotation_count += 1
            stamp = time.strftime("%H%M%S")
            archive_path = archive_dir / (
                f"{self.log_path.stem}.part-{self._state.rotation_count:03d}-{stamp}.log"
            )
            shutil.copy2(self.log_path, archive_path)
            # Truncate in place. open(..., "w") replaces the file's contents
            # with the empty string (size becomes 0), preserving the inode so
            # any append-mode handles Hearthstone is holding stay valid.
            with self.log_path.open("w", encoding="utf-8"):
                pass
            self._state.last_rotation_at = time.monotonic()
            self._state.last_growth_at = time.monotonic()  # reset stall clock
            self._state.last_size_seen = 0
            self._state.archives.append(archive_path)
            self._update_status(
                "rotated",
                f"size hit {size_at_rotate} bytes; archived → {archive_path}",
            )
        except OSError as e:
            self._update_status("rotation_failed", f"{type(e).__name__}: {e}")

    def _ensure_archive_dir(self) -> Path:
        if self._state.archive_dir is None:
            d = self.log_path.parent / "rotated"
            d.mkdir(exist_ok=True)
            self._state.archive_dir = d
        return self._state.archive_dir

    def _maybe_emit_stall(self) -> None:
        """If we just rotated and writing hasn't resumed, surface that."""
        if self._state.last_rotation_at == 0:
            return
        if self._state.status in ("rotation_stalled", "hearthstone_capped"):
            return
        if time.monotonic() - self._state.last_growth_at < STALL_SECONDS:
            return
        self._update_status(
            "rotation_stalled",
            f"no writes for {STALL_SECONDS}s after rotation — Hearthstone may not have resumed",
        )

    def _update_status(self, new: LogStatus, detail: str) -> None:
        if new == self._state.status and new == "ok":
            return
        self._state.status = new
        self._on_status(new, detail)


def _default_status_logger(status: LogStatus, detail: str) -> None:
    print(f"[log_rotator] {status}: {detail}", file=sys.stderr)
