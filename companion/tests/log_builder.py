"""Fluent builder for synthesizing Hearthstone Power.log content.

Lets us write deterministic scenarios that exercise game-state extractors
without needing a captured log. Methods chain so a scenario reads top-down
like the game-state events we're modeling.

Format references:
- Power.log line shape: ``D HH:MM:SS.fffffff GameState.DebugPrintPower() - <event>``
- CREATE_GAME / FULL_ENTITY / TAG_CHANGE event grammars are what hslog parses.

Limitations:
- Synthesizes only what the extractors actually look at — CARDTYPE, CONTROLLER,
  CARDRACE, ZONE, BACON_*, TAG_SCRIPT_DATA_NUM_*, ATK/HEALTH. Other tags are
  omitted; that's fine because the extractors ignore them.
- Timestamps auto-increment so the parser sees a monotonic stream.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

# Subset-tag suffix per CARDRACE name (HearthSim spelling, not the Race enum's).
_RACE_SUBSET_SUFFIX: dict[str, str] = {
    "DRAGON": "DRAGON",
    "MURLOC": "MURLOC",
    "DEMON": "DEMON",
    "BEAST": "BEAST",
    "MECHANICAL": "MECH",
    "PIRATE": "PIRATE",
    "ELEMENTAL": "ELEMENTALS",
    "QUILBOAR": "QUILLBOAR",
    "UNDEAD": "UNDEAD",
    "NAGA": "NAGA",
}


@dataclass
class _PlayerSpec:
    player_id: int
    team_id: int = 0
    teammate_player_id: int | None = None


@dataclass
class LogBuilder:
    lines: list[str] = field(default_factory=list)
    _ts_micros: int = 0  # monotonic timestamp counter
    _next_entity_id: int = 100  # entity ids 1..99 reserved for game/players
    _player_entity_id: dict[int, int] = field(default_factory=dict)  # player_id → entity_id
    _race_pool_entities: dict[str, list[int]] = field(default_factory=dict)  # race → [eid]

    # ----- low-level emit -----

    def _ts(self) -> str:
        self._ts_micros += 1000  # 1ms apart
        total_us = self._ts_micros
        h = (total_us // (3600 * 1_000_000)) % 24
        m = (total_us // (60 * 1_000_000)) % 60
        s = (total_us // 1_000_000) % 60
        frac = total_us % 1_000_000
        return f"D {h:02d}:{m:02d}:{s:02d}.{frac:07d}"

    def _emit(self, content: str) -> "LogBuilder":
        self.lines.append(f"{self._ts()} {content}\n")
        return self

    def _state(self, body: str, indent: int = 0) -> "LogBuilder":
        prefix = " " * indent
        return self._emit(f"GameState.DebugPrintPower() - {prefix}{body}")

    def _new_entity(self) -> int:
        eid = self._next_entity_id
        self._next_entity_id += 1
        return eid

    # ----- public API -----

    def create_game(self, players: Iterable[_PlayerSpec | dict] | None = None) -> "LogBuilder":
        """Emit a CREATE_GAME with the supplied players. Defaults to a single
        solo player (player_id=1, entity_id=2)."""
        if players is None:
            # hslog refuses to parse FullEntities until at least 2 players
            # have been declared, so default to a 2-player setup.
            specs = [
                _PlayerSpec(player_id=1, team_id=1),
                _PlayerSpec(player_id=2, team_id=2),
            ]
        else:
            specs = []
            for p in players:
                if isinstance(p, _PlayerSpec):
                    specs.append(p)
                else:
                    specs.append(_PlayerSpec(**p))

        self._state("CREATE_GAME")
        self._state("GameEntity EntityID=1", indent=4)
        self._state("tag=CARDTYPE value=GAME", indent=8)
        self._state("tag=STATE value=RUNNING", indent=8)

        next_eid = 2
        for spec in specs:
            eid = next_eid
            next_eid += 1
            self._state(
                f"Player EntityID={eid} PlayerID={spec.player_id} GameAccountId=[hi=1 lo={spec.player_id}]",
                indent=4,
            )
            self._state("tag=PLAYSTATE value=PLAYING", indent=8)
            self._state(f"tag=PLAYER_ID value={spec.player_id}", indent=8)
            self._state(f"tag=ENTITY_ID value={eid}", indent=8)
            self._state("tag=CARDTYPE value=PLAYER", indent=8)
            team = spec.team_id or spec.player_id
            self._state(f"tag=TEAM_ID value={team}", indent=8)
            self._state(f"tag=CONTROLLER value={spec.player_id}", indent=8)
            if spec.teammate_player_id is not None:
                self._state(
                    f"tag=BACON_DUO_TEAMMATE_PLAYER_ID value={spec.teammate_player_id}",
                    indent=8,
                )
            self._player_entity_id[spec.player_id] = eid

        return self

    def full_entity(
        self,
        card_id: str,
        controller: int = 1,
        *,
        cardtype: str = "ENCHANTMENT",
        num1: int | None = None,
        num2: int | None = None,
        atk: int | None = None,
        health: int | None = None,
        zone: str = "PLAY",
        cardrace: str | None = None,
        extra_tags: list[tuple[str, str | int]] | None = None,
    ) -> int:
        """Emit a generic FULL_ENTITY. Returns the new entity id."""
        eid = self._new_entity()
        self._state(
            f"FULL_ENTITY - Updating [entityName=stub id={eid} zone={zone} cardId={card_id} player={controller}] CardID={card_id}"
        )
        self._state(f"tag=CARDTYPE value={cardtype}", indent=4)
        self._state(f"tag=CONTROLLER value={controller}", indent=4)
        self._state(f"tag=ZONE value={zone}", indent=4)
        if num1 is not None:
            self._state(f"tag=TAG_SCRIPT_DATA_NUM_1 value={num1}", indent=4)
        if num2 is not None:
            self._state(f"tag=TAG_SCRIPT_DATA_NUM_2 value={num2}", indent=4)
        if atk is not None:
            self._state(f"tag=ATK value={atk}", indent=4)
        if health is not None:
            self._state(f"tag=HEALTH value={health}", indent=4)
        if cardrace is not None:
            self._state(f"tag=CARDRACE value={cardrace.upper()}", indent=4)
            suffix = _RACE_SUBSET_SUFFIX.get(cardrace.upper())
            if suffix is not None:
                self._state(f"tag=BACON_SUBSET_{suffix} value=1", indent=4)
        if extra_tags:
            for tag_name, tag_val in extra_tags:
                self._state(f"tag={tag_name} value={tag_val}", indent=4)
        return eid

    def cast_bloodgem(self, controller: int, attack: int, health: int, *, gem_variant: int = 1) -> "LogBuilder":
        card = "BG20_GEMe" if gem_variant == 1 else "BG20_GEMe2"
        self.full_entity(card, controller=controller, num1=attack, num2=health)
        return self

    def player_tracker(self, card_id: str, controller: int, num1: int, num2: int | None = None) -> "LogBuilder":
        """Emit a player-tracker enchantment (the canonical `pe` pattern)."""
        self.full_entity(card_id, controller=controller, num1=num1, num2=num2)
        return self

    def add_pool_minion(self, race: str, controller: int = 1, *, count: int = 1) -> list[int]:
        """Drop `count` minions of `race` into SETASIDE. Returns their entity ids."""
        ids: list[int] = []
        race_upper = race.upper()
        for _ in range(count):
            eid = self.full_entity(
                card_id=f"stub_{race_upper}",
                controller=controller,
                cardtype="MINION",
                cardrace=race_upper,
                zone="SETASIDE",
            )
            ids.append(eid)
        self._race_pool_entities.setdefault(race_upper, []).extend(ids)
        return ids

    def deplete_pool(self, race: str, count: int = 1) -> "LogBuilder":
        """Move `count` entities of `race` out of SETASIDE (simulating a buy)."""
        race_upper = race.upper()
        pool = self._race_pool_entities.get(race_upper, [])
        for _ in range(min(count, len(pool))):
            eid = pool.pop(0)
            self._state(f"TAG_CHANGE Entity={eid} tag=ZONE value=PLAY")
        return self

    def restock_pool(self, race: str, count: int = 1) -> "LogBuilder":
        """Move `count` previously-depleted entities back to SETASIDE (sells).
        Re-uses entities that were created but later moved out — for clean
        scenarios just call `add_pool_minion` again instead.
        """
        # No-op stub; simpler to rebuild fresh entities.
        return self

    def enter_combat(self, player_id: int) -> "LogBuilder":
        eid = self._player_entity_id.get(player_id)
        if eid is None:
            raise ValueError(f"unknown player_id {player_id}; call create_game first")
        self._state(f"TAG_CHANGE Entity={eid} tag=BACON_CURRENT_COMBAT_PLAYER_ID value={player_id}")
        return self

    def exit_combat(self, player_id: int) -> "LogBuilder":
        eid = self._player_entity_id.get(player_id)
        if eid is None:
            raise ValueError(f"unknown player_id {player_id}")
        self._state(f"TAG_CHANGE Entity={eid} tag=BACON_CURRENT_COMBAT_PLAYER_ID value=0")
        return self

    def update_tracker(self, entity_id: int, *, num1: int | None = None, num2: int | None = None) -> "LogBuilder":
        """Mutate NUM_1/NUM_2 on an existing tracker entity (TagChange)."""
        if num1 is not None:
            self._state(f"TAG_CHANGE Entity={entity_id} tag=TAG_SCRIPT_DATA_NUM_1 value={num1}")
        if num2 is not None:
            self._state(f"TAG_CHANGE Entity={entity_id} tag=TAG_SCRIPT_DATA_NUM_2 value={num2}")
        return self

    def update_minion_stats(self, entity_id: int, *, atk: int | None = None, health: int | None = None) -> "LogBuilder":
        """Mutate ATK/HEALTH on an existing minion (TagChange)."""
        if atk is not None:
            self._state(f"TAG_CHANGE Entity={entity_id} tag=ATK value={atk}")
        if health is not None:
            self._state(f"TAG_CHANGE Entity={entity_id} tag=HEALTH value={health}")
        return self

    def turn(self, n: int = 2) -> "LogBuilder":
        """Sentinel TAG_CHANGE that bumps TURN — useful as a flush point so
        any deferred FULL_ENTITY packets get delivered to the callback."""
        self._state(f"TAG_CHANGE Entity=1 tag=TURN value={n}")
        return self

    def delay(self, seconds: float) -> "LogBuilder":
        """Advance the timestamp clock so a paced replay sees a real gap
        before the next event. Useful for visual demos."""
        self._ts_micros += int(seconds * 1_000_000)
        return self

    def build(self) -> str:
        return "".join(self.lines)
