"""Sitzung eines Spiels: läuft es gerade, und was steht neu in seinem Client.txt.

Meldet beides auf dem Bus (game.started/game.stopped über nexcore.GameWatch, neue Zeilen als POE_LOG),
damit jedes PoE-Modul nur abonniert, statt selbst /proc und Client.txt zu lesen.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from nexcore import EventBus
from nexcore.gamewatch import GameWatch

from ..core.topics import POE_LOG
from .client_log import ClientLog, LevelUp, LogEvent, ZoneEntered
from .games import PoeGame, RunningGame

log = logging.getLogger("nexboard.poe")

LOG_POLL_S = 0.5  # so oft nach neuen Zeilen sehen: Zonenwechsel sollen sofort auf der Leiste stehen
GAME_POLL_EVERY = 10  # /proc nur jede zehnte Runde (5 s), das ist teurer als ein stat()


@dataclass(frozen=True)
class PoeLogMessage:
    game: str  # PoeGame.id
    event: LogEvent


class GameState(Protocol):
    """Was ein PoE-Modul von der Sitzung braucht, wenn es mitten im Spiel eingeschaltet wird."""
    @property
    def running(self) -> bool: ...
    zone: ZoneEntered | None
    levels: dict[str, LevelUp]


class PoeSession:
    def __init__(self, bus: EventBus, game: PoeGame, client_txt: Callable[[], str]) -> None:
        self.bus = bus
        self.game = game
        self.client_txt = client_txt  # Einstellung: Pfad zu Client.txt, leer = selbst suchen
        self.watch = GameWatch(bus, game.id, self._find)
        self.found: RunningGame | None = None
        self.log: ClientLog | None = None
        self.zone: ZoneEntered | None = None
        self.levels: dict[str, LevelUp] = {}  # letzter Aufstieg je Charakter, zuletzt aufgestiegener am Ende

    @property
    def running(self) -> bool:
        return bool(self.watch.running)

    def _find(self) -> bool:
        self.found = self.game.find()
        return self.found is not None

    def path(self) -> Path | None:
        """Wo Client.txt liegt: Einstellung, sonst Ordner des laufenden Spiels, sonst Steam."""
        if self.client_txt():
            return Path(self.client_txt()).expanduser()
        if self.found and self.found.install:
            return self.game.client_txt(self.found.install)
        return self.game.steam_client_txt()

    async def run(self) -> None:
        await self._follow()  # einmal lesen, auch ohne Spiel: wo man zuletzt war, zeigt die Web-UI gleich
        tick = 0
        while True:
            if tick % GAME_POLL_EVERY == 0:
                await self.watch.check()
            tick += 1
            if self.watch.running:
                await self._follow()
            else:
                self.log = None  # beim nächsten Start neu öffnen (Datei kann neu angelegt sein)
            await asyncio.sleep(LOG_POLL_S)

    async def _follow(self) -> None:
        if self.log is None:
            path = self.path()
            if path is None or not path.is_file():
                return
            log.info("%s: lese %s", self.game.name, path)
            self.log = ClientLog(path)
            events = self.log.open()
        else:
            events = self.log.read_new()
        for event in events:
            await self._publish(event)

    async def _publish(self, event: LogEvent) -> None:
        if isinstance(event, ZoneEntered):
            self.zone = event
        else:
            self.levels.pop(event.character, None)  # ans Ende: die Reihenfolge sagt, wer zuletzt aufstieg
            self.levels[event.character] = event
        await self.bus.emit(POE_LOG, PoeLogMessage(self.game.id, event))
