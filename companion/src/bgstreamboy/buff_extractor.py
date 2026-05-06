"""Extract numeric BG buff values from parsed packets.

Two patterns are supported:

1. **Per-cast** — short-lived enchantments whose NUM_1/NUM_2 reflect the
   strength applied at cast time (e.g. Blood Gems). The most recent cast wins.

2. **Player tracker** — invisible enchantments attached to a player entity
   (card IDs typically ending in `pe`). Their NUM_1/NUM_2 are mutated via
   TagChange as the player accumulates buffs. The latest tag value wins.

A single registry below maps card IDs → buff types. Adding a new buff = one
entry in `_REGISTRY` plus a card-art crop on the plugin side.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Literal

from hearthstone.enums import GameTag
from hslog.packets import FullEntity, Packet, ShowEntity, TagChange

from .snapshot import Buff


@dataclass(frozen=True)
class BuffSpec:
    """How to interpret a Hearthstone entity as a `Buff`.

    Most player-tracker enchantments carry their values in
    `TAG_SCRIPT_DATA_NUM_1/_NUM_2`. For self-tracking minions like Tethys
    and Lightfang Enforcer, the values live on the minion's own
    `ATK`/`HEALTH` tags instead — `value_tags` overrides per spec.
    """

    card_ids: frozenset[str]
    buff_type: str
    kind: Literal["per_cast", "player_tracker"]
    field: Literal["attack_health", "value"]
    value_tags: tuple[int, int | None] = (
        GameTag.TAG_SCRIPT_DATA_NUM_1.value,
        GameTag.TAG_SCRIPT_DATA_NUM_2.value,
    )


def _C(card_id: str, buff_type: str) -> BuffSpec:
    """Counter (single-int) player tracker."""
    return BuffSpec(
        card_ids=frozenset({card_id}),
        buff_type=buff_type,
        kind="player_tracker",
        field="value",
    )


def _S(card_id: str, buff_type: str) -> BuffSpec:
    """Stat-pair (NUM_1=attack, NUM_2=health) player tracker."""
    return BuffSpec(
        card_ids=frozenset({card_id}),
        buff_type=buff_type,
        kind="player_tracker",
        field="attack_health",
    )


_REGISTRY: tuple[BuffSpec, ...] = (
    # Per-cast: short-lived enchantments; latest cast wins.
    BuffSpec(
        card_ids=frozenset({"BG20_GEMe", "BG20_GEMe2"}),
        buff_type="bloodgem",
        kind="per_cast",
        field="attack_health",
    ),

    # ---- Counters (single integer) ----
    _C("BG25_008pe",        "eternal_knight"),
    _C("BG31_816pe",        "ballers_sold"),
    _C("BGS_028pe",         "pogos_played"),
    _C("BG22_HERO_305tpe",  "whelps_summoned"),
    _C("BG34_Giant_201pe",  "boars_died"),
    _C("BG_TTN_401pe",      "automatons_summoned"),
    _C("BGDUO31_208pe",     "sanlayn_died"),
    _C("BGDUO_119pe",       "orcestra_played"),

    # ---- Stat-pair trackers (NUM_1 / NUM_2 = +A / +H) ----
    _S("BG26_159pe",        "bloodgem_player"),  # backup tracker; per-cast usually wins
    _S("BG26_502pe",        "deep_blues"),
    _S("BG28_168pe",        "jewelry_box"),
    _S("BG31_830pe",        "tavern_spell"),
    _S("BG31_870pe",        "big_brother"),
    _S("BG32_861pe",        "temp_tavern_spell"),
    _S("BG34_402pe",        "whelp_buff"),
    _S("BG34_854pe",        "tavern_minion_buff"),
    _S("BG35_MagicItem_150pe", "cursed_crystal"),

    # ---- Hero / spell / treasure trackers (mostly +A/+H) ----
    _S("BG20_HERO_102pe",   "horde_hoard"),
    _S("BG21_020pe",        "dazzling_lightspawn"),
    _S("BG25_011pe",        "undying_army"),  # spec: "undead resummon stack"
    _S("BG26_162pe",        "dancing_barnstormer"),
    _S("BG26_805pe",        "humming_bird"),
    _S("BG27_556pe",        "diremuck"),
    _S("BG30_MagicItem_544pe", "nomi_sticker"),
    _S("BG31_808pe",        "beetle_army"),
    _S("BG31_815pe",        "dune_dweller"),
    _S("BG31_842pe",        "nether_construct"),
    _S("BG31_873pe",        "archimonde"),
    _S("BG32_814pe",        "align_elements"),
    _S("BG32_843pe",        "blazing_greasefire"),
    _S("BG33_112pe",        "haunted_carapace"),
    _S("BG33_152pe",        "improviser"),
    _S("BG33_311pe",        "felblaze_leader"),
    _S("BG33_805pe",        "gleaming_trader"),
    _S("BG34_170pe",        "volumizer"),
    _S("BG34_855pe",        "nomi_kitchen_dream"),
    _S("BG34_Giant_362pe",  "timewarped_goldrinn"),
    _S("BG35_150pe",        "fodder_refresh"),
    _S("BG35_152pe",        "tier3_shop_buff"),
    _S("BG35_153pe",        "consummate_conqueror"),
    _S("BG35_MagicItem_701pe", "fang_anklet"),
    _S("BGDUO33_150pe",     "dark_dazzler"),
    _S("BGDUO_121pe",       "manari_messenger"),
    _S("BGS_018pe",         "goldrinn"),
    _S("BGS_104pe",         "nomi"),

    # ---- Tavern shop buffs (BG_ShopBuff_*); per-tribe + generic ----
    _S("BG_ShopBuff",          "shop_buff"),
    _S("BG_ShopBuff_Beast",    "shop_buff_beast"),
    _S("BG_ShopBuff_Demon",    "shop_buff_demon"),
    _S("BG_ShopBuff_Dragon",   "shop_buff_dragon"),
    _S("BG_ShopBuff_Elemental", "shop_buff_elemental"),
    _S("BG_ShopBuff_Mech",     "shop_buff_mech"),
    _S("BG_ShopBuff_MultiRace", "shop_buff_multirace"),
    _S("BG_ShopBuff_Murloc",   "shop_buff_murloc"),
    _S("BG_ShopBuff_Naga",     "shop_buff_naga"),
    _S("BG_ShopBuff_Pirate",   "shop_buff_pirate"),
    _S("BG_ShopBuff_Quilboar", "shop_buff_quilboar"),
    _S("BG_ShopBuff_Undead",   "shop_buff_undead"),

    # ---- Self-tracking minions: read values off ATK/HEALTH on the minion ----
    BuffSpec(
        card_ids=frozenset({"BG26_766", "BG26_766_G"}),
        buff_type="tethys_growing",
        kind="player_tracker",
        field="attack_health",
        value_tags=(GameTag.ATK.value, GameTag.HEALTH.value),
    ),
    BuffSpec(
        card_ids=frozenset({"BGS_009", "TB_BaconUps_082"}),
        buff_type="lightfang_aura",
        kind="player_tracker",
        field="attack_health",
        value_tags=(GameTag.ATK.value, GameTag.HEALTH.value),
    ),

    # ---- Per-cast in-hand enchantment: latest spellcraft buff value wins ----
    BuffSpec(
        card_ids=frozenset({"BG23_Spellcraft_e"}),
        buff_type="spellcraft",
        kind="per_cast",
        field="attack_health",
    ),
)


_BY_CARD_ID: dict[str, BuffSpec] = {
    cid: spec for spec in _REGISTRY for cid in spec.card_ids
}


def _entity_id(entity: object) -> int | None:
    if isinstance(entity, int):
        return entity
    return getattr(entity, "entity_id", None)


def _read_nums(tags: list[tuple[int, int]], value_tags: tuple[int, int | None]) -> tuple[int | None, int | None]:
    num1_tag, num2_tag = value_tags
    num1 = num2 = None
    for tag, val in tags:
        if tag == num1_tag:
            num1 = val
        elif num2_tag is not None and tag == num2_tag:
            num2 = val
    return num1, num2


def _read_controller(tags: list[tuple[int, int]]) -> int | None:
    for tag, val in tags:
        if tag == GameTag.CONTROLLER:
            return val
    return None


# Sentinel for "controller wasn't on the entity's tags" — collapses to a
# pseudo-shared bucket so legacy callers (or solo games where we don't care
# about controller) still see all tracked buffs.
_UNKNOWN_CONTROLLER = 0


class BuffExtractor:
    def __init__(self) -> None:
        # controller (player_id) -> buff_type -> Buff
        self._buffs: dict[int, dict[str, Buff]] = {}
        # For player-tracker entities, store (spec, controller) so subsequent
        # TagChanges that mutate values route to the right per-controller bucket.
        self._tracked_entities: dict[int, tuple[BuffSpec, int]] = {}

    def observe(self, packet: Packet) -> bool:
        if isinstance(packet, (FullEntity, ShowEntity)):
            return self._observe_entity(packet)
        if isinstance(packet, TagChange):
            return self._observe_tag_change(packet)
        return False

    def _observe_entity(self, packet: FullEntity | ShowEntity) -> bool:
        """Handle both FULL_ENTITY (entity created visibly) and SHOW_ENTITY
        (entity revealed after being created hidden). Both carry a card_id
        and tags accumulated from the log."""
        spec = _BY_CARD_ID.get(packet.card_id or "")
        if spec is None:
            return False

        num1, num2 = _read_nums(packet.tags, spec.value_tags)
        controller = _read_controller(packet.tags) or _UNKNOWN_CONTROLLER

        if spec.kind == "player_tracker":
            eid = _entity_id(packet.entity)
            if eid is not None:
                self._tracked_entities[eid] = (spec, controller)

        return self._update_buff(spec, controller, num1, num2)

    def _observe_tag_change(self, packet: TagChange) -> bool:
        eid = _entity_id(packet.entity)
        if eid is None:
            return False
        tracked = self._tracked_entities.get(eid)
        if tracked is None:
            return False
        spec, controller = tracked
        if spec.kind != "player_tracker":
            return False

        num1_tag, num2_tag = spec.value_tags
        if packet.tag == num1_tag:
            return self._update_field(spec, controller, num1=packet.value)
        if num2_tag is not None and packet.tag == num2_tag:
            return self._update_field(spec, controller, num2=packet.value)
        return False

    def _bucket(self, controller: int) -> dict[str, Buff]:
        return self._buffs.setdefault(controller, {})

    def _update_buff(self, spec: BuffSpec, controller: int, num1: int | None, num2: int | None) -> bool:
        bucket = self._bucket(controller)
        existing = bucket.get(spec.buff_type)
        if spec.field == "attack_health":
            if num1 is None or num2 is None:
                return False
            if existing and existing.attack == num1 and existing.health == num2:
                return False
            bucket[spec.buff_type] = Buff(
                type=spec.buff_type,
                attack=num1,
                health=num2,
                last_changed=time.time(),
            )
            return True
        # field == "value"
        if num1 is None:
            return False
        if existing and existing.value == num1:
            return False
        bucket[spec.buff_type] = Buff(
            type=spec.buff_type,
            value=num1,
            last_changed=time.time(),
        )
        return True

    def _update_field(self, spec: BuffSpec, controller: int, *, num1: int | None = None, num2: int | None = None) -> bool:
        bucket = self._bucket(controller)
        existing = bucket.get(spec.buff_type)
        if existing is None:
            # Many BG player trackers (e.g. BG25_008pe) arrive without initial
            # NUM tags and only get them populated via subsequent TagChanges.
            # Initialize the buff on first TagChange so we don't drop it.
            if spec.field == "value" and num1 is not None:
                bucket[spec.buff_type] = Buff(
                    type=spec.buff_type,
                    value=num1,
                    last_changed=time.time(),
                )
                return True
            if spec.field == "attack_health" and num1 is not None and num2 is not None:
                bucket[spec.buff_type] = Buff(
                    type=spec.buff_type,
                    attack=num1,
                    health=num2,
                    last_changed=time.time(),
                )
                return True
            # Stat-pair with only one of the two values yet — wait for the other.
            return False
        if spec.field == "attack_health":
            new_attack = num1 if num1 is not None else existing.attack
            new_health = num2 if num2 is not None else existing.health
            if new_attack == existing.attack and new_health == existing.health:
                return False
            bucket[spec.buff_type] = existing.model_copy(update={
                "attack": new_attack,
                "health": new_health,
                "last_changed": time.time(),
            })
            return True
        # field == "value"
        new_val = num1 if num1 is not None else existing.value
        if new_val == existing.value:
            return False
        bucket[spec.buff_type] = existing.model_copy(update={
            "value": new_val,
            "last_changed": time.time(),
        })
        return True

    def buffs(self, controller: int | None = None) -> list[Buff]:
        """Return tracked buffs.

        With `controller` set, returns only that player's buffs. Without it,
        returns the union across all controllers seen — useful when we
        haven't yet identified perspective.
        """
        if controller is not None:
            return list(self._buffs.get(controller, {}).values())
        out: list[Buff] = []
        for bucket in self._buffs.values():
            out.extend(bucket.values())
        return out
