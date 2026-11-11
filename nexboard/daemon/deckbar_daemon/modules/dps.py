"""Modul DPS-Mitschnitt: liest den Kampf passiv mit und liefert DPS für Leiste, Overlay und Discord."""
from __future__ import annotations

from typing import Any

from aiohttp import web
from nexcore import Context, ModuleInfo
from nexcore.settings import SettingsStore

from ..core.http import ok, read_object
from ..core.live import LiveHub
from ..core.topics import DPS_RESET
from ..dps import STATUS_TEXT, DpsFeed
from ..overlay_layout import WidgetOption, WidgetSpec
from ..state import State
from .base import WebModule


class DpsModule(WebModule):
    info = ModuleInfo(
        "aion2.dps", "AION 2 · Kampfdaten", "ingame", "sword-cross",
        "Liest den Kampf passiv mit (deckbar-capture, Kern des A2Tools DPS Meter) und liefert DPS "
        "für Leiste, Overlay und Discord.",
        tags=("AION 2", "Live"),
    )
    ui_key = "dps"
    overlay_widgets = (
        WidgetSpec("meter", "DPS-Meter", "Oberfläche des A2Tools-Meters", profiles=("PvE", "PvP")),
        WidgetSpec("boss", "Boss-Leiste", "HP des Ziels mit Kill-Prognose", options=(
            WidgetOption("show_ttk", "Kill-Prognose", "Restzeit aus dem HP-Verlauf der letzten 40 s"),
            WidgetOption("hide_idle", "Außerhalb von Kämpfen ausblenden"),
        )),
    )

    def __init__(self, ctx: Context, live: LiveHub, dps: DpsFeed, state: State) -> None:
        super().__init__(ctx, live)
        self.dps = dps
        self.state = state
        dps.status_listeners.append(self.changed)
        ctx.bus.on(DPS_RESET, self.reset)  # auch ausgeschaltet: dann warnt reset() nur

    def ui_info(self) -> dict[str, Any]:
        return self.dps.info()

    @property
    def store(self) -> SettingsStore[Any]:
        return self.dps.store

    def save_settings(self, value: Any) -> None:
        self.dps.save(value)

    async def start(self) -> None:
        self.spawn(self.dps.watch)
        if not self.dps.settings.enabled:
            self.dps.save(self.dps.settings.model_copy(update={"enabled": True}))

    async def stop(self) -> None:
        self.dps.status, self.dps.detail = "off", ""
        self.state.update(dps=None, dps_active=False)
        await self.changed()

    async def reset(self, _: object = None) -> None:
        """Reset-Knopf der DPS-Kachel: wie der Reset im Meter (Kampf speichern, neu zählen)."""
        if self.dps.settings.source != "capture":
            self.log.warning("DPS-Reset geht nur mit eigenem Mitschnitt (Quelle %s)", self.dps.settings.source)
            return
        try:
            await self.dps.capture.request("reset")
        except (RuntimeError, TimeoutError) as e:
            self.log.warning("DPS-Reset fehlgeschlagen: %s", e)

    def status(self) -> dict[str, Any]:
        dps = self.state.values.get("dps") or {}
        return {"status": self.dps.status, "text": STATUS_TEXT[self.dps.status],
                "active": bool(self.state.values.get("dps_active")), "target": dps.get("target"),
                "top": (dps.get("rows") or [])[:3]}

    def routes(self, router: web.UrlDispatcher) -> None:
        router.add_get("/api/dps", self.api_get)
        router.add_put("/api/dps", self.api_put)

    async def api_get(self, request: web.Request) -> web.Response:
        return web.json_response(self.dps.info())

    async def api_put(self, request: web.Request) -> web.Response:
        await self.update_settings(await read_object(request))
        return ok(**self.dps.info())
