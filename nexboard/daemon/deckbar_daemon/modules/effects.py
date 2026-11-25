"""Modul Effekte: was gerade auf dem Boss und auf dir liegt, für andere Programme auf diesem PC."""
from __future__ import annotations

from typing import Any

from aiohttp import web
from nexcore import Context, ModuleInfo

from ..core.live import LiveHub
from ..effects import EMPTY, ActiveEffects
from .base import WebModule


class EffectsModule(WebModule):
    info = ModuleInfo(
        "aion2.effects", "AION 2 · Effekte", "aion2", "flash",
        "Gibt anderen Programmen auf diesem PC die Effekte, die gerade auf dem Boss und auf dir liegen, mit "
        "genauem Anfang und Ende aus den Kampfdaten (z. B. Schadensreflexion).",
        requires=("aion2.dps",), split_from="aion2.warnings", tags=("AION 2", "Desktop"),
    )

    def __init__(self, ctx: Context, live: LiveHub, effects: ActiveEffects) -> None:
        super().__init__(ctx, live)
        self.effects = effects

    async def current(self) -> dict[str, Any]:
        """Die laufenden Effekte; bei ausgeschaltetem Modul keine."""
        return await self.effects.current() if self.active else EMPTY

    def routes(self, router: web.UrlDispatcher) -> None:
        router.add_get(f"/api/m/{self.info.id}", self.api_get)

    async def api_get(self, request: web.Request) -> web.Response:
        return web.json_response(await self.current())
