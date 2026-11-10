"""Goldtest: spielt die Radar-Mitschnitte (pcap) ab und schreibt jedes Ergebnis als JSON-Zeile.

Drei Spuren: „radar“ (jedes Ereignis des RadarDienstes), „capture“ (Ausgabe und Kampfdateien
von deckbar-capture, also die DPS-Kette) und „runs“ (die Dungeon-Runs, die der Daemon aus diesen
Kampfdateien bildet, mit Discord-Text und den Bildpunkten ihres Bildes). Der Umbau muss für jeden Mitschnitt dasselbe liefern wie
der alte Code. Die Referenzen liegen neben den Mitschnitten, nicht im Repo: Sie enthalten Namen
anderer Spieler.

Aufruf (aus nexboard/radar, mit der .venv des Daemons):
  python -m werkzeuge.gold --schreiben radar|capture|runs   Referenzen der Spur neu schreiben
  python -m werkzeuge.gold datei.pcap                  Radar-Ereignisse auf stdout; nur mit leerem
                                                       HOME sinnvoll, siehe radar_isoliert()
"""
from __future__ import annotations

import argparse
import dataclasses
import gzip
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from radar.mitschnitt import SERVER_PORTS, TcpStrom, pcap_pakete, tcp_segment

RADAR = Path(__file__).resolve().parent.parent
DATEN = Path.home() / ".local" / "share" / "aion2-radar"
MITSCHNITTE = DATEN / "mitschnitte"
GOLD = DATEN / "gold"
CAPTURE = RADAR.parent / "capture" / "target" / "release" / "deckbar-capture"
TAKT_S = 0.2  # so oft ruft der Daemon RadarDienst.takt() auf


def wert(a: object) -> object:
    """Argument eines Ereignisses als JSON. Cube.seit ist ohne Serverzeit die Wanduhr, fällt weg."""
    if dataclasses.is_dataclass(a) and not isinstance(a, type):
        return {k: wert(v) for k, v in dataclasses.asdict(a).items() if k != "seit"}
    if isinstance(a, float):
        return round(a, 3)
    if isinstance(a, (list, tuple)):
        return [wert(v) for v in a]
    return a


class Aufzeichnung:
    """Hängt sich vor alle Haken des Radar-Zustands und schreibt mit, was die Warnzentrale meldet."""

    def __init__(self, dienst) -> None:
        self.dienst = dienst
        self.start: float | None = None
        self.jetzt = 0.0
        self.zeilen: list[str] = []
        self.warnungen: list[str] = []
        # Jede Liste bei_* ist ein Haken; der Mitschreiber kommt vor die echten Empfänger
        for name, empfaenger in vars(dienst.zustand).items():
            if name.startswith("bei_"):
                empfaenger.insert(0, self._mitschreiber(name))

    def _mitschreiber(self, name: str):
        def schreiben(*args: object) -> None:
            self.notieren(name, [wert(a) for a in args])
        return schreiben

    def notieren(self, art: str, daten: object) -> None:
        t = round(self.jetzt - (self.start or self.jetzt), 3)
        self.zeilen.append(json.dumps([t, art, daten], ensure_ascii=False))

    def uhr(self) -> float:
        return self.jetzt

    def takt(self) -> None:
        """Der Teil von RadarDienst.takt(), der ohne Ton und Bildschirm auskommt."""
        z = self.dienst.zentrale
        self.dienst.ansagen.takt()
        titel = [w.titel() for w in z.schnappschuss()]
        if titel != self.warnungen:
            self.warnungen = titel
            self.notieren("warnungen", titel)
        while z.laut:
            self.notieren("laut", list(z.laut.pop(0)))

    def ende(self) -> None:
        s = self.dienst.zustand.schnappschuss()
        pvp = self.dienst.zustand.pvp.stand()
        del pvp["beginn"]  # Wanduhr beim Anlegen des Dienstes, nicht aus dem Mitschnitt
        self.notieren("ende", {k: s[k] for k in ("nachrichten", "eid", "eid_sicher", "dungeon")}
                      | {"pvp": wert(pvp)})


