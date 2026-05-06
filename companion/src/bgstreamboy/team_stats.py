"""Track summed ATK/HEALTH across the player's minions currently on board.

Per-buff registries don't capture the actual *result* of all those buffs —
your minions' on-board stats. This tracker watches every minion entity's
ATK/HEALTH/ZONE/CONTROLLER and exposes a per-controller total for minions
in zone PLAY (i.e. on the board).

Emitted as a synthetic `Buff(type="team_stats", attack=sum_atk, health=sum_hp)`
so it slots into the existing snapshot pipeline.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from hearthstone.enums import GameTag, CardType, Zone
from hslog.packets import FullEntity, Packet, ShowEntity, TagChange

from .snapshot import Buff


@dataclass
class _MinionState:
    controller: int = 0
    atk: int = 0
    health: int = 0
    zone: int = 0


def _entity_id(entity: object) -> int | None:
    if isinstance(entity, int):
        return entity
    return getattr(entity, "entity_id", None)


class TeamStatsTracker:
    def __init__(self) -> None:
        self._minions: dict[int, _MinionState] = {}
        # cache: controller -> last computed (atk, hp) so we avoid spurious updates
        self._last_totals: dict[int, tuple[int, int]] = {}

    def observe(self, packet: Packet) -> bool:
        if isinstance(packet, (FullEntity, ShowEntity)):
            return self._observe_entity(packet)
        if isinstance(packet, TagChange):
            return self._observe_tag_change(packet)
        return False

    def _observe_entity(self, packet: FullEntity | ShowEntity) -> bool:
        eid = _entity_id(packet.entity)
        if eid is None:
            return False
        is_minion = False
        ctrl = atk = hp = zone = None
        for tag, val in packet.tags:
            if tag == GameTag.CARDTYPE and val == CardType.MINION:
                is_minion = True
            elif tag == GameTag.CONTROLLER:
                ctrl = val
            elif tag == GameTag.ATK:
                atk = val
            elif tag == GameTag.HEALTH:
                hp = val
            elif tag == GameTag.ZONE:
                zone = val
        if not is_minion:
            return False
        state = self._minions.setdefault(eid, _MinionState())
        if ctrl is not None: state.controller = ctrl
        if atk is not None: state.atk = atk
        if hp is not None: state.health = hp
        if zone is not None: state.zone = zone
        return self._totals_changed(state.controller)

    def _observe_tag_change(self, packet: TagChange) -> bool:
        eid = _entity_id(packet.entity)
        if eid is None or eid not in self._minions:
            return False
        state = self._minions[eid]
        if packet.tag == GameTag.ATK:
            state.atk = packet.value
        elif packet.tag == GameTag.HEALTH:
            state.health = packet.value
        elif packet.tag == GameTag.ZONE:
            state.zone = packet.value
        elif packet.tag == GameTag.CONTROLLER:
            state.controller = packet.value
        else:
            return False
        return self._totals_changed(state.controller)

    def _totals_changed(self, controller: int) -> bool:
        new = self._compute_totals(controller)
        old = self._last_totals.get(controller)
        if old == new:
            return False
        self._last_totals[controller] = new
        return True

    def _compute_totals(self, controller: int) -> tuple[int, int]:
        atk_sum = hp_sum = 0
        for m in self._minions.values():
            if m.controller != controller:
                continue
            if m.zone != Zone.PLAY:
                continue
            atk_sum += m.atk
            hp_sum += m.health
        return atk_sum, hp_sum

    def buff_for(self, controller: int) -> Buff | None:
        atk, hp = self._last_totals.get(controller, (0, 0))
        if atk == 0 and hp == 0:
            return None
        return Buff(
            type="team_stats",
            attack=atk,
            health=hp,
            last_changed=time.time(),
        )
