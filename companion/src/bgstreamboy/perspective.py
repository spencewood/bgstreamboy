"""Identify which player is 'us' and which is the duo ally.

In Hearthstone client logs, the FRIENDLY (local) player is conventionally
the first player declared in `CreateGame.players` — that's the perspective
the log was written from. In Duos, the local player's entity carries
`BACON_DUO_TEAMMATE_PLAYER_ID` whose value is the teammate's player_id.

Best-effort: if we never see the teammate tag (e.g. the parser opened
mid-game and missed lobby init), `ally_player_id` stays None and the
service treats all buffs as the local player's.
"""

from __future__ import annotations

from hearthstone.enums import GameTag
from hslog.packets import CreateGame, Packet, TagChange


def _player_id(entity: object) -> int | None:
    """Resolve a TagChange entity (PlayerReference or int) to a player_id."""
    return getattr(entity, "player_id", None)


class Perspective:
    def __init__(self) -> None:
        self.our_player_id: int | None = None
        self.ally_player_id: int | None = None

    def observe(self, packet: Packet) -> bool:
        before = (self.our_player_id, self.ally_player_id)

        if isinstance(packet, CreateGame):
            if packet.players and self.our_player_id is None:
                self.our_player_id = packet.players[0].player_id
            for pl in packet.players:
                for tag, val in pl.tags:
                    if tag == GameTag.BACON_DUO_TEAMMATE_PLAYER_ID:
                        if pl.player_id == self.our_player_id:
                            self.ally_player_id = val

        elif isinstance(packet, TagChange):
            if packet.tag == GameTag.BACON_DUO_TEAMMATE_PLAYER_ID:
                pid = _player_id(packet.entity)
                if pid is not None and pid == self.our_player_id:
                    self.ally_player_id = packet.value

        return (self.our_player_id, self.ally_player_id) != before
