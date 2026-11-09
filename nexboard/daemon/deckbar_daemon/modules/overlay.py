"""Modul Overlay: Meter und Widgets über dem Spiel."""
from __future__ import annotations

from typing import Any

from aiohttp import web
from nexcore import Context, ModuleInfo
from nexcore.errors import ApiError

from ..core.http import ok, read_object
from ..core.live import OPENED, LiveHub
from ..overlay import UNIT, Overlay
from ..state import State
from .base import WebModule


class OverlayModule(WebModule):
    info = ModuleInfo(
        "aion2.overlay", "AION 2 · Overlay", "games", "layers-triple",
        "Meter und Widgets über dem Spiel: frei verschiebbar, klickdurchlässig, mit Boss-Leiste, "
        "Event-Timern und Namenseffekt.",
        requires=("aion2.dps",), tags=("AION 2", "Desktop"),
    )
    ui_key = "overlay"

    def __init__(self, ctx: Context, live: LiveHub, overlay: Overlay, state: State) -> None:
        super().__init__(ctx, live)
        self.overlay = overlay
        overlay.listeners.append(self.changed)
        overlay.ui_watching = lambda: live.watching
        state.subscribe(overlay.on_state)

    def ui_info(self) -> dict[str, Any]:
        return self.overlay.info()

    async def start(self) -> None:
        self.spawn(self.overlay.watch)
        self.on(OPENED, self.refresh)  # ohne offene Web-UI fragt watch() nicht nach dem Dienst
        await self.overlay.on_module(True)

    async def stop(self) -> None:
        await self.overlay.on_module(False)

    async def refresh(self, _: object = None) -> None:
        await self.overlay.refresh_unit()

    def status(self) -> dict[str, Any]:
        return {"unit": self.overlay.unit, "clients": len(self.overlay.clients)}

    def routes(self, router: web.UrlDispatcher) -> None:
        router.add_get("/api/overlay", self.api_get)
        router.add_put("/api/overlay", self.api_put)
        router.add_post("/api/overlay/command", self.api_command)
        router.add_post("/api/overlay/restart", self.api_restart)

    async def api_get(self, request: web.Request) -> web.Response:
        if self.active:
            await self.refresh()
        return web.json_response(self.overlay.info())

    async def api_put(self, request: web.Request) -> web.Response:
        await self.overlay.update(await read_object(request))
        return ok(**self.overlay.info())

    async def api_command(self, request: web.Request) -> web.Response:
        cmd = (await read_object(request)).get("cmd")
        if not isinstance(cmd, str):
            raise ApiError(400, "erwartet {cmd}")
        try:
            await self.overlay.command(cmd)
        except ValueError as e:
            raise ApiError(400, str(e)) from e
        except RuntimeError as e:
            raise ApiError(409, str(e)) from e
        return ok()

    async def api_restart(self, request: web.Request) -> web.Response:
        """Overlay-Programm neu starten (nach Änderungen an Monitor oder GPU)."""
        self.require_active()
        code, out = await self.overlay.systemctl("restart", UNIT)
        await self.refresh()
        await self.changed()
        if code:
            raise ApiError(500, out or "Neustart ging nicht")
        return ok(**self.overlay.info())
