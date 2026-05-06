"""End-to-end scenarios that exercise the companion's extractors against
synthesized Power.log streams. Each scenario:

  1. Builds a deterministic log via `LogBuilder`.
  2. Replays it through the same Service → snapshot pipeline that the live
     companion uses (minus the WebSocket — we collect snapshots in-process).
  3. Prints + asserts what the snapshot looks like at the end (and at key
     transitions).

Run with: cd companion && uv run python tests/scenarios.py
"""

from __future__ import annotations

import logging
import sys

logging.disable(logging.CRITICAL)

from bgstreamboy.buff_extractor import BuffExtractor
from bgstreamboy.log_tailer import _hook_register_packet
from bgstreamboy.perspective import Perspective
from bgstreamboy.phase_detector import PhaseDetector
from bgstreamboy.snapshot import Side, Snapshot
from bgstreamboy.tribe_tracker import TribeTracker
from hslog import LogParser

from log_builder import LogBuilder, _PlayerSpec  # type: ignore[import-not-found]


class _SimService:
    """In-process equivalent of `Service` — same reducer, no asyncio/WS."""

    def __init__(self) -> None:
        self.phase = PhaseDetector()
        self.buffs = BuffExtractor()
        self.tribes = TribeTracker()
        self.perspective = Perspective()
        self.snapshot = Snapshot()
        self.snapshots_at_phase: dict[str, Snapshot] = {}

    def on_packet(self, packet) -> None:
        if self.phase.observe(packet):
            self.snapshot = self.snapshot.model_copy(update={"phase": self.phase.phase})
        perspective_changed = self.perspective.observe(packet)
        if self.buffs.observe(packet) or perspective_changed:
            self.snapshot = self.snapshot.model_copy(update=self._buff_fields())
        if self.tribes.observe(packet):
            self.snapshot = self.snapshot.model_copy(update={"tribes": self.tribes.tribes()})
        # Always remember the latest snapshot for each phase value.
        self.snapshots_at_phase[self.snapshot.phase] = self.snapshot.model_copy()

    def _buff_fields(self) -> dict[str, object]:
        our = self.perspective.our_player_id
        ally = self.perspective.ally_player_id
        player_buffs = self.buffs.buffs(controller=our) if our else self.buffs.buffs()
        ally_side = Side(buffs=self.buffs.buffs(controller=ally)) if ally else None
        return {"player": Side(buffs=player_buffs), "ally": ally_side}


def _run(name: str, log_text: str) -> _SimService:
    parser = LogParser()
    svc = _SimService()
    _, flush = _hook_register_packet(parser, svc.on_packet)
    for line in log_text.splitlines(keepends=True):
        try:
            parser.read_line(line)
        except Exception as e:
            print(f"  [{name}] parse error: {e!r}: {line.rstrip()!r}", file=sys.stderr)
    flush()
    return svc


def _tag(name: str) -> str:
    return f"\033[1;36m{name}\033[0m"


# ----------------------------- scenarios --------------------------------


def scenario_solo_phase_flip() -> None:
    print(f"=== {_tag('solo_phase_flip')} ===")
    log = (
        LogBuilder()
        .create_game()  # default 2 players (hslog requirement) but no teammate tag = solo
        .cast_bloodgem(controller=1, attack=4, health=2)
        .turn()
        .enter_combat(1)
        .turn()
        .exit_combat(1)
        .turn()
        .build()
    )
    svc = _run("solo_phase_flip", log)
    assert svc.perspective.our_player_id == 1
    assert svc.perspective.ally_player_id is None
    assert "combat" in svc.snapshots_at_phase
    assert "recruit" in svc.snapshots_at_phase
    final = svc.snapshot
    assert any(b.type == "bloodgem" and b.attack == 4 for b in final.player.buffs)
    assert final.ally is None
    print(f"  perspective: us={svc.perspective.our_player_id}")
    print(f"  phases reached: {sorted(svc.snapshots_at_phase)}")
    print(f"  player.buffs: {[(b.type, b.attack, b.health) for b in final.player.buffs]}")
    print("  PASS\n")


