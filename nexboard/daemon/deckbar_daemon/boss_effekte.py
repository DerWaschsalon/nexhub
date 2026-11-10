"""Effekte, die gerade auf dem Boss und auf dir liegen, aus dem Capture (für andere Programme
auf diesem PC, GET /api/radar/kampf).

Das Radar erkennt Status-Effekte auf dem Boss erst spät und zeigt sie mit fester Dauer (Lakshmis
Schadensreflexion am 04.11.2026: 3 s zu spät, 3,5 s zu lang). Das Capture (A2Tools-Kern) kennt Anfang
und Ende genau: Es sind dieselben Buff-Daten, die im NexLog stehen. Dazu die eigenen Effekte (z. B. Präzision
vom Markierungsschuss).
"""
from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, Protocol

FRISCH_S = 0.2  # Abfragen kommen bis zu alle 0,1 s; das Capture höchstens so oft fragen
ABFRAGE_S = 1.0  # Zeitlimit je Befehl an das Capture
# eigene_effekte None = unbekannt (Capture aus, eigene ID noch nicht gesehen), [] = keine
LEER = {"boss_effekte": [], "eigene_effekte": None}


class Capture(Protocol):
    running: bool

    async def request(self, cmd: str, timeout: float = 5, **args: Any) -> Any: ...


class BossEffekte:
    """Fragt das Capture nach den laufenden Effekten auf dem Ziel und auf dir, kurz zwischengespeichert.
    Welche laufen, rechnet das Capture selbst (capture/src/effects.rs)."""

    def __init__(self, capture: Capture, uhr: Callable[[], float] = time.time) -> None:
        self.capture = capture
        self.uhr = uhr
        self._stand: dict = LEER
        self._zeit = 0.0

    async def aktuell(self) -> dict:
        if self.uhr() - self._zeit < FRISCH_S:
            return self._stand
        self._zeit = self.uhr()  # vor dem Warten setzen, damit gleichzeitige Anfragen nicht doppelt fragen
        if not self.capture.running:
            self._stand = LEER
            return self._stand
        try:
            self._stand = await self.capture.request("active_effects", timeout=ABFRAGE_S) or LEER
        except (RuntimeError, TimeoutError):
            self._stand = LEER  # Capture aus oder Antwort unbekannt: keine Effekte
        return self._stand
