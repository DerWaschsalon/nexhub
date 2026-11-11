"""Modul Termine: feste Termine der Server und eigene Ereignisse, für die Web-UI und das Overlay-Widget."""
from __future__ import annotations

import asyncio
from typing import Any

from aiohttp import web
from nexcore import Context, ModuleInfo
from nexcore.settings import SettingsStore

from ..core.live import LiveHub
from ..core.topics import SCHEDULE
from ..overlay_layout import WidgetSpec
from ..schedule import Schedule
from .base import WebModule

PUSH_S = 10  # so oft geht die Liste ans Overlay; Termine wechseln nur zur vollen Minute


class ScheduleModule(WebModule):
    info = ModuleInfo(
        "aion2.schedule", "AION 2 · Termine", "ingame", "calendar-clock",
        "Feste Termine der Server (Riss, Shugo-Fest, Resets …) und eigene Ereignisse mit Countdown, "
        "in der Web-UI und als Widget im Overlay.",
        tags=("AION 2",),
    )
    overlay_widgets = (
        WidgetSpec("timers", "Termine", "Countdown bis zum nächsten Termin; welche, steht unter Termine",
                   enabled=False),
    )

    def __init__(self, ctx: Context, live: LiveHub, schedule: Schedule) -> None:
        super().__init__(ctx, live)
        self.schedule = schedule

    @property
    def store(self) -> SettingsStore[Any]:
        return self.schedule.store

    async def start(self) -> None:
        self.spawn(self._push_loop)

    async def _push_loop(self) -> None:
        while True:
            await self._push()
            await asyncio.sleep(PUSH_S)

    async def _push(self) -> None:
        await self.ctx.bus.emit(SCHEDULE, self.schedule.visible())

    async def stop(self) -> None:
        await self.ctx.bus.emit(SCHEDULE, [])  # Widget leeren

    async def update_settings(self, patch: dict[str, Any]) -> None:
        await super().update_settings(patch)
        await self._push()  # das Widget soll die Änderung sofort zeigen, nicht erst nach PUSH_S

    def routes(self, router: web.UrlDispatcher) -> None:
        router.add_get("/api/schedule", self.api_get)

    async def api_get(self, request: web.Request) -> web.Response:
        return web.json_response({"entries": self.schedule.entries()})
