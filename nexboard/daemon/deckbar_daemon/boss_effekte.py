"""Effekte, die gerade auf dem Boss liegen, aus dem Capture (für eigene Makros, GET /api/radar/kampf).

Das Radar erkennt Status-Effekte auf dem Boss erst spät und zeigt sie mit fester Dauer (Lakshmis
Schadensreflexion am 04.11.2026: 3 s zu spät, 3,5 s zu lang). Das Capture (A2Tools-Kern) kennt Anfang
und Ende genau: Es sind dieselben Buff-Daten, die im NexLog stehen.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, Protocol

STILL_ON = 10  # end_code im A2Tools-Kern: der Abschnitt läuft beim letzten Treffer noch
FRISCH_S = 0.2  # Makros fragen alle 0,1 s; das Capture höchstens so oft fragen
MAX_S = 15.0  # länger offen heißt: niemand trifft mehr, das Fenster des Captures steht still
ABFRAGE_S = 1.0  # Zeitlimit je Befehl an das Capture


class Capture(Protocol):
    running: bool

    async def request(self, cmd: str, timeout: float = 5, **args: Any) -> Any: ...


def aktive(daten: dict | None, jetzt_ms: float) -> list[dict]:
    """Effekte auf dem Ziel, deren letzter Abschnitt noch läuft, mit Sekunden seit Beginn."""
    if not daten:
        return []
    ziel, kampf_start = daten.get("targetId"), daten.get("startTimeMs") or 0
    ergebnis = []
    for spur in daten.get("buffs") or []:
        if spur.get("on") != ziel or not spur.get("segs"):
            continue
        start, _ende, _stapel, wie = spur["segs"].split(";")[-1].split(",")
        seit = (jetzt_ms - kampf_start - int(start)) / 1000
        if int(wie) == STILL_ON and seit <= MAX_S:
            ergebnis.append({"id": spur["id"], "seit": round(seit, 1)})
    return ergebnis


class BossEffekte:
    """Fragt das Capture nach dem aktuellen Ziel und dessen Effekten, kurz zwischengespeichert."""

    def __init__(self, capture: Capture, uhr: Callable[[], float] = time.time) -> None:
        self.capture = capture
        self.uhr = uhr
        self._stand: list[dict] = []
        self._zeit = 0.0

    async def aktuell(self) -> list[dict]:
        if self.uhr() - self._zeit < FRISCH_S:
            return self._stand
        self._zeit = self.uhr()  # vor dem Warten setzen, damit gleichzeitige Anfragen nicht doppelt fragen
        try:
            self._stand = await self._abfragen()
        except (RuntimeError, TimeoutError, AttributeError, KeyError, ValueError):
            self._stand = []  # Capture aus oder Antwort unbekannt: keine Effekte, Makros laufen normal
        return self._stand

    async def _abfragen(self) -> list[dict]:
        if not self.capture.running:
            return []
        kontext = await self.capture.request("context", timeout=ABFRAGE_S)
        ziel = (kontext or {}).get("currentTargetId")
        if not ziel:
            return []
        daten = await self.capture.request("buffs", timeout=ABFRAGE_S, target_id=ziel)
        return aktive(daten, self.uhr() * 1000)
