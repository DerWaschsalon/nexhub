"""Effekte, die gerade auf dem Boss und auf dir liegen, aus dem Capture (für eigene Makros,
GET /api/radar/kampf).

Das Radar erkennt Status-Effekte auf dem Boss erst spät und zeigt sie mit fester Dauer (Lakshmis
Schadensreflexion am 04.11.2026: 3 s zu spät, 3,5 s zu lang). Das Capture (A2Tools-Kern) kennt Anfang
und Ende genau: Es sind dieselben Buff-Daten, die im NexLog stehen. Die eigenen Effekte (z. B. Präzision
vom Markierungsschuss) braucht ein Makro, um den Zielpfeil ins Buff-Fenster zu legen.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, Protocol

STILL_ON = 10  # end_code im A2Tools-Kern: der Abschnitt läuft beim letzten Treffer noch
FRISCH_S = 0.2  # Makros fragen alle 0,1 s; das Capture höchstens so oft fragen
# Das Capture rechnet bis zum letzten Treffer. Trifft so lange niemand mehr, gilt der Stand als veraltet
# (Lakshmis Reflexion dauert 8 s, in der Zeit greifen manche nicht an)
MAX_RUHE_S = 10.0
ABFRAGE_S = 1.0  # Zeitlimit je Befehl an das Capture


class Capture(Protocol):
    running: bool
    data_listeners: list

    async def request(self, cmd: str, timeout: float = 5, **args: Any) -> Any: ...


def aktive(daten: dict | None, jetzt_ms: float, auf: int | None) -> list[dict]:
    """Effekte auf `auf` (Ziel oder Spieler), deren letzter Abschnitt noch läuft, mit Sekunden seit Beginn."""
    if not daten or auf is None:
        return []
    kampf_start = daten.get("startTimeMs") or 0
    if jetzt_ms - kampf_start - (daten.get("durationMs") or 0) > MAX_RUHE_S * 1000:
        return []
    ergebnis = []
    for spur in daten.get("buffs") or []:
        if spur.get("on") != auf or not spur.get("segs"):
            continue
        start, _ende, _stapel, wie = spur["segs"].split(";")[-1].split(",")
        seit = (jetzt_ms - kampf_start - int(start)) / 1000
        if int(wie) == STILL_ON:
            ergebnis.append({"id": spur["id"], "seit": round(seit, 1)})
    return ergebnis


# eigene_effekte None = unbekannt (Capture aus, eigene ID noch nicht gesehen), [] = keine
LEER = {"boss_effekte": [], "eigene_effekte": None}


class BossEffekte:
    """Fragt das Capture nach dem aktuellen Ziel und den Effekten darauf und auf dir, kurz zwischengespeichert."""

    def __init__(self, capture: Capture, uhr: Callable[[], float] = time.time) -> None:
        self.capture = capture
        self.uhr = uhr
        self._stand: dict = LEER
        self._zeit = 0.0
        self.ich: int | None = None  # eigene Actor-ID, kommt mit jedem DPS-Stand des Captures
        capture.data_listeners.append(self._daten)

    async def _daten(self, art: str, inhalt: Any) -> None:
        if art == "dps" and isinstance(inhalt, dict) and inhalt.get("localPlayerId") is not None:
            self.ich = int(inhalt["localPlayerId"])

    async def aktuell(self) -> dict:
        if self.uhr() - self._zeit < FRISCH_S:
            return self._stand
        self._zeit = self.uhr()  # vor dem Warten setzen, damit gleichzeitige Anfragen nicht doppelt fragen
        try:
            self._stand = await self._abfragen()
        except (RuntimeError, TimeoutError, AttributeError, KeyError, ValueError):
            self._stand = LEER  # Capture aus oder Antwort unbekannt: keine Effekte, Makros laufen normal
        return self._stand

    async def _abfragen(self) -> dict:
        if not self.capture.running:
            return LEER
        kontext = await self.capture.request("context", timeout=ABFRAGE_S)
        ziel = (kontext or {}).get("currentTargetId")
        if not ziel:
            return LEER
        daten = await self.capture.request("buffs", timeout=ABFRAGE_S, target_id=ziel)
        jetzt_ms = self.uhr() * 1000
        eigene = aktive(daten, jetzt_ms, self.ich) if self.ich is not None else None
        return {"boss_effekte": aktive(daten, jetzt_ms, ziel), "eigene_effekte": eigene}
