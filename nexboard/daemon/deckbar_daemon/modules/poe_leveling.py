"""Modul PoE 1 · Leveling-Guide: der Act Tracker von Exile-UI auf der Touch-Leiste und in der Web-UI.

Die Leiste zeigt den aktuellen Schritt auf der Guide-Kachel und springt auf ihre Seite, solange PoE läuft
und der Guide nicht zu Ende ist. Tippen links = zurück, rechts = weiter, rechts lange = zur aktuellen Zone.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import aiohttp
from aiohttp import web
from nexcore import Context, ModuleInfo
from nexcore.errors import ApiError
from nexcore.settings import SettingsStore

from ..core.http import ok, read_object
from ..core.live import LiveHub
from ..core.topics import DECK_PAGE, GAME_STARTED, GAME_STOPPED, POE_LOG, TILE_EVENT, TileEvent
from ..poe.client_log import LevelUp, ZoneEntered
from ..poe.games import POE1
from ..poe.leveling import pob
from ..poe.leveling.data import DATA_DIR
from ..poe.leveling.leveling import Leveling
from ..poe.leveling.settings import LevelingSettings
from ..poe.session import GameState, PoeLogMessage
from ..state import State
from .base import WebModule

POBBIN_TIMEOUT_S = 10
ZONE_CHECK_S = 0.5  # wie oft „steht man in der Zielzone?“ geprüft wird, solange das Spiel läuft
# Tippen auf die Guide-Kachel → Befehl
TILE_COMMANDS = {("button_press", "back"): "back", ("button_press", "next"): "next", ("long_press", "next"): "skip"}
COMMANDS = ("next", "back", "skip", "reset")


class PoeLevelingModule(WebModule):
    game = POE1
    info = ModuleInfo(
        "poe1.leveling", "PoE 1 · Leveling-Guide", "ingame", "format-list-bulleted",
        "Act Tracker nach Exile-UI: aktueller Schritt mit Gems aus dem PoB-Build auf der Touch-Leiste, "
        "schaltet beim Betreten der Zielzone selbst weiter.",
        requires=("poe1.client",), tags=("PoE 1", "Leiste"),
    )
    ui_key = "leveling"

    def __init__(self, ctx: Context, live: LiveHub, state: State, game_state: GameState, config_dir: Path) -> None:
        super().__init__(ctx, live)
        self.state = state
        self.game_state = game_state
        store = SettingsStore(config_dir / f"{self.info.id}.yaml", LevelingSettings,
                              header=f"{self.info.name} – wird von der Web-UI überschrieben")
        self.leveling = Leveling(store, ctx.paths.data / self.game.id / "leveling.json")
        self.page_shown: str | None = None  # Seite, um die das Modul die Leiste gebeten hat

    @property
    def store(self) -> SettingsStore[Any]:
        return self.leveling.store

    def ui_info(self) -> dict[str, Any]:
        return {**self.leveling.view(), "running": self.game_state.running}

    # ------------------------------------------------------------ Lebenszyklus
    async def start(self) -> None:
        if self.game_state.zone:
            self.leveling.on_zone(self.game_state.zone)
        for up in self.game_state.levels.values():
            self.leveling.on_level(up)
        self.on(POE_LOG, self.on_log)
        self.on(GAME_STARTED, self.on_game)
        self.on(GAME_STOPPED, self.on_game)
        self.on(TILE_EVENT, self.on_tile)
        self.spawn(self._watch_zone)
        await self.push()

    async def _watch_zone(self) -> None:
        while True:
            await asyncio.sleep(ZONE_CHECK_S)
            if self.game_state.running and self.leveling.check_zone():
                await self.push()

    async def stop(self) -> None:
        self.state.update(guide=None)
        await self._ask_page(None)

    async def on_log(self, message: PoeLogMessage) -> None:
        if message.game != self.game.id:
            return
        if isinstance(message.event, ZoneEntered):
            self.leveling.on_zone(message.event)
        elif isinstance(message.event, LevelUp):
            self.leveling.on_level(message.event)
        await self.push()

    async def on_game(self, name: str) -> None:
        if name == self.game.id:
            await self.push()

    async def on_tile(self, event: TileEvent) -> None:
        command = TILE_COMMANDS.get((event.event, event.part or ""))
        if event.item_type == "guide" and command:
            await self.run_command(command)

    # ------------------------------------------------------------ Ausgabe
    async def push(self) -> None:
        """Neuer Stand an Leiste und Web-UI; die Seite der Leiste folgt Spiel und Guide."""
        self.state.update(guide=self.leveling.device())
        await self.changed()
        show = self.game_state.running and self.leveling.settings.active and not self.leveling.finished()
        await self._ask_page(self.leveling.settings.page if show else None)

    async def _ask_page(self, page: str | None) -> None:
        if page != self.page_shown:
            self.page_shown = page
            await self.ctx.bus.emit(DECK_PAGE, page)

    async def run_command(self, command: str) -> None:
        self.leveling.command(command)
        await self.push()

    async def update_settings(self, patch: dict[str, Any]) -> None:
        await super().update_settings(patch)
        self.leveling.rebuild()
        await self.push()

    def status(self) -> dict[str, Any]:
        view = self.leveling.device()
        return {"step": view["step"], "text": f"Schritt {view['step']}"}

    # ------------------------------------------------------------ Web-API
    def routes(self, router: web.UrlDispatcher) -> None:
        base = f"/api/{self.game.id}/leveling"
        router.add_get(base, self.api_get)
        router.add_post(f"{base}/command", self.api_command)
        router.add_post(f"{base}/import", self.api_import)
        router.add_post(f"{base}/default-guide", self.api_default_guide)
        router.add_put(f"{base}/gem-sources", self.api_gem_sources)
        router.add_static(f"/static/{self.game.id}/icons/", DATA_DIR / "icons")
        router.add_static(f"/static/{self.game.id}/layouts/", DATA_DIR / "hints")

    async def api_get(self, request: web.Request) -> web.Response:
        return web.json_response(self.ui_info())

    async def api_command(self, request: web.Request) -> web.Response:
        command = (await read_object(request)).get("cmd")
        if command not in COMMANDS:
            raise ApiError(400, f"erwartet cmd: {' | '.join(COMMANDS)}")
        self.require_active()
        await self.run_command(str(command))
        return ok(**self.ui_info())

    async def api_import(self, request: web.Request) -> web.Response:
        """PoB-Code, pobb.in-Link oder Guide-JSON."""
        text = (await read_object(request)).get("code")
        if not isinstance(text, str) or not text.strip():
            raise ApiError(400, "erwartet {code}")
        try:
            if pob.is_pobbin(text):
                text = await self._fetch_pobbin(text)
            kind = self.leveling.import_code(text)
        except pob.PobError as e:
            raise ApiError(422, str(e)) from e
        await self.push()
        return ok(kind=kind, **self.ui_info())

    @staticmethod
    async def _fetch_pobbin(link: str) -> str:
        timeout = aiohttp.ClientTimeout(total=POBBIN_TIMEOUT_S)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as http, http.get(pob.pobbin_raw_url(link)) as response:
                response.raise_for_status()
                return await response.text()
        except (aiohttp.ClientError, TimeoutError) as e:
            raise pob.PobError(f"pobb.in nicht erreichbar: {e}") from e

    async def api_default_guide(self, request: web.Request) -> web.Response:
        self.leveling.use_default_guide()
        await self.push()
        return ok(**self.ui_info())

    async def api_gem_sources(self, request: web.Request) -> web.Response:
        sources = (await read_object(request)).get("sources")
        if not isinstance(sources, dict) or not all(isinstance(v, int) for v in sources.values()):
            raise ApiError(400, "erwartet {sources: {gem: akt}}")
        self.leveling.set_gem_sources({str(k): v for k, v in sources.items()})
        await self.push()
        return ok(**self.ui_info())
