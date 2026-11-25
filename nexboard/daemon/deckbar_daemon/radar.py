"""AION 2 · Radar: läuft im Daemon, solange AION 2 läuft, und zeigt sich als Widgets im Overlay.

Mitschnitt und Auswertung stecken in aion2/ (RadarService, ohne Fenster). Der Daemon ruft dessen Takt
mehrmals pro Sekunde auf und schickt den Stand als Overlay-Ereignis „radar“. Das Radar-Widget zeigt sich
dort nur, solange ein Cube in Sicht ist.

Jedes der drei Module (Radar, Boss-Warnungen, Feldbosse) hat seine Einstellungen in <Modul>.yaml; der Dienst
bekommt sie als ein Settings-Objekt. Die Schlüssel von info() sind die der NexBoard-Seite.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from nexcore import SettingsStore
from pydantic import BaseModel

from .aion2 import field_bosses
from .aion2.callouts import page_list
from .aion2.gamedata import load_state
from .aion2.maps import GameMap
from .aion2.rules import SWITCHES
from .aion2.service import CUBES, DEATHS_KEPT, FIELD_BOSSES, PARTS, WARNINGS, RadarService
from .aion2.settings import FieldBossSettings, RadarSettings, Settings, WarningSettings
from .capture import Capture
from .core.packets import CaptureSource
from .game_process import aion2_running

log = logging.getLogger(__name__)

# Teil → Modell seiner Einstellungen; die Datei heißt wie das Modul (aion2.<Teil>.yaml)
MODELS: dict[str, type[BaseModel]] = {CUBES: RadarSettings, WARNINGS: WarningSettings, FIELD_BOSSES: FieldBossSettings}
SETTINGS_HEADER = "Einstellungen des Moduls, geschrieben von der NexBoard-Web-UI"
TICK_S = 0.2  # so oft zeichnen die Widgets neu, Warnungen zählen in Zehntelsekunden
VOICE_LANGUAGES = ("de", "en")  # Ansagen und Warnungen gibt es nur auf Deutsch und Englisch
# Voreinstellungen der Seite „Warnungen“: was jede setzt. Art der Ansage, Wellenton und die Einzelheiten je
# Dungeon, Boss und Ruf stehen unter „Erweitert“ und bleiben beim Wechsel, wie sie sind.
WARNING_PRESETS: dict[str, dict[str, Any]] = {
    "aus": {"enabled": False},
    "wichtig": {"enabled": True, "only_me": True},  # nur, was dich betrifft (Standard)
    "alles": {"enabled": True, "only_me": False},  # auch Angriffe und Effekte auf andere Spieler
}
OWN_PRESET = "eigene"
FROM_CAPTURE = "capture"  # Einstellung source: Pakete vom Mitschnitt der Kampfdaten statt von tcpdump
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
    def __init__(self, publish: Callable[[dict], Awaitable[None]], config_dir: Path,
                 game_running: Callable[[], Awaitable[bool]] = _game_running,
                 service: Callable[..., Any] = RadarService, poll_s: float = 5, linger_s: float = 30,
                 capture: Capture | None = None) -> None:
        self.publish = publish  # Overlay-Ereignis „radar“
        self.stores: dict[str, SettingsStore[Any]] = {
            part: SettingsStore(config_dir / f"aion2.{part}.yaml", model, header=SETTINGS_HEADER)
            for part, model in MODELS.items()}
        self.settings = Settings()  # hält auch der laufende Dienst; _use_stores() setzt neue Werte ein
        self._use_stores()
        self.name, self.language = "", VOICE_LANGUAGES[0]  # aus den allgemeinen Einstellungen (sync_profile)
        self.game_running = game_running
        self.new_service = service
        self.capture = capture  # Mitschnitt der Kampfdaten, falls das Radar seine Pakete von dort nimmt
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

    def _use_stores(self) -> None:
        self.settings.radar = self.stores[CUBES].value
        self.settings.warnings = self.stores[WARNINGS].value
        self.settings.field_bosses = self.stores[FIELD_BOSSES].value

    def warning_preset(self) -> str:
        """Welche Voreinstellung zu den Einstellungen passt; „eigene“, wenn keine."""
        current = self.settings.warnings.model_dump()
        for name, values in WARNING_PRESETS.items():
            if all(current[key] == value for key, value in values.items()):
                return name
        return OWN_PRESET

    def info(self) -> dict:
        return {"meldungen": SWITCHES, "ansagen": self.callouts,
                "karten": [m.name for m in GameMap.all()], "presets": WARNING_PRESETS,
                "preset": self.warning_preset(),
                "laeuft": self.running, "aufnahme": self.recording, "spiel": self.game, "fehler": self.error}

    def save(self, part: str, value: BaseModel) -> None:
        """Geprüfte Einstellungen eines Moduls speichern und dem laufenden Dienst geben."""
        source = self.settings.radar.source
        self.stores[part].save(value)
        self._use_stores()
        if not self.service:
            return
        if self.settings.radar.source != source:
            self._restart()  # die Quelle steht beim Start fest
        else:
            self.service.reload()

    def sync_profile(self, name: str, language: str) -> None:
        """Charaktername und Sprache aus den allgemeinen Einstellungen. Den Namen liest das Radar nur beim
        Start, ein neuer startet es deshalb neu."""
        voice = language if language in VOICE_LANGUAGES else "en"
        renamed = name != self.name
        self.name, self.language = name, voice
        if self.service and renamed:
            self._restart()
        elif self.service:
            self.service.reload(voice)

    def _restart(self) -> None:
        self._stop()
        self._start()

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
        from_capture = self.capture is not None and self.settings.radar.source == FROM_CAPTURE
        source = {"source": CaptureSource(self.capture)} if from_capture else {}
        self.service = self.new_service(self.name, settings=self.settings, language=self.language, **source)
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
