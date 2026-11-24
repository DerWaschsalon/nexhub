"""Die Oberfläche des A2Tools DPS Meter (Submodul capture/a2tools, GPL-3.0) fürs NexBoard-Overlay.

Läuft als eigener kleiner Webserver auf 127.0.0.1 (Port der NexBoard + 1), damit die absoluten
Pfade der Oberfläche (/src/js/…, /vendor/…) unverändert passen. Das Overlay (overlay/deckbar-overlay)
lädt sie in Qt WebEngine. Statt Tauri spricht die Oberfläche mit dem Shim in web/a2shim.js:

    GET  /…                 Dateien der Oberfläche und der Plugins (meter_files.py)
    GET  /api/a2/events     Server-Sent Events: die Tauri-Events (meter_events.py)
    POST /api/a2/invoke     {"cmd": …, "args": {…}}: Tauri-Commands; die an den Mitschnitt stehen in
                            meter_commands.py, die der Plugins im Plugin-Host (plugins.py)
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Awaitable, Callable

from aiohttp import web

from .capture import Capture
from .meter_commands import CaptureCommands
from .meter_events import EventStream
from .meter_files import MeterFiles, app_version
from .meter_settings import MeterSettings
from .plugin_files import PluginError
from .plugins import LANGUAGE_KEY, PluginHost

log = logging.getLogger(__name__)

# Befehle ohne plugin_-Vorsilbe, die der Plugin-Host beantwortet
PLUGIN_COMMANDS = {"meter_shown", "set_meter_shown", "set_plugin_theme"}
# Ohne Gegenstück in der NexBoard (Offline-Build des Meters, siehe app.rs): Befehl → feste Antwort
STUBS: dict[str, Any] = {
    "build_features": {"online": False}, "is_admin": True,
    "log_from_ui": None, "set_debug_logging": None, "set_packet_logging": None, "account_sign_out": None,
    "write_cached_icon": None, "read_cached_icon": None, "account_status_cached": None,
    "choose_screenshot_folder": None,
    "discord_activity_available": False, "show_update_window": False,
    "default_screenshot_folder": "", "share_status": {}, "get_hotkey_status": {},
}


class A2Ui:
    def __init__(self, capture: Capture, settings_path: Path, plugin_dir: Path | None = None) -> None:
        self.capture = capture
        self.settings = MeterSettings(settings_path)
        self._apply_update_rate()
        self.events = EventStream(capture)
        self.commands = CaptureCommands(capture)
        base = plugin_dir or Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "deckbar"
        self.plugins = PluginHost(capture, lambda: self.settings.values, self.set_setting, self.events.emit,
                                  base / "plugins", base / "plugin-data")
        self.files = MeterFiles(self.plugins)
        # Sprachwahl im Meter speichert die allgemeine Einstellung (setzt __main__); die meldet sich
        # dann über apply_language zurück
        self.on_language: Callable[[str], Awaitable[None]] | None = None

    async def apply_language(self, language: str) -> None:
        """Sprache der allgemeinen Einstellungen an Mitschnitt, Meter und Plugins geben."""
        if self.capture.running:
            try:
                await self.commands.request("language", lang=language)
            except (RuntimeError, TimeoutError) as e:
                log.warning("Sprache nicht an den Mitschnitt übergeben: %s", e)
        await self.change_setting(LANGUAGE_KEY, language)
        await self.plugins.tell_all("language", language)

    def set_setting(self, key: str, value: str) -> None:
        self.settings.set(key, value)
        self._apply_update_rate()

    async def change_setting(self, key: str, value: str) -> None:
        """Wie set_setting, meldet die Änderung aber der Oberfläche; ohne Änderung passiert nichts."""
        if self.settings.values.get(key) != value:
            self.set_setting(key, value)
            await self.events.emit("setting-changed", {"key": key, "value": value})

    def _apply_update_rate(self) -> None:
        """Takt aus den Meter-Einstellungen an den Mitschnitt; gilt ab seinem nächsten Start, damit er
        nicht mitten im Spiel neu startet."""
        self.capture.interval_ms = self.settings.update_rate_ms

    async def invoke(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
            cmd, args = str(body["cmd"]), body.get("args") or {}
            window = body.get("window")
        except (ValueError, KeyError, TypeError):
            return web.json_response({"error": "erwartet {cmd, args}"}, status=400)
        try:
            # Plugin-Seiten kommen nur an ihre Befehle, das prüft der Host anhand der Fensterkennung
            from_plugin = str(window or "").startswith(("plugin-", "widget:"))
            if cmd.startswith("plugin_") or cmd in PLUGIN_COMMANDS or from_plugin:
                result = await self._plugin_call(cmd, args, str(window) if window else None)
            else:
                result = await self.call(cmd, args)
        except PluginError as e:
            return web.json_response({"error": str(e)}, status=500)
        except Exception as e:  # Tauri-Commands melden Fehler als String
            log.debug("invoke %s: %s", cmd, e)
            return web.json_response({"error": str(e)}, status=500)
        return web.json_response({"result": result})

    async def _plugin_call(self, cmd: str, args: dict, window: str | None) -> Any:
        if cmd == "get_settings":
            return self.settings.values
        return await self.plugins.call(cmd, args, window)

    async def call(self, cmd: str, args: dict) -> Any:
        """Ein Tauri-Command der Oberfläche: hier die zur Oberfläche selbst, der Rest geht an den
        Mitschnitt. Fensterbefehle macht das Overlay."""
        if cmd in STUBS:
            return STUBS[cmd]
        match cmd:
            case "get_app_version":
                return app_version()
            case "get_settings":
                return self.settings.values
            case "update_settings":
                await self.change_setting(str(args.get("key")), str(args.get("value")))
            case "clear_settings":
                self.settings.clear()
                self._apply_update_rate()
            case "set_language":
                await (self.on_language or self.apply_language)(str(args.get("language")))
            case _:
                return await self.commands.call(cmd, args)
        return None

    def app(self, *middlewares, routes=None) -> web.Application:
        """routes: weitere Routen (Overlay-Seite), vor der Auslieferung der Meter-Dateien."""
        app = web.Application(middlewares=list(middlewares), client_max_size=4 * 1024 * 1024)
        if routes:
            routes(app)
        app.router.add_get("/api/a2/events", self.events.handle)
        app.router.add_post("/api/a2/invoke", self.invoke)
        app.router.add_get("/{tail:.*}", self.files.static)
        return app
