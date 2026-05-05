"""Track active BG tribes and their shared-pool counts.

Each minion entity in the game carries one or more `BACON_SUBSET_<TRIBE>`
flags indicating which lobby-tribe pools it belongs to. The shared pool
itself is the SETASIDE zone — minions move between SETASIDE and tavern
zones (PLAY/HAND) as players buy and sell.

Lobby tribes: derived from which BACON_SUBSET_* tags appear with non-zero
counts on at least one minion. The 5 most-represented tribes are the
"active" lobby tribes.

Pool counts: count of distinct entities currently in SETASIDE that carry
each tribe's BACON_SUBSET flag.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from hearthstone.enums import GameTag, Zone
from hslog.packets import FullEntity, Packet, TagChange

from .snapshot import Tribe

# Map BACON_SUBSET_* GameTag suffix to the user-facing tribe key.
# Tribe keys are stable identifiers used by the plugin's icon registry.
_SUBSET_TO_TRIBE: dict[str, str] = {
    "BACON_SUBSET_DRAGON": "dragon",
    "BACON_SUBSET_MURLOC": "murloc",
    "BACON_SUBSET_DEMON": "demon",
    "BACON_SUBSET_BEAST": "beast",
    "BACON_SUBSET_MECH": "mech",
    "BACON_SUBSET_PIRATE": "pirate",
    "BACON_SUBSET_ELEMENTALS": "elemental",
    "BACON_SUBSET_QUILLBOAR": "quilboar",
    "BACON_SUBSET_UNDEAD": "undead",
    "BACON_SUBSET_NAGA": "naga",
}

# Reverse: GameTag value → tribe key.
_TAG_VALUE_TO_TRIBE: dict[int, str] = {
    GameTag[name].value: tribe for name, tribe in _SUBSET_TO_TRIBE.items()
}

_NUM_LOBBY_TRIBES = 5


@dataclass
class _EntState:
    tribes: set[str] = field(default_factory=set)
    zone: int | None = None


class TribeTracker:
    def __init__(self) -> None:
        self._ents: dict[int, _EntState] = {}
        self._max_pool_seen: dict[str, int] = {}
        self._cached: list[Tribe] = []

    def observe(self, packet: Packet) -> bool:
        """Update internal state from a packet. Returns True if tribes changed."""
        if isinstance(packet, FullEntity):
            ent_id = packet.entity if isinstance(packet.entity, int) else getattr(packet.entity, "entity_id", None)
            if ent_id is None:
                return False
            state = self._ents.setdefault(ent_id, _EntState())
            for tag, val in packet.tags:
                tribe = _TAG_VALUE_TO_TRIBE.get(tag)
                if tribe is not None and val:
                    state.tribes.add(tribe)
                elif tag == GameTag.ZONE:
                    state.zone = val
        elif isinstance(packet, TagChange):
            if packet.tag != GameTag.ZONE:
                return False
            ent_id = packet.entity if isinstance(packet.entity, int) else getattr(packet.entity, "entity_id", None)
            if ent_id is None or ent_id not in self._ents:
                return False
            self._ents[ent_id].zone = packet.value
        else:
            return False

        return self._recompute()

    def _recompute(self) -> bool:
        # Count entities in SETASIDE per tribe.
        pool: dict[str, int] = {}
        for state in self._ents.values():
            if state.zone != Zone.SETASIDE:
                continue
            for tribe in state.tribes:
                pool[tribe] = pool.get(tribe, 0) + 1

        # Track high-water mark per tribe so we can pick the lobby tribes
        # even if the pool is partially drained when we first see it.
        for tribe, count in pool.items():
            if count > self._max_pool_seen.get(tribe, 0):
                self._max_pool_seen[tribe] = count

        # Top 5 by high-water mark = lobby tribes.
        lobby = sorted(self._max_pool_seen.items(), key=lambda x: -x[1])[:_NUM_LOBBY_TRIBES]
        new_cached = [
            Tribe(name=name, remaining=pool.get(name), max=hw)
            for name, hw in lobby
        ]

        if [(t.name, t.remaining, t.max) for t in new_cached] == [
            (t.name, t.remaining, t.max) for t in self._cached
        ]:
            return False
        self._cached = new_cached
        return True

    def tribes(self) -> list[Tribe]:
        return list(self._cached)
