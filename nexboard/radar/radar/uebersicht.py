"""Feldbosse: Respawn-Timer und Ansagen (auch für den Riss). Angezeigt auf der NexBoard-Seite „Termine“,
angesagt vom RadarDienst. Die Termine selbst rechnet nexproto.termine."""
from __future__ import annotations

import time

from nexproto.termine import TERMINE, termin

from .daten import npc_name
from .konfig import konfig_laden
from .warnung import ansage, tr

VERMUTLICH_DA = 2 * 3600  # so lange nach dem Respawn gilt ein Feldboss als "vermutlich da"
GRUEN, ORANGE, GRAU = "ok", "warn", "leise"  # Farbklassen der NexBoard-Seite


def riss(jetzt: float) -> tuple[float, bool]:
    return termin(jetzt, *TERMINE[0][1:])


def feldboss_name(platz: str, boss: dict) -> str:
    return npc_name(boss["npc"], konfig_laden()["sprache"]) if boss.get("npc") else \
        f"{tr('Feldboss')} {int(platz) % 100}"


def feldboss_text(boss: dict, jetzt: float) -> tuple[str, str, float]:
    """(Anzeige, Farbe, Sekunden bis Respawn) fuer einen Feldboss-Platz."""
    rest = boss["zeit"] - jetzt
    if boss["lebt"]:
        return tr("lebt"), GRUEN, 0
    if rest > 0:
        return f"{tr('in')} {int(rest // 3600)}:{int(rest % 3600 // 60):02}:{int(rest % 60):02}", ORANGE, rest
    if boss["zeit"] and -rest < VERMUTLICH_DA:
        return tr("vermutlich da"), GRUEN, 0
    return tr("unbekannt"), GRAU, 1e9


def feldboss_ansagen(zustand, gemeldet: set) -> None:
    """Ansage 5 Minuten vor dem Respawn und beim Respawn, nur fuer die aktuelle Karte."""
    if not konfig_laden()["feldboss_ansage"]:
        return
    jetzt = time.time()
    beginn, _ = riss(jetzt)
    for grenze, satz in ((300, " in 5 Minuten"), (0, " ist offen")):
        if beginn - jetzt <= grenze and ("riss", beginn, grenze) not in gemeldet:
            gemeldet.add(("riss", beginn, grenze))
            if beginn - jetzt > grenze - 30:
                ansage(tr("Riss") + tr(satz))
    for platz, boss in list(zustand.feldbosse.items()):
        rest = boss["zeit"] - jetzt
        if boss["karte"] != zustand.zone or boss["lebt"] or rest < -10:
            continue
        for grenze, satz in ((300, " in 5 Minuten"), (0, " ist da")):
            schluessel = (platz, boss["zeit"], grenze)
            if rest <= grenze and schluessel not in gemeldet:
                gemeldet.add(schluessel)
                if rest > grenze - 30:  # nicht nachtraeglich, z.B. nach dem Einloggen
                    ansage(feldboss_name(platz, boss) + tr(satz))


def feldbosse(plaetze: dict[str, dict], zone: int | None) -> list[dict]:
    """Alle bekannten Feldboss-Plaetze, die der aktuellen Karte (zone) zuerst, dann nach Respawn."""
    jetzt, zeilen = time.time(), []
    for platz, boss in plaetze.items():
        text, farbe, rest = feldboss_text(boss, jetzt)
        hier = boss["karte"] == zone
        zeilen.append((not hier, rest, {"name": feldboss_name(platz, boss), "karte": boss["karte"],
                                        "status": text, "farbe": farbe, "hier": hier}))
    return [z for *_, z in sorted(zeilen, key=lambda z: z[:2])]

