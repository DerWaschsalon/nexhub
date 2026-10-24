"""Start: python -m radar [--name Navonex] [--pcap datei.pcap] [--log]"""
from __future__ import annotations

import argparse
import fcntl
import os
import subprocess
import signal
import sys
from pathlib import Path

LOG = Path.home() / ".local" / "share" / "aion2-radar" / "spawns.jsonl"
SPERRE = Path.home() / ".cache" / "aion2-radar" / "laeuft.lock"


def schon_offen() -> bool:
    """Live nur ein Radar: sonst laufen alte Fenster mit altem Code weiter und Ansagen kommen doppelt."""
    SPERRE.parent.mkdir(parents=True, exist_ok=True)
    global _sperre  # offen halten, solange das Radar laeuft; das System gibt die Sperre beim Beenden frei
    _sperre = open(SPERRE, "w")
    try:
        fcntl.flock(_sperre, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return False
    except OSError:
        subprocess.run(["notify-send", "AION2 Radar", "Läuft schon. Zum Neustart erst über Rechtsklick > Beenden schließen."],
                       check=False)
        return True


def main() -> int:
    ap = argparse.ArgumentParser(prog="aion2-radar")
    ap.add_argument("--name", default=os.environ.get("AION2_CHAR", ""),
                    help="Charaktername, macht die eigene Erkennung sicher")
    ap.add_argument("--pcap", help="Mitschnitt abspielen statt live mitzulesen")
    ap.add_argument("--schnell", action="store_true", help="pcap ohne Echtzeit abspielen")
    ap.add_argument("--log", action="store_true", help=f"alle Spawns nach {LOG} schreiben")
    ap.add_argument("--karte", action="store_true", help="Kartenfenster beim Start zeigen")
    ap.add_argument("--id", type=int, action="append", default=[],
                    help="zusaetzliche Objekt-ID als Cube werten (mehrfach)")
    a = ap.parse_args()
    if not a.pcap and schon_offen():
        return 0

    # XWayland: nur so kann das Fenster seine Position setzen und oben bleiben
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from . import befehle
    from .karte import KartenFenster
    from .overlay import RadarFenster, konfig_neu_laden, ton_abspielen
    from .punkte import PunkteDB
    from .quelle import Quelle
    from .warnung import STATUS_REGELN, WarnFenster, WarnZentrale, ansagen_vorbereiten
    from .zustand import RadarZustand

    if a.log:
        LOG.parent.mkdir(parents=True, exist_ok=True)
    zustand = RadarZustand(a.name, LOG if a.log else None, set(a.id), speichern=not a.pcap)
    quelle = Quelle(zustand)

    app = QApplication(sys.argv)
    app.setApplicationName("aion2-radar")

    # jeder gesehene Cube wird als Spawnpunkt gemerkt
    punkte = PunkteDB()
    zustand.bei_neuem_cube.append(lambda c: punkte.eintragen(c.x, c.y, c.z, c.objekt_id))

    zentrale = WarnZentrale(zustand)
    ansagen_vorbereiten()
    zustand.bei_cast.append(zentrale.cast)
    zustand.bei_status.append(zentrale.status)
    zustand.bei_groggy.append(zentrale.groggy)
    zustand.status_ids = set(STATUS_REGELN)

    karte = KartenFenster(zustand, punkte)
    fenster = RadarFenster(zustand, quelle, karte, WarnFenster(zentrale))
    fenster.show()
    if a.karte or fenster.k.get("karte_offen"):
        karte.show()
    # Strg+C und Beenden durch den NexBoard-Daemon: Radar schliessen (stoppt auch tcpdump), dann die
    # App, auch wenn noch andere Fenster offen sind. Der Timer gibt Python regelmaessig die Kontrolle,
    # sonst kommt das Signal in Qt nicht an.
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: (fenster.close(), app.quit()))
    wach = QTimer()
    wach.timeout.connect(lambda: None)
    wach.start(500)

    def neu_laden() -> None:
        """Einstellungen von der NexBoard-Seite uebernehmen. Was die Fenster beim Zeichnen lesen,
        wirkt sofort, hier nur das, was sie beim Start setzen."""
        k = konfig_neu_laden()
        fenster.setWindowOpacity(k["deckkraft"])
        fenster.resize(k["groesse"], k["groesse"] + 34)
        fenster.update()
        karte.setWindowOpacity(k["karte_deckkraft"])
        karte.folgen = k["karte_folgen"]
        zentrale.an = k["warn_an"]
        ansagen_vorbereiten()  # falls die Sprache gewechselt hat

    bote = befehle.starten({
        "neu_laden": neu_laden,
        "ton_testen": ton_abspielen,
        "warnung_testen": fenster.warnung.test,
        "warnung_verschieben": fenster.warnung.verschieben_umschalten,
        "karte_zeigen": lambda: fenster._karte_umschalten(True),
        "karte_ausblenden": lambda: fenster._karte_umschalten(False),
        "uebersicht_zeigen": fenster._uebersicht_zeigen,
        "aufnahme_start": lambda: quelle.aufnahme_starten(zustand.dungeon or "dungeon"),
        "aufnahme_stopp": quelle.aufnahme_stoppen,
    })

    if a.pcap:
        quelle.datei_starten(a.pcap, echtzeit=not a.schnell)
    else:
        quelle.live_starten()
    code = app.exec()
    quelle.stoppen()
    del bote
    return code


if __name__ == "__main__":
    sys.exit(main())
