"""AION 2 · Radar: startet das Radar (nexboard/radar, eigenes Qt-Programm), solange AION 2 läuft,
und verwaltet seine Einstellungen für die Web-UI.

Die Einstellungen stehen in ~/.config/aion2-radar.json. Die Datei schreibt auch das Radar selbst
(Verschieben, Rechtsklick-Menü), deshalb liest der Daemon sie vor jedem Speichern neu und ändert
nur, was die Seite schickt. Standardwerte und Warnungsliste kommen aus radar/standard.json und
radar/meldungen.json, denselben Dateien, die das Radar nutzt.

Befehle gehen als Textzeile über stdin an das Radar (radar/befehle.py). Das Radar meldet seine
Aufnahme als Zeile auf stdout ("aufnahme an" / "aufnahme aus").
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Awaitable, Callable

from .capture import aion2_running
from .config import _atomic_write

log = logging.getLogger(__name__)

KONFIG = Path.home() / ".config" / "aion2-radar.json"
ORDNER = Path(__file__).resolve().parents[2] / "radar"  # nexboard/radar
PROGRAMM = ["/usr/bin/python3", "-m", "radar", "--log", "--befehle"]  # System-Python, dort ist PySide6
POSITIONEN = {"x", "y"}  # stellt man durch Ziehen ein, nicht auf der Seite
BEFEHLE = ("neu_laden", "ton_testen", "warnung_testen", "warnung_verschieben", "karte_zeigen",
           "karte_ausblenden", "uebersicht_zeigen", "aufnahme_start", "aufnahme_stopp")


async def _aion2_laeuft() -> bool:
    return await asyncio.to_thread(aion2_running)


def _json(pfad: Path) -> dict:
    try:
        daten = json.loads(pfad.read_text())
    except (OSError, ValueError):
        return {}
    return daten if isinstance(daten, dict) else {}


class Radar:
    def __init__(self, konfig: Path = KONFIG, arbeitsordner: Path = ORDNER, programm: list[str] = PROGRAMM,
                 spiel_laeuft: Callable[[], Awaitable[bool]] = _aion2_laeuft, abfrage_s: float = 5,
                 nachlauf_s: float = 30) -> None:
        self.konfig = konfig
        self.arbeitsordner = arbeitsordner
        self.programm = programm
        self.spiel_laeuft = spiel_laeuft
        self.abfrage_s = abfrage_s
        self.nachlauf_s = nachlauf_s  # Spiel weg: so lange warten (Absturz mit Neustart, Ladebildschirm)
        self.standard = _json(ORDNER / "radar" / "standard.json")
        self.meldungen = _json(ORDNER / "radar" / "meldungen.json")
        self.prozess: asyncio.subprocess.Process | None = None
        self.aufnahme = False
        self.spiel = False

    @property
    def laeuft(self) -> bool:
        return self.prozess is not None and self.prozess.returncode is None

    def einstellungen(self) -> dict:
        return {**self.standard, **_json(self.konfig)}

    def info(self) -> dict:
        return {"einstellungen": self.einstellungen(), "meldungen": self.meldungen,
                "laeuft": self.laeuft, "aufnahme": self.aufnahme, "spiel": self.spiel}

    def _pruefen(self, aenderung: dict) -> None:
        for schluessel, wert in aenderung.items():
            if schluessel not in self.standard or schluessel in POSITIONEN:
                raise ValueError(f"unbekannte Einstellung {schluessel}")
            soll = type(self.standard[schluessel])
            erlaubt = (int, float) if soll is float else soll  # 1 statt 1.0 ist in Ordnung
            if isinstance(wert, bool) != (soll is bool) or not isinstance(wert, erlaubt):
                raise ValueError(f"{schluessel}: erwartet {soll.__name__}")

    async def speichern(self, aenderung: dict) -> dict:
        self._pruefen(aenderung)
        daten = {**_json(self.konfig), **aenderung}
        _atomic_write(self.konfig, json.dumps(daten, indent=2, ensure_ascii=False))
        if self.laeuft:
            await self.befehl("neu_laden")
        return self.info()

    async def befehl(self, name: str) -> None:
        if name == "neustart":  # z.B. nach neuem Charakternamen, den liest das Radar nur beim Start
            await self._beenden()
            if self.spiel:
                await self._starten()
            return
        if name not in BEFEHLE:
            raise ValueError(f"unbekannter Befehl {name}")
        if not self.laeuft:
            raise RuntimeError("Radar läuft nicht")
        try:
            self.prozess.stdin.write(name.encode() + b"\n")
            await self.prozess.stdin.drain()
        except OSError as e:  # gerade beendet
            raise RuntimeError("Radar läuft nicht") from e

    async def _starten(self) -> None:
        name = self.einstellungen().get("name")
        log.info("AION 2 läuft, starte Radar")
        try:
            self.prozess = await asyncio.create_subprocess_exec(
                *self.programm, *(["--name", name] if name else []), cwd=self.arbeitsordner,
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE)
        except OSError as e:
            log.error("Radar startet nicht: %s", e)
            return
        asyncio.create_task(self._ausgabe_lesen(self.prozess))

    async def _ausgabe_lesen(self, prozess: asyncio.subprocess.Process) -> None:
        async for zeile in prozess.stdout:
            if zeile.strip() in (b"aufnahme an", b"aufnahme aus"):
                self.aufnahme = zeile.strip() == b"aufnahme an"
        if prozess is self.prozess:
            self.aufnahme = False  # Radar beendet

    async def _beenden(self) -> None:
        p = self.prozess
        if p is None or p.returncode is not None:
            return
        log.info("Radar wird beendet")
        p.terminate()
        try:
            await asyncio.wait_for(p.wait(), 3)
        except TimeoutError:
            p.kill()
            await p.wait()
        self.aufnahme = False

    async def watch(self) -> None:
        """Modul-Aufgabe: Radar mit dem Spiel starten und nachlauf_s nach Spielende beenden. Gehandelt
        wird nur beim Wechsel: wer das Radar mitten im Spiel schließt, behält das."""
        weg = 0.0
        try:
            while True:
                if await self.spiel_laeuft():
                    weg = 0
                    if not self.spiel:
                        self.spiel = True
                        await self._starten()
                elif self.spiel:
                    weg += self.abfrage_s
                    if weg >= self.nachlauf_s:
                        self.spiel = False
                        await self._beenden()
                await asyncio.sleep(self.abfrage_s)
        finally:
            self.spiel = False
            await asyncio.shield(self._beenden())
