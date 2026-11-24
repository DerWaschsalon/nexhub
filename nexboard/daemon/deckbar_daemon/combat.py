"""Kampferkennung: Aus den Ständen des Meters wird „gerade im Kampf“ (State `dps_active`) und der Stand für
die Leiste (State `dps`). Beginn = der Gesamtschaden wächst, Ende = so lange kein neuer Schaden, wie
eingestellt. Am Kampfende bekommen `fight_listeners` den letzten Stand mit allen Zeilen (dps_view.fight_view),
z. B. für den eigenen Charakter im NexLog (hub.py).
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

from .dps_view import total_damage
from .state import State

log = logging.getLogger(__name__)

CombatListener = Callable[[bool], Awaitable[None]]
FightListener = Callable[[dict], Awaitable[None]]


class CombatTracker:
    def __init__(self, state: State, idle_after: Callable[[], int], on_combat: CombatListener | None = None) -> None:
        """idle_after: Sekunden ohne Schaden bis zum Kampfende (Einstellung, deshalb als Abfrage)."""
        self.state = state
        self.idle_after = idle_after
        self.on_combat = on_combat
        self.fight_listeners: list[FightListener] = []
        self.fight: dict | None = None
        self._pending: set[asyncio.Task] = set()
        self._last_total = 0
        self._last_change = 0.0

    async def apply(self, value: dict | None, baseline: bool = False, fight: dict | None = None) -> None:
        """Neuer Stand vom Meter; erkennt Kampfbeginn am wachsenden Gesamtschaden.
        baseline: erster Stand nach dem Verbinden – ein alter Kampf zählt nicht als Beginn.
        fight: derselbe Stand als fight_view (alle Zeilen), wird zum Endstand des Kampfs."""
        was_active = bool(self.state.values.get("dps_active"))
        if fight and fight["rows"] and not baseline:
            self.fight = fight
        total = total_damage(value)
        # Schaden kam hinzu (auch: Meter hat zurückgesetzt und ein neuer Kampf läuft)
        hit = total > 0 and total != self._last_total and not baseline
        if hit:
            self._last_change = time.monotonic()
        self._last_total = total
        active = value is not None and (was_active or hit)
        self.state.update(dps=value, dps_active=active)
        if active != was_active:
            await self._combat(active)

    async def check_idle(self) -> None:
        if self.state.values.get("dps_active") and time.monotonic() - self._last_change >= self.idle_after():
            self.state.update(dps_active=False)
            await self._combat(False)

    async def _combat(self, active: bool) -> None:
        if self.on_combat:
            await self.on_combat(active)
        if active:
            return
        fight, self.fight = self.fight, None
        if fight:
            # entkoppelt: ein langsamer Zuhörer (Netz, bis 20 s) darf den Feed nicht anhalten
            for fn in self.fight_listeners:
                t = asyncio.ensure_future(self._notify_fight(fn, fight))
                self._pending.add(t)
                t.add_done_callback(self._pending.discard)

    @staticmethod
    async def _notify_fight(fn: FightListener, fight: dict) -> None:
        try:
            await fn(fight)
        except Exception:
            log.exception("Kampfende-Zuhörer")
