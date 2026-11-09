"""Gemeinsames aller Daemon-Module: Routen in der Web-API und Live-Meldungen an die Web-UI."""
from __future__ import annotations

from typing import Any, ClassVar

from aiohttp import web
from nexcore import Context, Module
from nexcore.errors import ApiError

from ..core.live import LiveHub


class WebModule(Module):
    # Live-Meldung {"type": ui_key, ui_key: ui_info()} und gleichnamiger Teil der Begrüßung
    ui_key: ClassVar[str | None] = None

    def __init__(self, ctx: Context, live: LiveHub) -> None:
        super().__init__(ctx)
        self.live = live
        if self.ui_key:
            live.section(self.ui_key, self.ui_info)

    def ui_info(self) -> Any:
        return None

    async def changed(self) -> None:
        if self.ui_key:
            await self.live.send({"type": self.ui_key, self.ui_key: self.ui_info()})

    def routes(self, router: web.UrlDispatcher) -> None:
        """Eigene Routen; sie bleiben auch bei ausgeschaltetem Modul erreichbar (Einstellungen)."""

    def require_active(self) -> None:
        if not self.active:
            raise ApiError(409, f"Modul {self.info.name} ist aus")
