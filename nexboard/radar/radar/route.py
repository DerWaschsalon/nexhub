"""Cube-Route: kuerzester Rundweg durch bekannte Cube-Fundorte, mit Fortschritt.

Die Fundorte (z.B. von aion2hub) sind Hotspots, keine sicheren Spawns: Meist liegt dort gerade
nichts. Ein Punkt gilt deshalb als erledigt, sobald man nah genug dran war, egal ob ein Cube da war.

Die Punkte stehen in Kartenbild-Pixeln, nicht in Weltkoordinaten: So bleiben sie richtig, wenn die
Karte spaeter genauer geeicht wird.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

Punkt = tuple[float, float]


def rundweg(punkte: list[Punkt]) -> list[int]:
    """Reihenfolge eines kurzen Rundwegs: naechster Nachbar, danach Kreuzungen aufloesen (2-opt)."""
    if not punkte:
        return []
    weg = [0]
    rest = set(range(1, len(punkte)))
    while rest:
        letzter = punkte[weg[-1]]
        naechster = min(rest, key=lambda i: math.dist(letzter, punkte[i]))
        weg.append(naechster)
        rest.remove(naechster)

    def d(a: int, b: int) -> float:
        return math.dist(punkte[weg[a % len(weg)]], punkte[weg[b % len(weg)]])

    besser = True
    while besser:
        besser = False
        for i in range(1, len(weg) - 1):
            for j in range(i + 1, len(weg)):
                # Kanten (i-1, i) und (j, j+1) gegen (i-1, j) und (i, j+1) tauschen
                if d(i - 1, i) + d(j, j + 1) > d(i - 1, j) + d(i, j + 1) + 1e-6:
                    weg[i:j + 1] = reversed(weg[i:j + 1])
                    besser = True
    return weg


class Route:
    """route.json: "punkte" in Rundweg-Reihenfolge, "offen" = noch nicht besuchte Indizes in der
    Reihenfolge, in der sie dran sind (None = Runde noch nicht gestartet)."""

    def __init__(self, datei: Path) -> None:
        self.datei = datei
        try:
            daten = json.loads(datei.read_text())
        except (OSError, ValueError):
            daten = {}
        self.punkte: list[Punkt] = [tuple(p) for p in daten.get("punkte", [])]
        self.offen: list[int] | None = daten.get("offen")

    @staticmethod
    def anlegen(datei: Path, punkte: list[Punkt]) -> None:
        reihenfolge = [list(punkte[i]) for i in rundweg(punkte)]
        datei.parent.mkdir(parents=True, exist_ok=True)
        datei.write_text(json.dumps({"punkte": reihenfolge, "offen": None}))

    @property
    def da(self) -> bool:
        return bool(self.punkte)

    @property
    def uebrig(self) -> int:
        return len(self.punkte) if self.offen is None else len(self.offen)

    def offene(self) -> list[Punkt]:
        """Noch nicht besuchte Punkte in Reihenfolge (vor dem Start alle)."""
        if self.offen is None:
            return list(self.punkte)
        return [self.punkte[i] for i in self.offen]

    def naechste(self, anzahl: int = 3) -> list[Punkt]:
        if self.offen is None:
            return []
        return self.offene()[:anzahl]

    def position(self, ich: Punkt, abstand: float) -> None:
        """Eigene Position melden: startet die Runde am naechsten Punkt und hakt ab, was in
        Reichweite liegt (auch Punkte, die erst spaeter dran waeren)."""
        if not self.punkte:
            return
        geaendert = False
        if self.offen is None:
            start = min(range(len(self.punkte)), key=lambda i: math.dist(ich, self.punkte[i]))
            self.offen = [(start + k) % len(self.punkte) for k in range(len(self.punkte))]
            geaendert = True
        nah = [i for i in self.offen if math.dist(ich, self.punkte[i]) <= abstand]
        for i in nah:
            self.offen.remove(i)
        if geaendert or nah:
            self._speichern()

    def ueberspringen(self) -> None:
        if self.offen:
            self.offen.pop(0)
            self._speichern()

    def neu_starten(self) -> None:
        self.offen = None
        self._speichern()

    def _speichern(self) -> None:
        tmp = self.datei.with_suffix(".tmp")
        tmp.write_text(json.dumps({"punkte": [list(p) for p in self.punkte], "offen": self.offen}))
        tmp.replace(self.datei)
