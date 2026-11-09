"""Modul Radar: Hidden Cubes, Karte, Boss-Warnungen und PvP als Widgets im Overlay."""
from __future__ import annotations

from typing import Any

from aiohttp import web
from nexcore import Context, ModuleInfo
from nexcore.errors import ApiError

from ..boss_effekte import BossEffekte
from ..core.http import ok, read_object
from ..core.live import LiveHub
from ..radar import Radar
from .base import WebModule


class RadarModule(WebModule):
    info = ModuleInfo(
        "aion2.radar", "AION 2 · Radar", "ingame", "radar",
        "Hidden Cubes, Karte, Boss-Warnungen und PvP der Sitzung als Widgets im Overlay, Feldbosse und "
        "Vertraute in der Web-UI. Läuft mit AION 2 und liest den Server-Verkehr passiv mit (tcpdump).",
        tags=("AION 2", "Desktop"),
    )

    def __init__(self, ctx: Context, live: LiveHub, radar: Radar, boss_effects: BossEffekte) -> None:
        super().__init__(ctx, live)
        self.radar = radar
        self.boss_effects = boss_effects

    async def start(self) -> None:
        self.spawn(self.radar.watch)

    def status(self) -> dict[str, Any]:
        return {"laeuft": self.radar.laeuft, "spiel": self.radar.spiel, "aufnahme": self.radar.aufnahme}

    def routes(self, router: web.UrlDispatcher) -> None:
        router.add_get("/api/radar", self.api_get)
        router.add_put("/api/radar", self.api_put)
        router.add_post("/api/radar/befehl", self.api_command)
        router.add_get("/api/radar/uebersicht", self.api_overview)
        router.add_get("/api/radar/kampf", self.api_fight)

    def overlay_routes(self, router: web.UrlDispatcher) -> None:
        """Auf dem Port der Overlay-Seite: die Karte."""
        router.add_get("/api/radar/karte", self.api_map)
        router.add_get("/api/radar/karte/{art}", self.api_map_file)

    async def api_get(self, request: web.Request) -> web.Response:
        return web.json_response(self.radar.info())

    async def api_put(self, request: web.Request) -> web.Response:
        try:
            return web.json_response(await self.radar.speichern(await read_object(request)))
        except ValueError as e:
            raise ApiError(400, str(e)) from e

    async def api_command(self, request: web.Request) -> web.Response:
        data = await read_object(request)
        if "befehl" not in data:
            raise ApiError(400, "erwartet {befehl}")
        try:
            await self.radar.befehl(str(data["befehl"]), str(data.get("ruf", "")))
        except ValueError as e:
            raise ApiError(400, str(e)) from e
        except RuntimeError as e:
            raise ApiError(409, str(e)) from e
        return ok(**self.radar.info())

    async def api_fight(self, request: web.Request) -> web.Response:
        return web.json_response({**self.radar.kampf(), **await self.boss_effects.aktuell()})

    async def api_overview(self, request: web.Request) -> web.Response:
        return web.json_response(self.radar.uebersicht())

    async def api_map(self, request: web.Request) -> web.Response:
        return web.json_response(self.radar.karte())

    async def api_map_file(self, request: web.Request) -> web.FileResponse:
        path = self.radar.kartendatei(request.match_info["art"])
        if not path:
            raise web.HTTPNotFound()
        return web.FileResponse(path)