def server_segmente(pcap: Path) -> Iterator[tuple[float, tuple, int, int, bytes]]:
    """(Zeit, Fluss, seq, Flags, Nutzdaten) jedes TCP-Segments vom Spielserver."""
    with open(pcap, "rb") as f:
        for zeit, ip in pcap_pakete(f):
            seg = tcp_segment(ip)
            if seg and seg[0][1] in SERVER_PORTS:
                yield zeit, *seg


def radar_ereignisse(pcap: Path) -> list[str]:
    """Einen Mitschnitt so schnell wie möglich durch den echten RadarDienst schicken."""
    from radar import konfig
    from radar.dienst import RadarDienst

    # Standardwerte, aber alle Warnungen, auch die anderer Spieler: so viel Verhalten wie möglich
    konfig._konfig = konfig.mit_standard({"nur_mich": False})
    dienst = RadarDienst(spawn_log=None)
    auf = Aufzeichnung(dienst)
    dienst.zentrale.uhr = auf.uhr
    naechster_takt = 0.0
    with mock.patch("time.time", auf.uhr):
        for zeit, fluss, seq, flags, daten in server_segmente(pcap):
            auf.jetzt = zeit
            auf.start = zeit if auf.start is None else auf.start
            if zeit >= naechster_takt:
                auf.takt()
                naechster_takt = zeit + TAKT_S
            dienst.quelle._strom(fluss).segment(seq, flags, daten)
        auf.takt()
        auf.ende()
    return auf.zeilen


def a2tools_mitschnitt(pcap: Path, ziel: Path) -> None:
    """pcap in das Textformat, das `deckbar-capture --replay` liest: Zeit|Client:<Port>:<Port>|Hex,
    je Strom in TCP-Reihenfolge (TcpStrom sortiert und verwirft Wiederholungen)."""
    zeit = 0.0
    stroeme: dict[tuple, TcpStrom] = {}
    with open(ziel, "w") as aus:
        def strom(fluss: tuple) -> TcpStrom:
            schluessel = f"Client:{fluss[3]}:{fluss[1]}"

            def ausgabe(daten: bytes) -> None:
                stempel = datetime.fromtimestamp(zeit, timezone.utc).isoformat(timespec="milliseconds")
                aus.write(f"{stempel}|{schluessel}|{daten.hex()}\n")
            return stroeme.setdefault(fluss, TcpStrom(ausgabe, lambda: None))

        for zeit, fluss, seq, flags, daten in server_segmente(pcap):
            strom(fluss).segment(seq, flags, daten)


def capture_lauf(pcap: Path, ordner: Path) -> list[dict]:
    """Den Mitschnitt durch deckbar-capture schicken; Kampfdateien landen in `ordner`. Zurück: jede Nachricht."""
    text = ordner.parent / "packets.txt"
    a2tools_mitschnitt(pcap, text)
    lauf = subprocess.run([str(CAPTURE), "--replay", str(text), "--history-dir", str(ordner)],
                          capture_output=True, text=True, check=True)
    return [json.loads(z) for z in lauf.stdout.splitlines()]


def capture_ausgabe(pcap: Path) -> list[str]:
    """Jede Zeile auf stdout außer dem Gruß (enthält Pfade), danach jede geschriebene Datei (Kämpfe und
    Treffer, daraus baut der Daemon die Runs)."""
    with tempfile.TemporaryDirectory() as tmp:
        ordner = Path(tmp) / "aion2"
        zeilen = [geordnet(n) for n in capture_lauf(pcap, ordner) if n["type"] != "hello"]
        for datei in sorted(ordner.rglob("*.json")):
            zeilen.append(geordnet({"datei": str(datei.relative_to(ordner)), "inhalt": json.loads(datei.read_text())}))
    return zeilen


