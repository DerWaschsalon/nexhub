"""Spielerkennung mit Nachlauf: meldet auf dem Bus, wann ein Spiel startet und endet.

Eine Stelle statt vier Schleifen mit eigenem /proc-Scan. Was „läuft“ heißt, entscheidet der Aufrufer
(Fachlogik, z. B. die AION-2-Prozessnamen); hier stecken nur Takt und Nachlauf.
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

from .bus import EventBus

POLL_S = 5.0
GRACE_S = 20.0  # so lange darf das Spiel fehlen (Neustart, Ladebildschirm), bevor es als beendet gilt


class GameWatch:
    def __init__(self, bus: EventBus, name: str, is_running: Callable[[], bool],
                 poll_s: float = POLL_S, grace_s: float = GRACE_S) -> None:
        self.bus = bus
        self.name = name  # Themen: game.started / game.stopped mit diesem Namen als Inhalt
        self.is_running = is_running
        self.poll_s = poll_s
        self.grace_s = grace_s
        self.running = False
        self._last_seen = 0.0

    async def check(self) -> None:
        """Einmal nachsehen und bei einem Wechsel melden."""
        seen = await asyncio.to_thread(self.is_running)
        now = time.monotonic()
        if seen:
            self._last_seen = now
        running = seen or (self.running and now - self._last_seen < self.grace_s)
        if running != self.running:
            self.running = running
            await self.bus.emit("game.started" if running else "game.stopped", self.name)

    async def run(self) -> None:
        while True:
            await self.check()
            await asyncio.sleep(self.poll_s)
