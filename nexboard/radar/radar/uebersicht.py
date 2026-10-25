"""Feldbosse und Vertraute: Respawn-Timer der Feldbosse, Riss-Zeitplan und Seelen-Stand der Vertrauten.
Angezeigt auf der NexBoard-Seite des Radars, angesagt vom RadarDienst."""
from __future__ import annotations

import time
from datetime import datetime, timezone

from .daten import VERTRAUTE, npc_name
from .konfig import konfig_laden
from .warnung import ansage, tr

VERMUTLICH_DA = 2 * 3600  # so lange nach dem Respawn gilt ein Feldboss als "vermutlich da"
GRUEN, ORANGE, GRAU = "ok", "warn", "leise"  # Farbklassen der NexBoard-Seite
SEELEN = (5, 25, 75)  # Seelen fuer Stufe 1, 2 und 3 (MAX), 105 insgesamt (laut aion2pettracker, passt zum Mitschnitt)


# Feste Termine der globalen Server (EU/NA) aus jackships/aion2-data: (Name, Bezugszeit UTC, alle Minuten,
# offen Minuten). In UTC, damit die Zeitumstellung nichts verschiebt. Nur der Riss ist dort "confirmed".
TERMINE = [
    ("Riss", "2026-10-07 00:00", 180, 10),
    ("Shugo-Fest", "2026-10-07 00:00", 60, 10),
    ("Beritra-Luftangriff", "2026-10-07 00:30", 60, 10),
    ("Wächterin Kaira", "2026-10-07 01:00", 180, 30),
    ("Tages-Reset", "2026-10-07 07:00", 1440, 1),
    ("Wochen-Reset", "2026-10-07 07:00", 10080, 1),  # Mittwoch
]


def termin(jetzt: float, bezug: str, alle: int, offen: int) -> tuple[float, bool]:
    """(Beginn des naechsten oder laufenden Termins, gerade offen?)."""
    start = datetime.fromisoformat(bezug).replace(tzinfo=timezone.utc).timestamp()
    beginn = start + -(-(jetzt - start) // (alle * 60)) * alle * 60  # naechster Beginn ab jetzt
    if jetzt < beginn - alle * 60 + offen * 60:
        return beginn - alle * 60, True
    return beginn, False


def riss(jetzt: float) -> tuple[float, bool]:
    return termin(jetzt, *TERMINE[0][1:])


def fehlende_seelen(stufe: int, seelen: int) -> tuple[int, int]:
    """(Seelen bis zur naechsten Stufe, Seelen bis MAX)."""
    if stufe >= 3:
        return 0, 0
    naechste = SEELEN[stufe] - seelen
    return naechste, naechste + sum(SEELEN[stufe + 1:])


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


def termine(jetzt: float) -> list[dict]:
    """Feste Termine: Name, Beginn (Sekunden seit 1970), offen bis (nur wenn gerade offen)."""
    zeilen = []
    for name, bezug, alle, dauer in TERMINE:
        beginn, offen = termin(jetzt, bezug, alle, dauer)
        zeilen.append({"name": tr(name), "beginn": beginn, "offen_bis": beginn + dauer * 60 if offen else None})
    return zeilen


def feldbosse(plaetze: dict[str, dict], zone: int | None) -> list[dict]:
    """Alle bekannten Feldboss-Plaetze, die der aktuellen Karte (zone) zuerst, dann nach Respawn."""
    jetzt, zeilen = time.time(), []
    for platz, boss in plaetze.items():
        text, farbe, rest = feldboss_text(boss, jetzt)
        hier = boss["karte"] == zone
        zeilen.append((not hier, rest, {"name": feldboss_name(platz, boss), "karte": boss["karte"],
                                        "status": text, "farbe": farbe, "hier": hier}))
    return [z for *_, z in sorted(zeilen, key=lambda z: z[:2])]


def vertraute(stand: dict[str, list[int]]) -> list[dict]:
    """Jeder Vertraute mit Stufe, Seelen, was zur naechsten Stufe fehlt und wo man ihn farmt."""
    sprache, zeilen = konfig_laden()["sprache"], []
    for vid, v in VERTRAUTE.items():
        stufe, seelen = stand.get(vid, [0, 0])
        monster = list(dict.fromkeys(npc_name(m, sprache) or "?" for m in v["monster"]))
        zeilen.append({"name": v[sprache], "art": tr(v["art"]), "stufe": stufe, "seelen": seelen,
                       "fehlen": fehlende_seelen(stufe, seelen)[0], "angefangen": vid in stand,
                       "bis_max": fehlende_seelen(stufe, seelen)[1], "wo": monster + v["orte"]})
    return zeilen