def scenario_duos_ally_swap() -> None:
    print(f"=== {_tag('duos_ally_swap')} ===")
    log = (
        LogBuilder()
        .create_game([
            _PlayerSpec(player_id=1, team_id=1, teammate_player_id=2),
            _PlayerSpec(player_id=2, team_id=1),
        ])
        .cast_bloodgem(controller=1, attack=4, health=2)   # ours
        .cast_bloodgem(controller=2, attack=8, health=4)   # ally's
        .turn()
        .enter_combat(1)
        .turn()
        .exit_combat(1)
        .turn()
        .build()
    )
    svc = _run("duos_ally_swap", log)

    assert svc.perspective.our_player_id == 1
    assert svc.perspective.ally_player_id == 2, f"got {svc.perspective.ally_player_id}"

    combat = svc.snapshots_at_phase["combat"]
    recruit = svc.snapshots_at_phase["recruit"]

    # Plugin's swap rule:
    def plugin_view(snap: Snapshot) -> list:
        return list(snap.ally.buffs) if snap.phase == "combat" and snap.ally else list(snap.player.buffs)

    recruit_view = plugin_view(recruit)
    combat_view = plugin_view(combat)

    assert any(b.type == "bloodgem" and b.attack == 4 for b in recruit_view), "recruit should show OUR bloodgem"
    assert any(b.type == "bloodgem" and b.attack == 8 for b in combat_view), "combat should show ALLY bloodgem"

    print(f"  perspective: us={svc.perspective.our_player_id} ally={svc.perspective.ally_player_id}")
    print(f"  recruit (plugin shows): {[(b.type, b.attack, b.health) for b in recruit_view]}")
    print(f"  combat  (plugin shows): {[(b.type, b.attack, b.health) for b in combat_view]}")
    print("  PASS\n")


def scenario_multiple_buff_types() -> None:
    print(f"=== {_tag('multiple_buff_types')} ===")
    # Cover three patterns simultaneously: per-cast (bloodgem), counter-style
    # player tracker (eternal_knight), and stat-pair tracker (whelp_buff).
    log = (
        LogBuilder()
        .create_game()
        .cast_bloodgem(controller=1, attack=18, health=6)
        .player_tracker("BG25_008pe", controller=1, num1=7)        # eternal_knight count
        .player_tracker("BG34_402pe", controller=1, num1=12, num2=12)  # whelp_buff stats
        .turn()
        .build()
    )
    svc = _run("multiple_buff_types", log)
    types = {b.type for b in svc.snapshot.player.buffs}
    assert "bloodgem" in types
    assert "eternal_knight" in types
    assert "whelp_buff" in types
    print(f"  buffs: {sorted((b.type, b.attack, b.health, b.value) for b in svc.snapshot.player.buffs)}")
    print("  PASS\n")


def scenario_minion_self_tracking() -> None:
    print(f"=== {_tag('minion_self_tracking')} ===")
    # Tethys reads off her own ATK/HEALTH; values change via TagChange as
    # she grows. Verify that flow.
    builder = (
        LogBuilder()
        .create_game()
    )
    tethys_eid = builder.full_entity(
        card_id="BG26_766", controller=1, cardtype="MINION", atk=8, health=6
    )
    log = (
        builder
        .turn()
        .update_minion_stats(tethys_eid, atk=14, health=10)
        .turn()
        .update_minion_stats(tethys_eid, atk=20, health=14)
        .turn()
        .build()
    )
    svc = _run("minion_self_tracking", log)
    tethys = next((b for b in svc.snapshot.player.buffs if b.type == "tethys_growing"), None)
    assert tethys is not None, "tethys_growing should be tracked"
    assert tethys.attack == 20 and tethys.health == 14, f"latest stats wrong: {tethys}"
    print(f"  final tethys: +{tethys.attack}/+{tethys.health}")
    print("  PASS\n")


def scenario_tribe_pool_depletion() -> None:
    print(f"=== {_tag('tribe_pool_depletion')} ===")
    # Initial pool with 5 tribes, then deplete two of them and confirm
    # remaining counts shrink.
    builder = LogBuilder().create_game()
    for race, count in [
        ("DRAGON", 20),
        ("MURLOC", 15),
        ("BEAST", 18),
        ("MECHANICAL", 12),
        ("ELEMENTAL", 16),
    ]:
        builder.add_pool_minion(race, count=count)
    builder.turn()  # flush initial entities
    # Buy 5 dragons + 8 elementals out of pool
    builder.deplete_pool("DRAGON", 5)
    builder.deplete_pool("ELEMENTAL", 8)
    builder.turn()

    svc = _run("tribe_pool_depletion", builder.build())
    by_name = {t.name: (t.remaining, t.max) for t in svc.snapshot.tribes}
    print(f"  detected tribes: {by_name}")
    # The 5 lobby tribes are present (top by high-water mark)
    assert set(by_name) == {"dragon", "murloc", "beast", "mech", "elemental"}, by_name
    # Dragon depleted 5 from 20 = 15 remaining
    assert by_name["dragon"] == (15, 20), by_name["dragon"]
    # Elemental depleted 8 from 16 = 8 remaining
    assert by_name["elemental"] == (8, 16), by_name["elemental"]
    # Untouched tribes keep their max
    assert by_name["murloc"] == (15, 15), by_name["murloc"]
    print("  PASS\n")


