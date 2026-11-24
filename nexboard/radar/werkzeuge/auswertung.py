"""Wertet Kaempfe aus: Mitschnitt + Kampfdateien des DPS-Meters (A2Tools/DeckBar).

Pro Kampf: Boss, Dauer, eigene DPS, jeder eigene Tod mit Ursache und mit der
Warnung, die das Radar zu dem Zeitpunkt gezeigt haette. Am Ende: wie frueh
die Teufelsflamme angekuendigt wurde.

Aufruf: python -m werkzeuge.auswertung mitschnitte/datei.pcap [--name <Charakter>]
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from deckbar_daemon.aion2.cast_trainer import CastTrainer
from deckbar_daemon.aion2.fight import FightEvents
from deckbar_daemon.aion2.gamedata import a2tools_data_dir
from deckbar_daemon.aion2.mechanic_warnings import MechanicWarnings
from deckbar_daemon.aion2.warning_board import WarningBoard
from deckbar_daemon.aion2.world import World
from deckbar_daemon.core.packets import PcapSource, server_segments
from deckbar_daemon.core.packets.messages import Hit, Vitals

KAEMPFE = Path.home() / ".local/share/deckbar/aion2/history"
SKILLNAMEN = a2tools_data_dir() / "i18n" / "skills" / "de.json"
TEUFELSFLAMME = 1801120


def kaempfe_laden(name: str, von: float, bis: float) -> list[dict]:
    """Kampfdateien des DPS-Meters, die in den Zeitraum des Mitschnitts fallen."""
    liste = []
    for f in KAEMPFE.glob("*.json"):
        d = json.loads(f.read_text())
        start = d["startTimeMs"] / 1000
        ich = [a["actorId"] for a in d["actors"] if a["nickname"] == name]
        if von <= start <= bis and ich:
            schaden = sum(s["dmg"] for s in d["details"]["skills"] if s["actorId"] == ich[0])
            liste.append({"boss": d["targetId"], "name": d["bossName"], "start": start,
                          "ende": start + d["durationMs"] / 1000, "ich": ich[0],
                          "dps": schaden / (d["durationMs"] / 1000)})
    return sorted(liste, key=lambda k: k["start"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pcap")
    ap.add_argument("--name", default="")
    a = ap.parse_args()
    skillname = json.loads(SKILLNAMEN.read_text()) if SKILLNAMEN.exists() else {}
    skillname["1801116"] = "Regen des Hasses"  # die Ticks haben keinen eigenen Namen

    # Mitschnitt einmal durch Welt und Warn-Anzeige laufen lassen
    uhr = [0.0]
    quelle, welt = PcapSource(), World(a.name)
    kampf = FightEvents(welt)
    tafel = WarningBoard(welt, clock=lambda: uhr[0])
    tafel.enabled = True
    MechanicWarnings(tafel, kampf)
    CastTrainer(tafel, kampf)
    welt.attach(quelle)
    kampf.attach(quelle)
    hp = defaultdict(list)        # entity -> [(zeit, hp)]
    treffer = defaultdict(list)   # ziel -> [(zeit, angreifer, skill)]
    warnungen = []                # [(zeit, [(titel, seit)])]
    quelle.on(Vitals, lambda m: m.hp is not None and hp[m.entity].append((uhr[0], m.hp)))
    quelle.on(Hit, lambda m: treffer[m.entity].append((uhr[0], m.attacker, m.skill)))
    von = None
    with open(a.pcap, "rb") as f:
        for zeit, segment in server_segments(f):
            von = von or zeit
            uhr[0] = zeit
            quelle.feed(*segment)
            warnungen.append((zeit, [(w.rule.title, w.since) for w in tafel.snapshot()]))

    vorwarnung = []
    ursachen = Counter()
    for k in kaempfe_laden(a.name, von, uhr[0]):
        print(f"{datetime.fromtimestamp(k['start']):%H:%M}  {k['name']:20} "
              f"{k['ende'] - k['start']:4.0f} s   {k['dps']:7,.0f} DPS")
        im_kampf = lambda t: k["start"] <= t <= k["ende"] + 1  # noqa: E731
        # eigene Tode: HP faellt auf 0
        werte = [(t, v) for t, v in hp[k["ich"]] if im_kampf(t)]
        for (_, vorher), (t, v) in zip(werte, werte[1:]):
            if v or not vorher:
                continue
            letzte = Counter(skillname.get(str(s), str(s)) for tt, an, s in treffer[k["ich"]]
                             if an == k["boss"] and 0 <= t - tt <= 3)
            ursache = letzte.most_common(1)[0][0] if letzte else "unklar"
            ursachen[ursache] += 1
            stand = next((w for z, w in warnungen if z >= t - 3), [])
            warn = ", ".join(f"{titel} ({t - seit:.0f} s vorher)" for titel, seit in stand) or "-"
            print(f"      Tod nach {t - k['start']:4.0f} s: {ursache:22}  Warnung: {warn}")
        # wie frueh kam die Warnung vor jeder Teufelsflamme?
        flammen = sorted({round(t, 1) for z in treffer.values() for t, an, s in z
                          if s == TEUFELSFLAMME and an == k["boss"] and im_kampf(t)})
        for t in [t for i, t in enumerate(flammen) if i == 0 or t - flammen[i - 1] > 3]:
            stand = next((w for z, w in warnungen if z >= t - 0.1), [])
            seit = [s for titel, s in stand if "Flamme" in titel or "Todesmal" in titel]
            vorwarnung.append(round(t - min(seit), 1) if seit else 0.0)

    print("\nTode nach Ursache:", dict(ursachen.most_common()))
    print("Vorwarnung vor jeder Teufelsflamme (s):", sorted(vorwarnung))


if __name__ == "__main__":
    main()
