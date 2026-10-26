"""PvP der laufenden Sitzung: Kills und Tode live, Abyss-Rangpunkte, Rang und K/D/A aus der Saisonwertung.

Opcodes (Namen wie im Desktop-Programm von questlog.gg, Formate an eigenen Mitschnitten geprueft):
  0x8D04 CharDie_NT: Tod. Opfer (Varint), Skill u32, Taeter (Varint), Server u16, Name des Taeters, ...
         Name und Taeter stehen nur drin, wenn ein Spieler getoetet hat.
  0x8D57 eigene Saisonwertung: Rang, Punkte, Grad und JSON mit kill_count/death_count/assist_count.
         Kommt beim Einloggen und nach manchen Zonenwechseln; der Server rechnet etwa stuendlich neu,
         die Werte daraus hinken also hinterher.
Die Sitzung beginnt, wenn das Radar mit dem Spiel startet, oder mit zuruecksetzen().
"""
from __future__ import annotations

import json
import time
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .protokoll import Leser

if TYPE_CHECKING:
    from .zustand import RadarZustand

OP_TOD = 0x8D04
OP_SAISON = 0x8D57
OPCODES = (OP_TOD, OP_SAISON)
ABYSS = 1  # Art der Wertung in 0x8D57
GRADE = {1: "Oberbefehlshaber", 2: "Kommandant", 3: "Großgeneral", 4: "General", 19: "Rekrut"}


def grad_name(grad: int) -> str:
    """Abyss-Rang zum Grad (1 = hoechster): 5-9 Offiziere mit Sternen, 10-18 Soldaten Rang 1-9."""
    if grad in GRADE:
        return GRADE[grad]
    if 5 <= grad <= 9:
        return f"{10 - grad}-Sterne-Offizier"
    if 10 <= grad <= 18:
        return f"Soldat Rang {grad - 9}"
    return ""


@dataclass(frozen=True)
class Saison:
    rang: int
    punkte: int
    grad: int
    kills: int
    tode: int
    assists: int
    zeit: float  # wann sie ankam

    @classmethod
    def lesen(cls, p: bytes) -> Saison | None:
        r = Leser(p)
        ergebnis, art = r.u16(), r.u8()
        if ergebnis or art != ABYSS:
            return None
        r.u8()  # Klasse, nach der gewertet wird (0 = alle)
        rang = r.i32()
        # uebersprungen: Charakter-ID, Name, Gilde, Wappen, Stufe, Eroberer-Stufe, Klasse
        for ueberspringen in (r.i64, r.text, r.text, r.u16, r.i32, r.i32, r.u8):
            ueberspringen()
        punkte = r.i64()
        zusatz = json.loads(r.text() or "{}")
        r.i32()  # Rangaenderung zur letzten Berechnung
        r.i32()  # Rang der Vorsaison
        grad = r.i32()
        return cls(rang, punkte, grad, zusatz.get("kill_count", 0), zusatz.get("death_count", 0),
                   zusatz.get("assist_count", 0), time.time())


class PvpSitzung:
    def __init__(self, zustand: RadarZustand) -> None:
        self.zustand = zustand  # eigene Entity, eigener Name, Spieler in Sicht
        self.saison: Saison | None = None
        self.zuruecksetzen()

    def zuruecksetzen(self) -> None:
        self.beginn = time.time()
        self.kills = 0
        self.tode = 0
        self.start = self.saison  # Vergleichswert fuer Punkte und Rang
        self.letzte: deque[tuple[str, str]] = deque(maxlen=3)  # ("kill", Opfer) oder ("tod", Taeter)

    def verarbeiten(self, op: int, p: bytes) -> None:
        if op == OP_TOD:
            self._tod(p)
        elif op == OP_SAISON:
            saison = Saison.lesen(p)
            if saison:
                self.saison = saison
                self.start = self.start or saison

    def _tod(self, p: bytes) -> None:
        r = Leser(p)
        opfer = r.varint()
        r.i32()  # Skill
        taeter = r.varint()
        r.u16()  # Server des Taeters
        name = r.text()
        if not name:
            return  # kein Spieler als Taeter: zaehlt nicht als PvP
        z = self.zustand
        if opfer == z.eigene_eid:
            self.tode += 1
            self.letzte.appendleft(("tod", name))
        elif opfer in z.spieler and (taeter == z.eigene_eid or name == z.charname):
            self.kills += 1
            self.letzte.appendleft(("kill", z.spieler[opfer]))

    def stand(self) -> dict:
        """Live gezaehlte Kills/Tode, sobald die Saisonwertung mehr kennt (z.B. Kills eines Begleiters)
        deren Zuwachs. Assists gibt es nur aus der Wertung."""
        s, a = self.saison, self.start
        if not s or not a:
            return {"kills": self.kills, "tode": self.tode, "assists": None, "punkte": None, "rang": None,
                    "beginn": self.beginn, "letzte": list(self.letzte)}
        return {"kills": max(self.kills, s.kills - a.kills), "tode": max(self.tode, s.tode - a.tode),
                "assists": s.assists - a.assists, "punkte": s.punkte - a.punkte, "punkte_saison": s.punkte,
                "rang": s.rang, "rang_plus": a.rang - s.rang, "grad": grad_name(s.grad), "stand": s.zeit,
                "beginn": self.beginn, "letzte": list(self.letzte)}