def scenario_per_cast_dedup() -> None:
    print(f"=== {_tag('per_cast_dedup')} ===")
    # Two consecutive identical bloodgems should not produce duplicate
    # last_changed mutations; differing ones should overwrite.
    log = (
        LogBuilder()
        .create_game()
        .cast_bloodgem(controller=1, attack=2, health=1)
        .cast_bloodgem(controller=1, attack=2, health=1)  # identical
        .cast_bloodgem(controller=1, attack=4, health=2)  # changed
        .turn()
        .build()
    )
    svc = _run("per_cast_dedup", log)
    bloodgems = [b for b in svc.snapshot.player.buffs if b.type == "bloodgem"]
    assert len(bloodgems) == 1
    assert bloodgems[0].attack == 4
    print(f"  final bloodgem: +{bloodgems[0].attack}/+{bloodgems[0].health}")
    print("  PASS\n")


def scenario_combat_oscillation() -> None:
    print(f"=== {_tag('combat_oscillation')} ===")
    # Several recruit↔combat flips should produce the expected number of
    # phase transitions, not get stuck.
    builder = LogBuilder().create_game()
    transitions = 0
    for _ in range(4):
        builder.enter_combat(1).turn().exit_combat(1).turn()
    svc = _run("combat_oscillation", builder.build())
    # Final state should be recruit (after the last exit_combat).
    assert svc.snapshot.phase == "recruit", svc.snapshot.phase
    assert "combat" in svc.snapshots_at_phase
    print("  observed both phases across 4 oscillations, settled on recruit")
    print("  PASS\n")


def scenario_full_catalog_smoke() -> None:
    """Drop one instance of every registered buff card_id and verify the
    extractor surfaces all of them. Acts as a regression check for the
    registry — if a future spec change drops an entry, this fails loudly."""
    print(f"=== {_tag('full_catalog_smoke')} ===")
    from bgstreamboy.buff_extractor import _REGISTRY

    builder = LogBuilder().create_game()
    expected_types: set[str] = set()
    for spec in _REGISTRY:
        expected_types.add(spec.buff_type)
        card_id = next(iter(spec.card_ids))
        if spec.value_tags == (
            __import__("hearthstone").enums.GameTag.ATK.value,
            __import__("hearthstone").enums.GameTag.HEALTH.value,
        ):
            builder.full_entity(card_id, controller=1, cardtype="MINION", atk=10, health=10)
        else:
            num1 = 7
            num2 = 7 if spec.field == "attack_health" else None
            builder.full_entity(card_id, controller=1, num1=num1, num2=num2)
    builder.turn()

    svc = _run("full_catalog_smoke", builder.build())
    seen_types = {b.type for b in svc.snapshot.player.buffs}
    missing = expected_types - seen_types
    assert not missing, f"missing buffs: {sorted(missing)}"
    print(f"  surfaced all {len(seen_types)} buff types")
    print("  PASS\n")


def main() -> int:
    scenarios = [
        scenario_solo_phase_flip,
        scenario_duos_ally_swap,
        scenario_multiple_buff_types,
        scenario_minion_self_tracking,
        scenario_tribe_pool_depletion,
        scenario_per_cast_dedup,
        scenario_combat_oscillation,
        scenario_full_catalog_smoke,
    ]
    failures = 0
    for s in scenarios:
        try:
            s()
        except AssertionError as e:
            print(f"  FAIL: {e}\n", file=sys.stderr)
            failures += 1
        except Exception as e:
            print(f"  ERROR: {type(e).__name__}: {e}\n", file=sys.stderr)
            failures += 1
    print(f"--- {len(scenarios) - failures}/{len(scenarios)} scenarios passed ---")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
