"""Verbindet Mitschnitt (live oder pcap-Datei) mit dem Radar-Zustand."""
from __future__ import annotations

import threading
import time
from datetime import datetime
from pathlib import Path
from typing import BinaryIO

from .mitschnitt import SERVER_PORTS, TcpStrom, pcap_pakete, tcp_segment, tcpdump_starten
from .protokoll import StromZerleger
from .zustand import RadarZustand

AUFNAHMEN = Path.home() / ".local" / "share" / "aion2-radar" / "mitschnitte"  # nie ins Repo


class Quelle:
    def __init__(self, zustand: RadarZustand) -> None:
        self.zustand = zustand
        self.stroeme: dict[tuple, TcpStrom] = {}
        self.fehler: str | None = None
        self.prozess = None
        self.aufnahme = None  # zweiter tcpdump, schreibt fuer den Lernmodus in eine Datei

    def _strom(self, fluss: tuple) -> TcpStrom:
        strom = self.stroeme.get(fluss)
        if strom is None:
            zerleger = StromZerleger()

            def ausgabe(daten: bytes) -> None:
                for op, p in zerleger.fuettern(daten):
                    self.zustand.verarbeiten(op, p)

            strom = self.stroeme[fluss] = TcpStrom(ausgabe, zerleger.zuruecksetzen)
        return strom

    def lesen(self, datei: BinaryIO, echtzeit: bool = False) -> None:
        start_pcap = start_wand = None
        for zeit, ip in pcap_pakete(datei):
            seg = tcp_segment(ip)
            if not seg or seg[0][1] not in SERVER_PORTS:
                continue
            if echtzeit:
                if start_pcap is None:
                    start_pcap, start_wand = zeit, time.time()
                warten = (zeit - start_pcap) - (time.time() - start_wand)
                if warten > 0:
                    time.sleep(warten)
            fluss, seq, flags, daten = seg
            self._strom(fluss).segment(seq, flags, daten)

    def live_starten(self, schnittstelle: str = "any") -> threading.Thread:
        def lauf() -> None:
            try:
                self.prozess = tcpdump_starten(schnittstelle)
                self.lesen(self.prozess.stdout)
                if self.prozess.wait() != 0:
                    self.fehler = "tcpdump beendet (Rechte? getcap /usr/bin/tcpdump)"
            except FileNotFoundError:
                self.fehler = "tcpdump fehlt (pacman -S tcpdump, dann setcap cap_net_raw,cap_net_admin=eip)"
            except Exception as e:  # Anzeige soll den Fehler zeigen
                self.fehler = str(e)

        t = threading.Thread(target=lauf, daemon=True)
        t.start()
        return t

    def datei_starten(self, pfad: str, echtzeit: bool = True) -> threading.Thread:
        def lauf() -> None:
            with open(pfad, "rb") as f:
                self.lesen(f, echtzeit)

        t = threading.Thread(target=lauf, daemon=True)
        t.start()
        return t

    def aufnahme_starten(self, name: str = "dungeon") -> None:
        self.aufnahme_stoppen()
        AUFNAHMEN.mkdir(parents=True, exist_ok=True)
        datei = AUFNAHMEN / f"{name.replace(' ', '_')}-{datetime.now():%Y%m%d-%H%M}.pcap"
        self.aufnahme = tcpdump_starten(datei=str(datei))
        print("aufnahme an", flush=True)  # liest der NexBoard-Daemon fuer die Anzeige

    def aufnahme_stoppen(self) -> None:
        if self.aufnahme:
            self.aufnahme.terminate()
            self.aufnahme = None
            print("aufnahme aus", flush=True)

    def stoppen(self) -> None:
        self.aufnahme_stoppen()
        if self.prozess and self.prozess.poll() is None:
            self.prozess.terminate()
