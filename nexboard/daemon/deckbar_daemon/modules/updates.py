"""Modul Updates: täglich nach neuen Versionen sehen, Installation mit einem Klick.

Liegt etwas Neues bereit (NexBoard, A2Tools oder Firmware einer verbundenen Leiste), meldet das Modul es
an drei Stellen: Zustand `update_available` (die Leiste zeigt dann oben rechts „Update verfügbar“),
Web-UI und einmal je neuem Stand eine Desktop-Benachrichtigung.
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from aiohttp import web
from nexcore import Context, ModuleInfo
from nexcore.errors import ApiError

from .. import desktop
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
                 device_firmware: Callable[[], list[str]], web_url: Callable[[], str] | None) -> None:
        """device_firmware: Firmware-Stände der gerade verbundenen Leisten.
        web_url: Adresse der Web-UI; None = keine Desktop-Benachrichtigung (Testinstanzen)."""
        super().__init__(ctx, live)
        self.updates = updates
        self.state = state
        self.device_firmware = device_firmware
        self.web_url = web_url
        self._announced: list[str] = []  # zuletzt gemeldeter Stand, damit er nicht täglich neu kommt
        self._notice: asyncio.Task[None] | None = None
        updates.listeners.append(self.announce)

    def firmware(self) -> dict[str, Any]:
        """Firmware im Repo und die älteren Stände verbundener Leisten (die muss man selbst flashen)."""
        repo_fw = firmware_in_repo()
        return {"repo": repo_fw, "outdated": [fw for fw in self.device_firmware() if firmware_outdated(fw, repo_fw)]}

    def news(self) -> list[str]:
        """Was neuer zu haben ist, eine Zeile je Teil; leer heißt alles aktuell."""
        u = self.updates.state
        repo, a2 = u.get("deckbar") or {}, u.get("a2tools") or {}
        lines = []
        behind = repo.get("behind") or 0
        if behind:
            lines.append(f"NexBoard: {behind} neue{'r' if behind == 1 else ''} Commit{'' if behind == 1 else 's'}")
        if a2.get("newer"):
            lines.append(f"A2Tools {a2.get('latest')} (bisher {a2.get('current')})")
        fw = self.firmware()
        lines += [f"Leiste: Firmware {old}, neu {fw['repo']} (selbst flashen)" for old in fw["outdated"]]
        return lines

    async def announce(self) -> None:
        """Nach jeder Prüfung und wenn eine Leiste kommt oder geht: Leiste, Web-UI und Desktop."""
        if not self.active:
            return
        news = self.news()
        self.state.update(update_available=bool(news))
        await self.changed()
        if news and news != self._announced and self.web_url:
            self._show_notice(news, self.web_url() + "#/updates")
        self._announced = news

    def _show_notice(self, news: list[str], url: str) -> None:
        # Eine ältere Benachrichtigung, die noch auf einen Klick wartet, wird durch die neue ersetzt
        if self._notice and not self._notice.done():
            self._notice.cancel()
        self._notice = asyncio.ensure_future(desktop.notify("Update verfügbar", "\n".join(news), "Updates anzeigen", url))

    async def stop(self) -> None:
        self.state.update(update_available=False)
        if self._notice:
            self._notice.cancel()

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

    async def api_get(self, request: web.Request) -> web.Response:
        return web.json_response(self.ui_info())

    async def api_check(self, request: web.Request) -> web.Response:
        await self.updates.check()
        return web.json_response(self.ui_info())

    async def api_run(self, request: web.Request) -> web.Response:
        try:
            result = await self.updates.run()
        except (RuntimeError, OSError) as e:
            raise ApiError(500, str(e)) from e
        return ok(result=result)
