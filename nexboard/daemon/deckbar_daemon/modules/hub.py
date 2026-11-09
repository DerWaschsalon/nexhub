"""Modul NexHub: verbindet die NexBoard mit dem Konto im Hub und lädt Runs hoch."""
from __future__ import annotations

from typing import Any

from aiohttp import web
from nexcore import Context, ModuleInfo
from nexcore.errors import ApiError
from nexcore.settings import SettingsStore

from ..core.http import ok, read_object
from ..core.live import LiveHub
from ..hub import Hub, HubError
from .base import WebModule


class HubModule(WebModule):
    info = ModuleInfo(
        "hub", "NexHub", "share", "link-variant",
        "Verbindet die NexBoard mit deinem Konto im NexHub, der Website der Gilde. Später lädt sie "
        "dorthin deine Dungeon-Runs hoch.",
        tags=("Hub", "Online"),
    )
    ui_key = "hub"

    def __init__(self, ctx: Context, live: LiveHub, hub: Hub) -> None:
        super().__init__(ctx, live)
        self.hub = hub
        hub.listeners.append(self.changed)
        self.actions = {"pair": hub.start_pairing, "cancel": hub.cancel_pairing, "unpair": hub.unpair,
                        "check": hub.check}

    def ui_info(self) -> dict[str, Any]:
        return self.hub.info()

    @property
    def store(self) -> SettingsStore[Any]:
        return self.hub.store

    async def update_settings(self, patch: dict[str, Any]) -> None:
        """Nur Adresse, Name und Hochladen; das Token setzt allein die Kopplung (hub.update)."""
        self.hub.update(patch)
        await self.changed()

    async def start(self) -> None:
        self.spawn(self.hub.watch)
        self.hub.enabled = True

    async def stop(self) -> None:
        self.hub.enabled = False
        await self.hub.close()

    def status(self) -> dict[str, Any]:
        return {"status": self.hub.status, "owner": (self.hub.account or {}).get("owner")}

    def routes(self, router: web.UrlDispatcher) -> None:
        router.add_get("/api/hub", self.api_get)
        router.add_put("/api/hub", self.api_put)
        router.add_post("/api/hub/{action:pair|cancel|unpair|check}", self.api_action)

    async def api_get(self, request: web.Request) -> web.Response:
        return web.json_response(self.hub.info())

    async def api_put(self, request: web.Request) -> web.Response:
        await self.update_settings(await read_object(request))
        return ok(**self.hub.info())

    async def api_action(self, request: web.Request) -> web.Response:
        """pair: Code holen · cancel: Kopplung abbrechen · unpair: abkoppeln · check: Stand prüfen"""
        self.require_active()
        try:
            await self.actions[request.match_info["action"]]()
        except HubError as e:
            raise ApiError(502, str(e)) from e
        return ok(**self.hub.info())
