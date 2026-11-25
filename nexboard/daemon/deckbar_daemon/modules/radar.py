"""Die Module des Radars: Hidden Cubes und Karte, Boss-Warnungen, Feldbosse. Sie teilen sich einen
RadarService (ein Mitschnitt, eine Welt); er läuft, solange eines von ihnen an ist."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, ClassVar

from aiohttp import web
from nexcore import Context, ModuleInfo, SettingsStore
from nexcore.errors import ApiError
from pydantic import BaseModel

from ..aion2.service import CUBES, FIELD_BOSSES, WARNINGS
from ..core.http import ok, read_object
from ..core.live import LiveHub
from ..overlay_layout import WidgetSpec
from ..radar import Radar
from .base import WebModule


class RadarPart(WebModule):
    """Ein Teil des Radars als Modul: schaltet seinen Teil am gemeinsamen Dienst."""

    part: ClassVar[str]

    def __init__(self, ctx: Context, live: LiveHub, radar: Radar) -> None:
        super().__init__(ctx, live)
        self.radar = radar

    async def start(self) -> None:
        self.radar.enable(self.part)

    async def stop(self) -> None:
        await self.radar.disable(self.part)

    @property
    def store(self) -> SettingsStore[Any]:
        return self.radar.stores[self.part]

    def save_settings(self, value: BaseModel) -> None:
        self.radar.save(self.part, value)

    def status(self) -> dict[str, Any]:
        return {"laeuft": self.radar.running, "spiel": self.radar.game, "aufnahme": self.radar.recording,
                "fehler": self.radar.error}


class RadarModule(RadarPart):
    info = ModuleInfo(
        "aion2.radar", "AION 2 · Radar", "aion2", "radar",
        "Hidden Cubes und Karte als Widgets im Overlay, mit Ton bei einem neuen Cube. Läuft mit AION 2 und "
        "liest den Server-Verkehr passiv mit (tcpdump).",
        tags=("AION 2", "Desktop"),
    )
    part = CUBES
    overlay_widgets = (
        WidgetSpec("cube", "Cube-Radar", "Kleines Radar mit Richtung und Abstand; zeigt sich nur, solange ein "
                   "Hidden Cube in Sicht ist"),
        WidgetSpec("map", "Karte", "Karte mit Cubes, Spawnpunkten und Teleportern; die Kartenbilder kommen aus "
                   "dem Plugin Pet Soul Tracker", enabled=False, size=(340, 300), profiles=()),
    )

    def routes(self, router: web.UrlDispatcher) -> None:
        """Stand und Knöpfe aller Radar-Module (ein gemeinsamer Dienst)."""
        router.add_get("/api/radar", self.api_get)
        router.add_post("/api/radar/befehl", self.api_command)

    def overlay_routes(self, router: web.UrlDispatcher) -> None:
        """Auf dem Port der Overlay-Seite: die Karte."""
        router.add_get("/api/radar/karte", self.api_map)
        router.add_get("/api/radar/karte/{art}", self.api_map_file)

    async def api_get(self, request: web.Request) -> web.Response:
        return web.json_response(self.radar.info())

    async def api_command(self, request: web.Request) -> web.Response:
        data = await read_object(request)
        if "befehl" not in data:
            raise ApiError(400, "erwartet {befehl}")
        try:
            await self.radar.command(str(data["befehl"]), str(data.get("ruf", "")))
        except ValueError as e:
            raise ApiError(400, str(e)) from e
        except RuntimeError as e:
            raise ApiError(409, str(e)) from e
        return ok(**self.radar.info())

    async def api_map(self, request: web.Request) -> web.Response:
        return web.json_response(self.radar.map())

    async def api_map_file(self, request: web.Request) -> web.FileResponse:
        path = self.radar.map_file(request.match_info["art"])
        if not path:
            raise web.HTTPNotFound()
        return web.FileResponse(path)


class WarningsModule(RadarPart):
    info = ModuleInfo(
        "aion2.warnings", "AION 2 · Boss-Warnungen", "aion2", "bell-alert",
        "Warnt vor Boss-Mechaniken und sagt an, was zu tun ist: Mechaniken je Dungeon, Boss-Ansagen, „Jetzt "
        "staggern“, Fläche unter dir, wenig HP. Als Widget im Overlay und gesprochen.",
        split_from="aion2.radar", tags=("AION 2", "Desktop"),
    )
    part = WARNINGS
    overlay_widgets = (
        WidgetSpec("warnings", "Boss-Warnungen", "Nur während einer Warnung; was gewarnt wird, steht unter "
                   "Warnungen"),
    )

    def __init__(self, ctx: Context, live: LiveHub, radar: Radar,
                 effects: Callable[[], Awaitable[dict[str, Any]]]) -> None:
        super().__init__(ctx, live, radar)
        self.effects = effects  # Übergang: die Route nannte bisher auch die Effekte (jetzt /api/m/aion2.effects)

    def routes(self, router: web.UrlDispatcher) -> None:
        router.add_get("/api/radar/kampf", self.api_fight)

    async def api_fight(self, request: web.Request) -> web.Response:
        """Für andere Programme auf diesem PC: Boss groggy und laufende Warnungen."""
        return web.json_response({**self.radar.fight_state(), **await self.effects()})


class FieldBossModule(RadarPart):
    info = ModuleInfo(
        "aion2.field_bosses", "AION 2 · Feldbosse", "aion2", "timer-outline",
        "Respawn-Timer der Feldbosse auf der Seite Termine, mit Ansage 5 Minuten vorher und beim Respawn; "
        "dazu die Ansage für den Riss.",
        requires=("aion2.schedule",), split_from="aion2.radar", tags=("AION 2",),
    )
    part = FIELD_BOSSES

    def routes(self, router: web.UrlDispatcher) -> None:
        router.add_get("/api/radar/feldbosse", self.api_field_bosses)

    async def api_field_bosses(self, request: web.Request) -> web.Response:
        return web.json_response({"feldbosse": self.radar.field_bosses()})
