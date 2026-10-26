"""AION 2 · Radar: läuft im Daemon, solange AION 2 läuft, und zeigt sich als Widgets im Overlay.

Mitschnitt und Auswertung stecken in nexboard/radar (RadarDienst, ohne Fenster). Der Daemon ruft
dessen Takt mehrmals pro Sekunde auf und schickt den Stand als Overlay-Ereignis „radar“. Das
Radar-Widget zeigt sich dort nur, solange ein Cube in Sicht ist.

Die Einstellungen stehen in ~/.config/aion2-radar.json. Standardwerte und Warnungsliste kommen aus
radar/standard.json und radar/meldungen.json, denselben Dateien, die das Radar nutzt.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Awaitable, Callable

from .capture import aion2_running
from .config import _atomic_write

ORDNER = Path(__file__).resolve().parents[2] / "radar"  # nexboard/radar
sys.path.insert(0, str(ORDNER))  # Paket „radar“ liegt dort, nicht im Daemon
from radar import daten, konfig, uebersicht  # noqa: E402
from radar.dienst import RadarDienst  # noqa: E402
from radar.punkte import Karte  # noqa: E402

log = logging.getLogger(__name__)

TAKT_S = 0.2  # so oft zeichnen die Widgets neu, Warnungen zählen in Zehntelsekunden
BEFEHLE = ("ton_testen", "warnung_testen", "aufnahme_start", "aufnahme_stopp", "neustart", "pvp_neu")


async def _aion2_laeuft() -> bool:
    return await asyncio.to_thread(aion2_running)


def _json(pfad: Path) -> dict:
    try:
        inhalt = json.loads(pfad.read_text())
    except (OSError, ValueError):
        return {}
    return inhalt if isinstance(inhalt, dict) else {}


class Radar:
    def __init__(self, veroeffentlichen: Callable[[dict], Awaitable[None]],
                 spiel_laeuft: Callable[[], Awaitable[bool]] = _aion2_laeuft,
                 dienst: Callable[[str], Any] = RadarDienst, abfrage_s: float = 5, nachlauf_s: float = 30) -> None:
        self.veroeffentlichen = veroeffentlichen  # Overlay-Ereignis „radar“
        self.spiel_laeuft = spiel_laeuft
        self.neuer_dienst = dienst
        self.abfrage_s = abfrage_s
        self.nachlauf_s = nachlauf_s  # Spiel weg: so lange warten (Absturz mit Neustart, Ladebildschirm)
        self.meldungen = _json(ORDNER / "radar" / "meldungen.json")
        self.dienst: RadarDienst | None = None
        self.spiel = False

    @property
    def laeuft(self) -> bool:
        return self.dienst is not None

    @property
    def aufnahme(self) -> bool:
        return bool(self.dienst and self.dienst.aufnahme)

    def einstellungen(self) -> dict:
        return {**konfig.STANDARD, **_json(konfig.KONFIG)}

    def info(self) -> dict:
        return {"einstellungen": self.einstellungen(), "meldungen": self.meldungen,
                "karten": [k.name for k in Karte.alle()],
                "laeuft": self.laeuft, "aufnahme": self.aufnahme, "spiel": self.spiel}

    def _pruefen(self, aenderung: dict) -> None:
        for schluessel, wert in aenderung.items():
            if schluessel not in konfig.STANDARD:
                raise ValueError(f"unbekannte Einstellung {schluessel}")
            soll = type(konfig.STANDARD[schluessel])
            erlaubt = (int, float) if soll is float else soll  # 1 statt 1.0 ist in Ordnung
            if isinstance(wert, bool) != (soll is bool) or not isinstance(wert, erlaubt):
                raise ValueError(f"{schluessel}: erwartet {soll.__name__}")

    async def speichern(self, aenderung: dict) -> dict:
        """Ändert nur, was die Seite schickt; fremde Schlüssel in der Datei bleiben."""
        self._pruefen(aenderung)
        inhalt = {**_json(konfig.KONFIG), **aenderung}
        _atomic_write(konfig.KONFIG, json.dumps(inhalt, indent=2, ensure_ascii=False))
        konfig.konfig_neu_laden()
        if self.dienst:
            self.dienst.neu_laden()
        return self.info()

    async def befehl(self, name: str) -> None:
        if name not in BEFEHLE:
            raise ValueError(f"unbekannter Befehl {name}")
        if name == "neustart":  # z.B. nach neuem Charakternamen, den liest das Radar nur beim Start
            self._beenden()
            if self.spiel:
                self._starten()
            return
        if not self.dienst:
            raise RuntimeError("Radar läuft nicht")
        aktionen = {"ton_testen": konfig.ton_abspielen, "warnung_testen": self.dienst.warnung_testen,
                    "aufnahme_start": self.dienst.aufnahme_starten,
                    "aufnahme_stopp": self.dienst.quelle.aufnahme_stoppen,
                    "pvp_neu": self.dienst.pvp_neu}
        aktionen[name]()

    def uebersicht(self) -> dict:
        """Feldbosse, Termine und Vertraute für die NexBoard-Seite. Ohne laufendes Radar aus den
        gespeicherten Ständen."""
        if self.dienst:
            z = self.dienst.zustand
            plaetze, zone, vertraute = z.feldbosse, z.zone, z.vertraute
        else:
            plaetze, zone, vertraute = daten.laden("feldbosse.json"), None, daten.laden("vertraute.json")
        return {"termine": uebersicht.termine(time.time()), "feldbosse": uebersicht.feldbosse(plaetze, zone),
                "vertraute": uebersicht.vertraute(vertraute)}

    def karte(self) -> dict:
        return self.dienst.karte() if self.dienst else {"name": ""}

    def kartendatei(self, art: str) -> Path | None:
        """Bild oder Teleporter-Symbol der gezeigten Karte, für die Overlay-Seite."""
        name = self.karte()["name"]
        if not name or art not in ("bild", "symbol"):
            return None
        karte = Karte(name)
        datei = karte.bild if art == "bild" else karte.symbol
        return datei if datei.exists() else None

    def _starten(self) -> None:
        log.info("AION 2 läuft, starte Radar")
        self.dienst = self.neuer_dienst(self.einstellungen()["name"])
        self.dienst.starten()

    def _beenden(self) -> None:
        if self.dienst:
            log.info("Radar wird beendet")
            self.dienst.stoppen()
            self.dienst = None

    async def _spiel_pruefen(self, weg: float) -> float:
        """Radar mit dem Spiel starten und nachlauf_s nach Spielende beenden. Gibt zurück, wie lange
        das Spiel schon weg ist."""
        if await self.spiel_laeuft():
            if not self.spiel:
                self.spiel = True
                self._starten()
            return 0
        if self.spiel:
            weg += self.abfrage_s
            if weg >= self.nachlauf_s:
                self.spiel = False
                self._beenden()
                await self.veroeffentlichen({"aktiv": False})
        return weg

    async def watch(self) -> None:
        """Modul-Aufgabe: Spiel alle abfrage_s prüfen, dazwischen Takt und Stand fürs Overlay."""
        weg, pruefen_um = 0.0, 0.0
        try:
            while True:
                if time.monotonic() >= pruefen_um:
                    pruefen_um = time.monotonic() + self.abfrage_s
                    weg = await self._spiel_pruefen(weg)
                if self.dienst:
                    self.dienst.takt()
                    await self.veroeffentlichen({"aktiv": True, **self.dienst.stand()})
                await asyncio.sleep(TAKT_S)
        finally:
            self.spiel = False
            self._beenden()
            await self.veroeffentlichen({"aktiv": False})
