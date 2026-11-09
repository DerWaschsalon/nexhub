"""Modul Updates: täglich nach neuen Versionen sehen, Installation mit einem Klick."""
from __future__ import annotations

from typing import Any

from aiohttp import web
from nexcore import Context, ModuleInfo
from nexcore.errors import ApiError

from ..core.http import ok
from ..core.live import LiveHub
from ..updates import Updates
from .base import WebModule


class UpdatesModule(WebModule):
    info = ModuleInfo(
        "updates", "Updates", "system", "update",
        "Prüft täglich auf neue Versionen und neue Releases des A2Tools-Kerns, Installation mit "
        "einem Klick.",
        default=True, tags=("Wartung",),
    )
    ui_key = "updates"

    def __init__(self, ctx: Context, live: LiveHub, updates: Updates) -> None:
        super().__init__(ctx, live)
        self.updates = updates
        updates.listeners.append(self.changed)

    def ui_info(self) -> dict[str, Any]:
        return self.updates.info()

    async def start(self) -> None:
        self.spawn(self.updates.watch)

    def status(self) -> dict[str, Any]:
        u = self.updates.state
        return {"available": u.get("available"), "checked_at": u.get("checked_at"), "error": u.get("error")}

    def routes(self, router: web.UrlDispatcher) -> None:
        router.add_get("/api/updates", self.api_get)
        router.add_post("/api/updates/check", self.api_check)
        router.add_post("/api/updates/run", self.api_run)

    async def api_get(self, request: web.Request) -> web.Response:
        return web.json_response(self.updates.info())

    async def api_check(self, request: web.Request) -> web.Response:
        await self.updates.check()
        return web.json_response(self.updates.info())

    async def api_run(self, request: web.Request) -> web.Response:
        try:
            result = await self.updates.run()
        except (RuntimeError, OSError) as e:
            raise ApiError(500, str(e)) from e
        return ok(result=result)
