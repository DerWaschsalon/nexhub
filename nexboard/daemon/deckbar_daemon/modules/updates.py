"""Modul Updates: täglich nach neuen Versionen sehen, Installation mit einem Klick.

Für die Leiste setzt es den Zustand `update_available`: Eine Schalter-Kachel mit `bind: update_available`
leuchtet, solange NexBoard, A2Tools oder die Firmware einer verbundenen Leiste neuer zu haben ist.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from aiohttp import web
from nexcore import Context, ModuleInfo
from nexcore.errors import ApiError

from ..core.http import ok
from ..core.live import LiveHub
from ..state import State
from ..updates import Updates, firmware_in_repo, firmware_outdated
from .base import WebModule


class UpdatesModule(WebModule):
    info = ModuleInfo(
        "updates", "Updates", "system", "update",
        "Prüft täglich auf neue Versionen und neue Releases des A2Tools-Kerns, Installation mit "
        "einem Klick.",
        default=True, tags=("Wartung",),
    )
    ui_key = "updates"

    def __init__(self, ctx: Context, live: LiveHub, updates: Updates, state: State,
                 device_firmware: Callable[[], list[str]]) -> None:
        """device_firmware: Firmware-Stände der gerade verbundenen Leisten."""
        super().__init__(ctx, live)
        self.updates = updates
        self.state = state
        self.device_firmware = device_firmware
        updates.listeners.append(self.show_on_bar)

    def firmware(self) -> dict[str, Any]:
        """Firmware im Repo und die älteren Stände verbundener Leisten (die muss man selbst flashen)."""
        repo_fw = firmware_in_repo()
        return {"repo": repo_fw, "outdated": [fw for fw in self.device_firmware() if firmware_outdated(fw, repo_fw)]}

    async def show_on_bar(self) -> None:
        """Zustand für die Update-Kachel und die Web-UI; nach jeder Prüfung und wenn eine Leiste kommt oder geht."""
        outdated = bool(self.firmware()["outdated"])
        self.state.update(update_available=bool(self.updates.state["available"]) or outdated)
        await self.changed()

    def ui_info(self) -> dict[str, Any]:
        return {**self.updates.info(), "firmware": self.firmware()}

    async def start(self) -> None:
        self.spawn(self.updates.watch)

    def status(self) -> dict[str, Any]:
        u = self.updates.state
        return {"available": u.get("available"), "checked_at": u.get("checked_at"), "error": u.get("error")}

    def routes(self, router: web.UrlDispatcher) -> None:
        router.add_get("/api/updates", self.api_get)
        router.add_post("/api/updates/check", self.api_check)
        router.add_post("/api/updates/run", self.api_run)
        router.add_post("/api/updates/news/seen", self.api_news_seen)

    async def api_get(self, request: web.Request) -> web.Response:
        return web.json_response(self.ui_info())

    async def api_check(self, request: web.Request) -> web.Response:
        await self.updates.check()
        return web.json_response(self.ui_info())

    async def api_news_seen(self, request: web.Request) -> web.Response:
        """„Neu in dieser Version“ als gelesen: Die Liste verschwindet bis zum nächsten Update."""
        self.updates.dismiss_news()
        await self.changed()
        return web.json_response(self.ui_info())

    async def api_run(self, request: web.Request) -> web.Response:
        try:
            result = await self.updates.run()
        except (RuntimeError, OSError) as e:
            raise ApiError(500, str(e)) from e
        return ok(result=result)
