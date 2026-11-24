"""Stagger-Leiste der Bosse: gebrochen = Boss groggy; bei Bossen mit Stagger-Prüfung dazu der Moment, in
dem die Leiste brechbar wird."""
from __future__ import annotations

import time

from ..core.packets import PacketSource
from ..core.packets.messages import Stagger
from .signal import Signal
from .world import World

GROGGY_MAX_S = 8.0  # kommt nach dem Brechen keine neue Leiste, gilt der Boss danach wieder als nicht groggy
LATE_S = 5.0  # erscheint die Leiste so lange nach dem Boss, ist es eine Stagger-Prüfung


class StaggerTracker:
    def __init__(self, world: World, check_bosses: set[int]) -> None:
        self.world = world
        self.check_bosses = check_bosses  # Boss-NPCs mit Stagger-Prüfung
        self.groggy_since: dict[int, float] = {}  # Boss-Entity → seit wann die Leiste gebrochen ist
        self.bar_ready: dict[int, bool] = {}  # Boss-Entity → war die Leiste zuletzt brechbar
        self.broken = Signal[int]()  # Boss-Entity, deren Leiste bricht
        self.ready = Signal[int]()  # Boss-Entity, deren Leiste brechbar wird

    def attach(self, source: PacketSource) -> None:
        source.on(Stagger, self._on_stagger)

    def groggy(self, now: float | None = None) -> bool:
        """Ist gerade ein Boss groggy? Für andere Programme, unabhängig davon, ob die Warnung angezeigt wird."""
        now = time.time() if now is None else now
        return any(now - since < GROGGY_MAX_S for since in self.groggy_since.values())

    def _on_stagger(self, m: Stagger) -> None:
        """Jede Leisten-Nachricht außer „gebrochen“ heißt, die Leiste läuft wieder, also ist groggy vorbei."""
        boss = m.entity
        if boss not in self.world.bosses:
            return
        if m.broken:
            self.groggy_since[boss] = time.time()
            self.bar_ready[boss] = False
            self.broken.emit(boss)
            return
        self.groggy_since.pop(boss, None)
        if self.world.bosses[boss] in self.check_bosses and m.ready is not None:
            self._check(boss, m.ready)

    def _check(self, boss: int, ready: bool) -> None:
        """Brechbar nach einer Pause oder eine Leiste, die erst später im Kampf erscheint = Prüfung. Eine
        Leiste, die von Anfang an brechbar ist, gehört zum Boss selbst (glass-cannon: Lakshmi)."""
        before = self.bar_ready.get(boss)
        self.bar_ready[boss] = ready
        late = time.time() - self.world.boss_since.get(boss, time.time()) >= LATE_S
        if ready and (before is False or (before is None and late)):
            self.ready.emit(boss)
