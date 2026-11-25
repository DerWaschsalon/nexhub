"""Effekte, die gerade auf dem Boss und auf dir liegen, aus dem Mitschnitt der Kampfdaten (für andere
Programme auf diesem PC, GET /api/m/aion2.effects).

Das Radar erkennt Status-Effekte auf dem Boss erst spät und zeigt sie mit fester Dauer (Lakshmis
Schadensreflexion am 04.11.2026: 3 s zu spät, 3,5 s zu lang). Der Mitschnitt (A2Tools-Kern) kennt Anfang
und Ende genau: Es sind dieselben Buff-Daten, die im NexLog stehen. Dazu die eigenen Effekte (z. B. Präzision
vom Markierungsschuss). Die Schlüssel der Antwort legt der Mitschnitt fest (capture/src/effects.rs).
"""
from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, Protocol

FRESH_S = 0.2  # Abfragen kommen bis zu alle 0,1 s; den Mitschnitt höchstens so oft fragen
REQUEST_S = 1.0  # Zeitlimit je Befehl an den Mitschnitt
# eigene_effekte None = unbekannt (Mitschnitt aus, eigene ID noch nicht gesehen), [] = keine
EMPTY: dict[str, Any] = {"boss_effekte": [], "eigene_effekte": None}


class Capture(Protocol):
    running: bool

    async def request(self, cmd: str, timeout: float = 5, **args: Any) -> Any: ...


class ActiveEffects:
    """Fragt den Mitschnitt nach den laufenden Effekten auf dem Ziel und auf dir, kurz zwischengespeichert.
    Welche laufen, rechnet der Mitschnitt selbst."""

    def __init__(self, capture: Capture, clock: Callable[[], float] = time.time) -> None:
        self.capture = capture
        self.clock = clock
        self._state = EMPTY
        self._asked = 0.0

    async def current(self) -> dict[str, Any]:
        if self.clock() - self._asked < FRESH_S:
            return self._state
        self._asked = self.clock()  # vor dem Warten setzen, damit gleichzeitige Anfragen nicht doppelt fragen
        self._state = await self._ask()
        return self._state

    async def _ask(self) -> dict[str, Any]:
        if not self.capture.running:
            return EMPTY
        try:
            return await self.capture.request("active_effects", timeout=REQUEST_S) or EMPTY
        except (RuntimeError, TimeoutError):
            return EMPTY  # Mitschnitt aus oder Antwort unbekannt: keine Effekte
