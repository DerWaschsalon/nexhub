"""Lernmodus: wertet eine Dungeon-Aufnahme aus, damit neue Warnungen entstehen koennen.

Pro Boss jeder Skill mit: wie oft gecastet, wann der erste Treffer kommt (= Vorlauf
fuer die Warnung), wie viele Spieler daran gestorben sind und welcher andere Cast
regelmaessig davor kommt (moegliche fruehere Vorwarnung, wie Todesmal vor Teufelsflamme).

Aufruf: python -m werkzeuge.lernen mitschnitte/<datei>.pcap
"""
from __future__ import annotations

import argparse
import json
import struct
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

from radar.mitschnitt import SERVER_PORTS, pcap_pakete, tcp_segment
from radar.protokoll import uvarint
from radar.quelle import Quelle
from radar.zustand import BOSSE, OP_CAST, OP_NPC, RadarZustand

NAMEN = Path("/usr/lib/A2Tools DPS Meter/data/i18n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pcap")
    a = ap.parse_args()
    skillname = json.loads((NAMEN / "skills/de.json").read_text())
    npcname = {k: v["name"] for k, v in json.loads((NAMEN / "npcs/de.json").read_text()).items()}

    # Aufnahme einmal durchlesen und Boss-Casts, Treffer und Tode sammeln
    zustand = RadarZustand()
    uhr = [0.0]
    boss_von: dict[int, int] = {}                 # Entity -> Boss-NPC-ID
    casts = defaultdict(list)                     # Boss-Entity -> [(zeit, skill)]
    treffer = defaultdict(list)                   # (Boss-Entity, skill) -> [zeit]
    letzter_treffer: dict[int, tuple[int, int]] = {}  # Ziel -> (Boss-Entity, skill)
    hp: dict[int, int] = {}
    tode = Counter()                              # (Boss-Entity, skill) -> Anzahl

    def mitlesen(op: int, p: bytes) -> None:
        try:
            eid, n = uvarint(p)
            if op == OP_NPC and struct.unpack_from("<I", p, n + 3)[0] in BOSSE:
                boss_von[eid] = struct.unpack_from("<I", p, n + 3)[0]
            elif op == OP_CAST and eid in boss_von:
                casts[eid].append((uhr[0], struct.unpack_from("<I", p, n + 1)[0]))
            elif op == 0x3804:  # Treffer: Ziel, 2 Byte, Angreifer, Skill
                angreifer, k = uvarint(p, n + 2)
                if angreifer in boss_von:
                    skill = struct.unpack_from("<I", p, n + 2 + k)[0]
                    treffer[(angreifer, skill)].append(uhr[0])
                    letzter_treffer[eid] = (angreifer, skill)
            elif op == 0x8D00 and p[n:n + 3] == b"\x02\x01\x00":  # aktuelle HP
                wert = struct.unpack_from("<I", p, n + 3)[0]
                if wert == 0 and hp.get(eid) and eid in letzter_treffer:
                    tode[letzter_treffer[eid]] += 1
                hp[eid] = wert
        except (ValueError, struct.error):
            pass
    zustand.verarbeiten = mitlesen

    quelle = Quelle(zustand)
    with open(a.pcap, "rb") as f:
        for zeit, ip in pcap_pakete(f):
            seg = tcp_segment(ip)
            if seg and seg[0][1] in SERVER_PORTS:
                uhr[0] = zeit
                quelle._strom(seg[0]).segment(*seg[1:])

    for eid, npc in boss_von.items():
        liste = casts[eid]
        if not liste:
            continue
        print(f"\n{npcname.get(str(npc), npc)} ({BOSSE[npc]}), {len(liste)} Casts")
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
