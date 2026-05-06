"""JSON schema for state snapshots emitted to the Stream Deck plugin."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Mode = Literal["solo", "duos", "unknown"]
Phase = Literal["recruit", "combat", "hero_select", "shopping", "other", "unknown"]


class Buff(BaseModel):
    type: str
    label: str | None = None
    attack: int | None = None
    health: int | None = None
    value: int | None = None
    current: int | None = None
    target: int | None = None
    last_changed: float


class Tribe(BaseModel):
    name: str
    remaining: int | None = None
    max: int | None = None
    """High-water mark seen for this tribe's shared pool — used by the
    plugin to compute a fullness ratio for color-shifting."""


class Side(BaseModel):
    buffs: list[Buff] = Field(default_factory=list)


ServiceStatus = Literal[
    "ok",
    "rotated",
    "rotation_stalled",
    "hearthstone_capped",
    "rotation_failed",
]


class Snapshot(BaseModel):
    mode: Mode = "unknown"
    phase: Phase = "unknown"
    player: Side = Field(default_factory=Side)
    ally: Side | None = None
    tribes: list[Tribe] = Field(default_factory=list)
    service_status: ServiceStatus = "ok"
