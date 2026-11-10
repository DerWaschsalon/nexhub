"""Modul Plugins: die A2Tools-Plugins (Katalog, Installation mit Zustimmung, ein/aus, Fenster).

Der Plugin-Host selbst steht in plugins.py; seine Befehle sind dieselben, die die Oberfläche des Meters
nutzt (plugin_list, plugin_install …). Die Web-UI bekommt davon nur die zur Verwaltung.
"""
from __future__ import annotations

import json
from typing import Any

from aiohttp import web
from nexcore import Context, ModuleInfo
from nexcore.errors import ApiError

from ..a2ui import A2_ROOT
from ..core.http import read_object
from ..core.live import LiveHub
from ..plugins import PluginError, PluginHost
from .base import WebModule

# Texte der Plugin-Einstellungen des Meters (Rechte, Hinweise), deutsch wie die Web-UI
TEXTS = A2_ROOT / "src" / "data" / "i18n" / "ui" / "de.json"
# Was die Web-UI darf: verwalten, nicht wie eine Plugin-Seite Daten lesen oder Fenster steuern
MANAGEMENT = frozenset({"plugin_list", "plugin_catalog", "plugin_install", "plugin_uninstall",
                        "plugin_check_updates", "plugin_set_enabled", "plugin_open"})


class PluginsModule(WebModule):
    info = ModuleInfo(
        "aion2.plugins", "AION 2 · Plugins", "ingame", "puzzle-outline",
        "Plugins aus dem signierten Katalog von A2Tools: installieren mit Zustimmung zu ihren Rechten, "
        "Fenster und Widgets im Overlay.",
        requires=("aion2.overlay",), default=True, tags=("AION 2", "Desktop"),
    )

    def __init__(self, ctx: Context, live: LiveHub, host: PluginHost) -> None:
        super().__init__(ctx, live)
        self.host = host

    async def start(self) -> None:
        self.host.start()
        await self.host.send_decoders()

    async def stop(self) -> None:
        await self.host.deactivate()

    def status(self) -> dict[str, Any]:
        return {"installed": len(self.host.loaded)}

    def routes(self, router: web.UrlDispatcher) -> None:
        router.add_post("/api/plugins", self.api_call)
        router.add_get("/api/plugins/texts", self.api_texts)

    async def api_texts(self, request: web.Request) -> web.Response:
        try:
            texts = json.loads(TEXTS.read_text())["settings"]["plugins"]
        except (OSError, ValueError, KeyError) as e:
            raise ApiError(500, f"Texte der Plugins fehlen: {e}") from e
        return web.json_response(texts)

    async def api_call(self, request: web.Request) -> web.Response:
        body = await read_object(request)
        cmd, args = body.get("cmd"), body.get("args") or {}
        if cmd not in MANAGEMENT or not isinstance(args, dict):
            raise ApiError(400, "erwartet {cmd, args} mit einem Verwaltungsbefehl")
        try:
            return web.json_response({"result": await self.host.call(str(cmd), args, None)})
        except PluginError as e:
            raise ApiError(400, str(e)) from e