def run_bilder(pcap: Path) -> list[str]:
    """Die Runs, die der Daemon aus den Kampfdateien des Mitschnitts bildet: je Run Bosse, Discord-Text und
    die Bildpunkte des Run-Bildes (verglichen wird das entpackte Bild, nicht die WebP-Datei). Mit
    RUN_BILDER=<Ordner> landen die Bilder zum Ansehen dort."""
    from deckbar_daemon import runs  # das Daemon-Paket, gleiche .venv
    from PIL import Image
    with tempfile.TemporaryDirectory() as tmp:
        ordner = Path(tmp) / "aion2"
        capture_lauf(pcap, ordner)
        kaempfe = [runs.load_fight(p) for p in sorted((ordner / "history").glob("*.json"))]
    tracker = runs.RunTracker(runs.RunSettings().idle_minutes * 60_000)
    fertig = []
    for kampf in sorted((k for k in kaempfe if k), key=lambda k: k.start_ms):
        fertig += tracker.add(kampf)
    fertig += tracker.check_idle(2**62)
    zeilen = []
    for nummer, run in enumerate(fertig):
        bild = runs.render_run(run)
        if os.environ.get("RUN_BILDER"):
            ziel = Path(os.environ["RUN_BILDER"]) / f"{pcap.stem}-{nummer}.webp"
            ziel.parent.mkdir(parents=True, exist_ok=True)
            ziel.write_bytes(bild)
        punkte = Image.open(io.BytesIO(bild)).convert("RGBA")
        zeilen.append(geordnet({"text": runs.run_message(run), "komplett": run.complete, "groesse": punkte.size,
                                "bosse": [[b.name, b.attempts, b.killed, b.total] for b in run.bosses()],
                                "bildpunkte": hashlib.sha256(punkte.tobytes()).hexdigest()}))
    return zeilen


def geordnet(daten: object) -> str:
    """JSON mit sortierten Listen: A2Tools gibt manche Listen in Hash-Reihenfolge aus, die bei jedem
    Lauf anders ist. Verglichen wird also der Inhalt, nicht die Reihenfolge."""
    return json.dumps(_sortiert(daten), sort_keys=True, ensure_ascii=False)


def _sortiert(daten: object) -> object:
    if isinstance(daten, dict):
        return {k: _sortiert(v) for k, v in daten.items()}
    if isinstance(daten, list):
        return sorted((_sortiert(v) for v in daten), key=lambda v: json.dumps(v, sort_keys=True))
    return daten


def radar_isoliert(pcap: Path) -> list[str]:
    """radar_ereignisse() in einem eigenen Prozess mit leerem HOME: keine eigenen Einstellungen, Karten
    oder gelernten Feldbosse, und nichts wird in die echten Dateien geschrieben."""
    with tempfile.TemporaryDirectory() as home:
        lauf = subprocess.run([sys.executable, "-m", "werkzeuge.gold", str(pcap)], cwd=RADAR,
                              env={**os.environ, "HOME": home}, capture_output=True, text=True, check=True)
    return lauf.stdout.splitlines()


# Spur -> Abspielen; jede Spur hat eigene Referenzen unter GOLD/<spur>/
SPUREN = {"radar": radar_isoliert, "capture": capture_ausgabe, "runs": run_bilder}


def referenz(spur: str, pcap: Path) -> Path:
    return GOLD / spur / f"{pcap.stem}.jsonl.gz"


def referenz_lesen(spur: str, pcap: Path) -> list[str]:
    with gzip.open(referenz(spur, pcap), "rt", encoding="utf-8") as f:
        return f.read().splitlines()


def alle(spur: str, pcaps: list[Path]) -> list[list[str]]:
    """Mitschnitte parallel abspielen; jeder läuft in einem eigenen Prozess."""
    with ThreadPoolExecutor(max_workers=os.cpu_count()) as pool:
        return list(pool.map(SPUREN[spur], pcaps))


def schreiben(spur: str) -> None:
    pcaps = sorted(MITSCHNITTE.glob("*.pcap"))
    (GOLD / spur).mkdir(parents=True, exist_ok=True)
    for pcap, zeilen in zip(pcaps, alle(spur, pcaps)):
        with gzip.open(referenz(spur, pcap), "wt", encoding="utf-8") as f:
            f.write("".join(z + "\n" for z in zeilen))  # ohne Zeilen eine leere Datei, nicht eine leere Zeile
        print(f"{spur} {pcap.name}: {len(zeilen)} Zeilen", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pcap", nargs="?", type=Path)
    ap.add_argument("--schreiben", choices=SPUREN, help="Referenzen dieser Spur für alle Mitschnitte schreiben")
    a = ap.parse_args()
    if a.schreiben:
        schreiben(a.schreiben)
    elif a.pcap:
        print("\n".join(radar_ereignisse(a.pcap)))
    else:
        ap.error("Mitschnitt oder --schreiben angeben")


if __name__ == "__main__":
    main()
