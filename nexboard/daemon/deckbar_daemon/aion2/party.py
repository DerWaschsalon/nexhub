"""Die eigene Gruppe: wo die Mitspieler stehen, wie sie heißen und wie viel LP sie haben."""
from __future__ import annotations

import threading
import time

from ..core.packets import PacketSource
from ..core.packets.messages import PartyHp, PartyList, PartyMember
from .signal import Signal
from .world import World

FRESH_S = 10  # so lange gilt eine Position (sie kommt etwa alle 2 s)


class PartyTracker:
    def __init__(self, world: World) -> None:
        self.world = world
        self.lock = threading.Lock()
        self.members: dict[int, tuple[float, float, float, float]] = {}  # Charakter-ID → x, y, z, Zeit
        self.names: dict[int, str] = {}  # Charakter-ID → Name
        self.hp = Signal[int, float]()  # (Entity eines Mitspielers, LP-Anteil 0–1)

    def attach(self, source: PacketSource) -> None:
        source.on(PartyMember, self._on_member)
        source.on(PartyList, self._on_list)
        source.on(PartyHp, self._on_hp)

    def visible(self) -> list[tuple[str, float, float, float, float]]:
        """(Name, x, y, z, Zeit) der Mitspieler mit frischer Position."""
        with self.lock:
            return [(self.names.get(cid, ""), *m) for cid, m in self.members.items() if time.time() - m[3] < FRESH_S]

    def _on_member(self, m: PartyMember) -> None:
        with self.lock:
            self.members[m.character_id] = (*m.position, time.time())

    def _on_list(self, m: PartyList) -> None:
        self.names.update(m.names)

    def _on_hp(self, m: PartyHp) -> None:
        if m.entity != self.world.own_id and m.maximum:
            self.hp.emit(m.entity, m.hp / m.maximum)
