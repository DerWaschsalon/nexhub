"""AION 2 · Radar: läuft im Daemon, solange AION 2 läuft, und zeigt sich als Widgets im Overlay.

Mitschnitt und Auswertung stecken in aion2/ (RadarService, ohne Fenster). Der Daemon ruft dessen Takt
mehrmals pro Sekunde auf und schickt den Stand als Overlay-Ereignis „radar“. Das Radar-Widget zeigt sich
dort nur, solange ein Cube in Sicht ist.

Die Einstellungen stehen in ~/.config/aion2-radar.json über den Standardwerten aus aion2/data/defaults.json.
Die Schlüssel von info() sind die der NexBoard-Seite.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from .aion2 import field_bosses, settings
from .aion2.callouts import page_list
from .aion2.gamedata import load_state
from .aion2.maps import GameMap
from .aion2.rules import SWITCHES
from .aion2.service import DEATHS_KEPT, PARTS, RadarService
from .config import _atomic_write
from .game_process import aion2_running

log = logging.getLogger(__name__)

SETTINGS_FILE = settings.FILE  # ~/.config/aion2-radar.json
TICK_S = 0.2  # so oft zeichnen die Widgets neu, Warnungen zählen in Zehntelsekunden
# Charaktername und Sprache stehen in den allgemeinen Einstellungen (config.yaml); in die Datei des Radars
# schreibt sie nur sync_profile(), bis jedes Modul seine Einstellungen über den Daemon bekommt.
PROFILE_KEYS = ("name", "sprache")
VOICE_LANGUAGES = ("de", "en")  # Ansagen und Warnungen gibt es nur auf Deutsch und Englisch
# Voreinstellungen der Seite „Warnungen“: was jede setzt. Art der Ansage, Wellenton und die Einzelheiten je
# Dungeon, Boss und Ruf stehen unter „Erweitert“ und bleiben beim Wechsel, wie sie sind.
WARNING_PRESETS: dict[str, dict[str, Any]] = {
    "aus": {"warn_an": False},
    "wichtig": {"warn_an": True, "nur_mich": True},  # nur, was dich betrifft (Standard)
    "alles": {"warn_an": True, "nur_mich": False},  # auch Angriffe und Effekte auf andere Spieler
}
OWN_PRESET = "eigene"
RESTART = "neustart"
# Knopf der NexBoard-Seite → was er am laufenden Dienst tut
COMMANDS: dict[str, Callable[[RadarService, str], None]] = {
    "ton_testen": lambda service, _: service.test_ping(),
    "warnung_testen": lambda service, _: service.test_warning(),
    "aufnahme_start": lambda service, _: service.start_recording(),
    "aufnahme_stopp": lambda service, _: service.stop_recording(),
    "ansage_testen": lambda service, call: service.test_callout(call),
}
NO_FIGHT = {"groggy": False, "warnungen": []}
MAP_FILES = {"bild": lambda game_map: game_map.image, "symbol": lambda game_map: game_map.symbol}


async def _game_running() -> bool:
    return await asyncio.to_thread(aion2_running)


class Radar:
    def __init__(self, publish: Callable[[dict], Awaitable[None]],
                 game_running: Callable[[], Awaitable[bool]] = _game_running,
                 service: Callable[[str], Any] = RadarService, poll_s: float = 5, linger_s: float = 30) -> None:
        self.publish = publish  # Overlay-Ereignis „radar“
        self.game_running = game_running
        self.new_service = service
        self.poll_s = poll_s
        self.linger_s = linger_s  # Spiel weg: so lange warten (Absturz mit Neustart, Ladebildschirm)
        self.callouts = page_list()  # Boss-Ansagen je Schalter, für eigene Worte und ▶ auf der Seite
        self.service: RadarService | None = None
        self.game = False
        self.parts: set[str] = set()  # eingeschaltete Teile (Module); das Radar läuft, solange einer an ist
        self._task: asyncio.Task | None = None
        # Tode mit Ursache; hier, damit sie ein Ende des Radars bis zum Hochladen überleben
        self.deaths: deque[dict] = deque(maxlen=DEATHS_KEPT)

    def enable(self, part: str) -> None:
        """Ein Modul geht an: das Radar läuft ab jetzt (auch) für diesen Teil."""
        assert part in PARTS, part
        self.parts.add(part)
        self._parts_changed()
        if self._task is None:
            self._task = asyncio.create_task(self.watch())

    async def disable(self, part: str) -> None:
        """Ein Modul geht aus; mit dem letzten endet das Radar."""
        self.parts.discard(part)
        self._parts_changed()
        if not self.parts and self._task:
            task, self._task = self._task, None
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    def _parts_changed(self) -> None:
        if self.service:
            self.service.reload()

    @property
    def running(self) -> bool:
        return self.service is not None

    @property
    def error(self) -> str | None:
        """Warum der Mitschnitt des Radars nicht läuft (etwa tcpdump ohne Rechte), sonst None."""
        return self.service.error if self.service else None

    @property
    def recording(self) -> bool:
        return bool(self.service and self.service.recording)

    def settings(self) -> dict:
        return settings.with_defaults(settings.read_file())

    def warning_preset(self) -> str:
        """Welche Voreinstellung zu den Einstellungen passt; „eigene“, wenn keine."""
        current = self.settings()
        for name, values in WARNING_PRESETS.items():
            if all(current[key] == value for key, value in values.items()):
                return name
        return OWN_PRESET

    def info(self) -> dict:
        return {"einstellungen": self.settings(), "meldungen": SWITCHES, "ansagen": self.callouts,
                "karten": [m.name for m in GameMap.all()], "presets": WARNING_PRESETS,
                "preset": self.warning_preset(),
                "laeuft": self.running, "aufnahme": self.recording, "spiel": self.game, "fehler": self.error}

    def _validate(self, change: dict) -> None:
        for key, value in change.items():
            if key in PROFILE_KEYS:
                raise ValueError(f"{key} kommt aus den allgemeinen Einstellungen")
            if key not in settings.DEFAULTS:
                raise ValueError(f"unbekannte Einstellung {key}")
            wanted = type(settings.DEFAULTS[key])
            allowed = (int, float) if wanted is float else wanted  # 1 statt 1.0 ist in Ordnung
            if isinstance(value, bool) != (wanted is bool) or not isinstance(value, allowed):
                raise ValueError(f"{key}: erwartet {wanted.__name__}")

    async def save(self, change: dict) -> dict:
        """Ändert nur, was die Seite schickt; fremde Schlüssel in der Datei bleiben."""
        self._validate(change)
        self._write(change)
        return self.info()

    def sync_profile(self, name: str, language: str) -> None:
        """Charaktername und Sprache aus den allgemeinen Einstellungen ans Radar geben. Den Namen liest
        das Radar nur beim Start, ein neuer startet es deshalb neu."""
        voice = language if language in VOICE_LANGUAGES else "en"
        current = self.settings()
        if (current["name"], current["sprache"]) == (name, voice):
            return
        self._write({"name": name, "sprache": voice})
        if current["name"] != name and self.service:
            self._stop()
            self._start()

    def _write(self, change: dict) -> None:
        content = {**settings.read_file(), **change}
        _atomic_write(settings.FILE, json.dumps(content, indent=2, ensure_ascii=False))
        settings.reload()
        if self.service:
            self.service.reload()

    async def command(self, name: str, call: str = "") -> None:
        """Ein Knopf der NexBoard-Seite; `call` = Schlüssel der Boss-Ansage bei „ansage_testen“."""
        if name == RESTART:
            self._stop()
            if self.game:
                self._start()
            return
        if name not in COMMANDS:
            raise ValueError(f"unbekannter Befehl {name}")
        if not self.service:
            raise RuntimeError("Radar läuft nicht")
        COMMANDS[name](self.service, call)

    def deaths_between(self, start_ms: int, end_ms: int) -> list[dict]:
        """Tode eines Runs (Zeiten in ms seit 1970), für das NexLog."""
        return [d for d in self.deaths if start_ms <= d["t_ms"] <= end_ms]

    def fight_state(self) -> dict:
        """Kampfzustand für andere Programme auf diesem PC (GET /api/radar/kampf)."""
        return self.service.fight_state() if self.service else dict(NO_FIGHT)

    def field_bosses(self) -> list[dict]:
        """Feldbosse für die Seite „Termine“. Ohne laufendes Radar aus dem gespeicherten Stand."""
        if self.service:
            return field_bosses.overview(self.service.field_bosses.slots, self.service.world.zone)
        return field_bosses.overview(load_state(field_bosses.STATE_FILE), None)

    def map(self) -> dict:
        return self.service.map() if self.service else {"name": ""}

    def map_file(self, kind: str) -> Path | None:
        """Bild oder Teleporter-Symbol der gezeigten Karte, für die Overlay-Seite."""
        name = self.map()["name"]
        if not name or kind not in MAP_FILES:
            return None
        file = MAP_FILES[kind](GameMap(name))
        return file if file.exists() else None

    def _start(self) -> None:
        log.info("AION 2 läuft, starte Radar")
        self.service = self.new_service(self.settings()["name"])
        self.service.deaths = self.deaths
        self.service.parts = self.parts
        self.service.start()

    def _stop(self) -> None:
        if self.service:
            log.info("Radar wird beendet")
            self.service.stop()
            self.service = None

    async def _check_game(self, gone: float) -> float:
        """Radar mit dem Spiel starten und linger_s nach Spielende beenden. Gibt zurück, wie lange das
        Spiel schon weg ist."""
        if await self.game_running():
            if not self.game:
                self.game = True
                self._start()
            return 0
        if self.game:
            gone += self.poll_s
            if gone >= self.linger_s:
                self.game = False
                self._stop()
                await self.publish({"aktiv": False})
        return gone

    async def watch(self) -> None:
        """Modul-Aufgabe: Spiel alle poll_s prüfen, dazwischen Takt und Stand fürs Overlay."""
        gone, check_at = 0.0, 0.0
        try:
            while True:
                if time.monotonic() >= check_at:
                    check_at = time.monotonic() + self.poll_s
                    gone = await self._check_game(gone)
                if self.service:
                    self.service.tick()
                    await self.publish({"aktiv": True, **self.service.state()})
                await asyncio.sleep(TICK_S)
        finally:
            self.game = False
            self._stop()
            await self.publish({"aktiv": False})
