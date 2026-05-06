"""Detect Battlegrounds phase (recruit vs combat).

The standard Hearthstone `Step` enum doesn't usefully transition during a BG
game — BG uses its own signal. The reliable per-round phase indicator is the
`BACON_CURRENT_COMBAT_PLAYER_ID` GameTag on player entities:

  - 0 on every player → no combat in progress → "recruit"
  - non-zero on any player → that player is currently fighting → "combat"

Empirically verified against tests/fixtures/duos_2026_05_02.power.log.
"""

from __future__ import annotations

from hearthstone.enums import GameTag
from hslog.packets import CreateGame, FullEntity, Packet, TagChange

from .snapshot import Phase


def _entity_id(entity: object) -> int | None:
    """hslog uses raw int IDs OR PlayerReference for entity references."""
    if isinstance(entity, int):
        return entity
    return getattr(entity, "entity_id", None)


class PhaseDetector:
    def __init__(self) -> None:
        self.phase: Phase = "unknown"
        self._player_combat_id: dict[int, int] = {}

    def observe(self, packet: Packet) -> bool:
        """Update internal state from a packet. Returns True if phase changed."""
        before = self.phase

        if isinstance(packet, CreateGame):
            # We're now in a game — assume recruit until a combat tag fires.
            if self.phase == "unknown":
                self.phase = "recruit"
        elif isinstance(packet, FullEntity):
            for tag, val in packet.tags:
                self._apply(packet.entity, tag, val)
        elif isinstance(packet, TagChange):
            self._apply(packet.entity, packet.tag, packet.value)

        return self.phase != before

    def _apply(self, entity: object, tag: int, value: int) -> None:
        try:
            gtag = GameTag(tag)
        except ValueError:
            return
        if gtag != GameTag.BACON_CURRENT_COMBAT_PLAYER_ID:
            return
        eid = _entity_id(entity)
        if eid is None:
            return
        self._player_combat_id[eid] = value
        in_combat = any(v > 0 for v in self._player_combat_id.values())
        self.phase = "combat" if in_combat else "recruit"
