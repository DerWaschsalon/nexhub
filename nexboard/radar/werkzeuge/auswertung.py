"""Wertet Kaempfe aus: Mitschnitt + Kampfdateien des DPS-Meters (A2Tools/DeckBar).

Pro Kampf: Boss, Dauer, eigene DPS, jeder eigene Tod mit Ursache und mit der
Warnung, die das Radar zu dem Zeitpunkt gezeigt haette. Am Ende: wie frueh
die Teufelsflamme angekuendigt wurde.

Aufruf: python -m werkzeuge.auswertung mitschnitte/datei.pcap [--name Navonex]
"""
from __future__ import annotations

import argparse
import json
import struct
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from radar.mitschnitt import SERVER_PORTS, pcap_pakete, tcp_segment
from radar.protokoll import uvarint
from radar.quelle import Quelle
from radar.warnung import WarnZentrale
from radar.zustand import RadarZustand

KAEMPFE = Path.home() / ".local/share/deckbar/aion2/history"
SKILLNAMEN = Path("/usr/lib/A2Tools DPS Meter/data/i18n/skills/de.json")
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
    ap.add_argument("--name", default="Navonex")
    a = ap.parse_args()
    skillname = json.loads(SKILLNAMEN.read_text()) if SKILLNAMEN.exists() else {}
    skillname["1801116"] = "Regen des Hasses"  # die Ticks haben keinen eigenen Namen

    # Mitschnitt einmal durch Radar-Zustand und Warnzentrale laufen lassen
    zustand = RadarZustand(a.name)
    uhr = [0.0]
    zentrale = WarnZentrale(zustand, uhr=lambda: uhr[0])
    zentrale.an = True
    zustand.bei_cast.append(zentrale.cast)
    hp = defaultdict(list)        # entity -> [(zeit, hp)]
    treffer = defaultdict(list)   # ziel -> [(zeit, angreifer, skill)]
    warnungen = []                # [(zeit, [(titel, seit)])]

    lesen = zustand.verarbeiten

    def mitlesen(op: int, p: bytes) -> None:
        lesen(op, p)
        try:
            eid, n = uvarint(p)
            if op == 0x8D00 and p[n:n + 3] == b"\x02\x01\x00":
                hp[eid].append((uhr[0], struct.unpack_from("<I", p, n + 3)[0]))
            elif op == 0x3804:
                angreifer, k = uvarint(p, n + 2)
                treffer[eid].append((uhr[0], angreifer, struct.unpack_from("<I", p, n + 2 + k)[0]))
        except (ValueError, struct.error):
            pass
    zustand.verarbeiten = mitlesen

    quelle = Quelle(zustand)
    von = None
    with open(a.pcap, "rb") as f:
        for zeit, ip in pcap_pakete(f):
            seg = tcp_segment(ip)
            if seg and seg[0][1] in SERVER_PORTS:
                von = von or zeit
                uhr[0] = zeit
                quelle._strom(seg[0]).segment(*seg[1:])
                warnungen.append((zeit, [(w.regel.titel, w.seit) for w in zentrale.schnappschuss()]))

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
