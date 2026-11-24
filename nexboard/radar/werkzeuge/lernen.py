"""Lernmodus: wertet eine Dungeon-Aufnahme aus, damit neue Warnungen entstehen koennen.

Pro Boss jeder Skill mit: wie oft gecastet, wann der erste Treffer kommt (= Vorlauf
fuer die Warnung), wie viele Spieler daran gestorben sind und welcher andere Cast
regelmaessig davor kommt (moegliche fruehere Vorwarnung, wie Todesmal vor Teufelsflamme).

Aufruf: python -m werkzeuge.lernen mitschnitte/<datei>.pcap
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

from deckbar_daemon.aion2.gamedata import BOSSES
from deckbar_daemon.core.packets import PcapSource, server_segments
from deckbar_daemon.core.packets.messages import Cast, Hit, NpcSeen, Vitals

NAMEN = Path("/usr/lib/A2Tools DPS Meter/data/i18n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pcap")
    a = ap.parse_args()
    skillname = json.loads((NAMEN / "skills/de.json").read_text())
    npcname = {k: v["name"] for k, v in json.loads((NAMEN / "npcs/de.json").read_text()).items()}

    # Aufnahme einmal durchlesen und Boss-Casts, Treffer und Tode sammeln
    uhr = [0.0]
    boss_von: dict[int, int] = {}                 # Entity -> Boss-NPC-ID
    casts = defaultdict(list)                     # Boss-Entity -> [(zeit, skill)]
    treffer = defaultdict(list)                   # (Boss-Entity, skill) -> [zeit]
    letzter_treffer: dict[int, tuple[int, int]] = {}  # Ziel -> (Boss-Entity, skill)
    hp: dict[int, int] = {}
    tode = Counter()                              # (Boss-Entity, skill) -> Anzahl

    def boss(m: NpcSeen) -> None:
        if m.npc in BOSSES:
            boss_von[m.entity] = m.npc

    def cast(m: Cast) -> None:
        if m.entity in boss_von and m.skill is not None:
            casts[m.entity].append((uhr[0], m.skill))

    def getroffen(m: Hit) -> None:
        if m.attacker in boss_von:
            treffer[(m.attacker, m.skill)].append(uhr[0])
            letzter_treffer[m.entity] = (m.attacker, m.skill)

    def punkte(m: Vitals) -> None:
        if m.hp is None:
            return
        if m.hp == 0 and hp.get(m.entity) and m.entity in letzter_treffer:
            tode[letzter_treffer[m.entity]] += 1
        hp[m.entity] = m.hp

    quelle = PcapSource()
    for nachricht, abnehmer in ((NpcSeen, boss), (Cast, cast), (Hit, getroffen), (Vitals, punkte)):
        quelle.on(nachricht, abnehmer)
    with open(a.pcap, "rb") as f:
        for zeit, segment in server_segments(f):
            uhr[0] = zeit
            quelle.feed(*segment)

    for eid, npc in boss_von.items():
        liste = casts[eid]
        if not liste:
            continue
        print(f"\n{npcname.get(str(npc), npc)} ({BOSSES[npc]}), {len(liste)} Casts")
        print(f"  {'Skill':9} {'Name':28} {'Casts':>5} {'Treffer nach':>12} {'Tode':>4}  davor")
        for skill, anzahl in Counter(s for _, s in liste).most_common():
            zeiten = [t for t, s in liste if s == skill]
            # Vorlauf: erster Treffer desselben Skills bis 10 s nach dem Cast
            vorlauf = [min(h - t for h in treffer[(eid, skill)] if 0 <= h - t <= 10)
                       for t in zeiten if any(0 <= h - t <= 10 for h in treffer[(eid, skill)])]
            # welcher andere Cast kommt 2-8 s vorher?
            davor = Counter()
            for t in zeiten:
                davor.update({s for tt, s in liste if s != skill and 2 <= t - tt <= 8})
            hinweis = ""
            if davor:
                s, k = davor.most_common(1)[0]
                if k >= max(2, anzahl // 2):
                    abst = median(t - tt for t in zeiten for tt, ss in liste if ss == s and 2 <= t - tt <= 8)
                    hinweis = f"{s} in {k}/{anzahl} Faellen, {abst:.1f} s vorher"
            print(f"  {skill:<9} {skillname.get(str(skill), '?')[:28]:28} {anzahl:>5} "
                  f"{(f'{median(vorlauf):.2f} s' if vorlauf else '-'):>12} {tode[(eid, skill)]:>4}  {hinweis}")


if __name__ == "__main__":
    main()
