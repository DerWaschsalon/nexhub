"""Host des Daemons: baut Komponenten und Module zusammen und stellt Web-API, Web-UI und /ws bereit.

Fachliches steht in den Modulen (deckbar_daemon/modules/); hier bleibt nur, was keinem Modul gehört:
Status, Modulschalter, allgemeine Einstellungen, Neustart und die Auslieferung der Web-UI.
"""
from __future__ import annotations

import asyncio
import logging
import os
from importlib import resources
from pathlib import Path
from typing import Any

from aiohttp import WSCloseCode, web
from nexcore import Context, EventBus, Paths, Registry
from nexcore.errors import ApiError
from nexcore.registry import CHANGED
from nexcore.settings import MASK, SettingsStore, is_mask

from . import __version__
from .a2ui import A2Ui
from .boss_effekte import BossEffekte
from .bot import SETTINGS_FILE as bot_settings_file
from .bot import DiscordBot
from .capture import aion2_running, history_root
from .config import Settings, is_default_config, save_settings
from .core.http import api_errors, local_only, ok, read_object
from .core.live import LiveHub
from .core.topics import LANGUAGE
from .dps import SETTINGS_FILE as dps_settings_file
from .dps import DpsFeed
from .hub import Hub
from .modules import CATEGORIES
from .modules.base import WebModule
from .modules.bot import BotModule
from .modules.deck import DeckModule
from .modules.dps import DpsModule
from .modules.hub import HubModule
from .modules.overlay import OverlayModule
from .modules.plugins import PluginsModule
from .modules.radar import RadarModule
from .modules.runs import RunsModule
from .modules.schedule import ScheduleModule
from .modules.updates import UpdatesModule
from .overlay import UNIT as OVERLAY_UNIT
from .overlay import Overlay
from .radar import Radar
from .runs import SETTINGS_FILE as runs_settings_file
from .runs import DungeonRuns, a2tools_dir
from .schedule import Schedule
from .state import State
from .updates import Updates

log = logging.getLogger(__name__)

# Einstellungen, die erst nach einem Neustart des Daemons wirken
RESTART_FIELDS = ("host", "port", "token", "mdns", "usb", "heartbeat")
WEB_DIR = Path(str(resources.files("deckbar_daemon").joinpath("web")))
RESTART_DELAY_S = 0.3  # Antwort noch zustellen, dann SIGTERM an sich selbst


class NexBoard:
    def __init__(self, settings: Settings, config_dir: Path, mdns: bool = True) -> None:
        self.settings = settings
        self.config_dir = config_dir
        self.restart_requested = False
        # Nur der Daemon mit der echten Konfiguration steuert den Overlay-Dienst (nicht Testinstanzen)
        self.real_config = is_default_config(config_dir)
        self.bus = EventBus()
        ctx = Context(self.bus, Paths("deckbar"))
        self.live = LiveHub(self.bus)
        self.state = State()
        self._build_components()
        self.bar = DeckModule(ctx, self.live, lambda: self.settings, self.state, config_dir, WEB_DIR,
                              mdns and settings.mdns)
        self.radar_module = RadarModule(ctx, self.live, self.radar, BossEffekte(self.dps.capture))
        # Reihenfolge = Start- und Anzeigereihenfolge
        self.web_modules: list[WebModule] = [
            self.bar,
            DpsModule(ctx, self.live, self.dps, self.state),
            OverlayModule(ctx, self.live, self.overlay, self.state),
            PluginsModule(ctx, self.live, self.a2.plugins),
            RunsModule(ctx, self.live, self.runs, self.state),
            ScheduleModule(ctx, self.live, Schedule(config_dir)),
            self.radar_module,
            BotModule(ctx, self.live, self.bot, self.runs),
            HubModule(ctx, self.live, self.hub),
            UpdatesModule(ctx, self.live, Updates(state_path=config_dir / "updates-state.json")),
        ]
        # Plugins liefen bis zum eigenen Modul einfach mit dem Overlay: bei alten modules.yaml neu
        self.modules = Registry(self.bus, self.web_modules, config_dir / "modules.yaml", self._initial_modules,
                                introduced=frozenset({"aion2.plugins"}))
        self.bus.on(CHANGED, self._modules_changed)
        self.state.subscribe(self._state_changed)
        for key, provider in (("state", lambda: self.state.values), ("status", self.status),
                              ("modules", self.modules_info), ("settings", self.settings_info)):
            self.live.section(key, provider)

    def _build_components(self) -> None:
        """Die Komponenten und ihre Verdrahtung untereinander; sie werden mit ihrem Bereich zerlegt."""
        c = self.config_dir
        self.dps = DpsFeed(self.state, c, self._on_combat, language=lambda: self.settings.language)
        self.runs = DungeonRuns(c)
        self.runs.history_dir = self._history_dir
        own = lambda: self.dps.settings.source == "capture"  # noqa: E731
        self.runs.event_driven = self.runs.own_history = own
        self.dps.capture.data_listeners.append(self._capture_event)
        self.bot = DiscordBot(c)
        self.dps.fight_listeners.append(self.bot.on_fight)
        self.runs.run_listeners.append(self.bot.on_run)
        self.hub = Hub(c)
        self.hub.history_dir = self._history_dir
        self.hub.language = lambda: self.settings.language
        self.hub.capture_build = self._capture_build
        self.dps.fight_listeners.append(self.hub.on_fight)
        self.runs.run_listeners.append(self.hub.on_run)
        self.overlay = Overlay(c, manage_unit=self.real_config)
        self.overlay.game_check = self._game_running
        self.radar = Radar(lambda stand: self.overlay.publish("radar", stand), spiel_laeuft=self._game_running)
        self.hub.deaths = self.radar.tode_zwischen
        self._sync_radar()
        # Oberfläche des A2Tools-Meters mit dem Plugin-Host (eigener Port, siehe __main__); Testinstanzen
        # bekommen eigene Plugin-Ordner, damit sie die installierten Plugins nicht anfassen
        self.a2 = A2Ui(self.dps.capture, c / "a2-settings.json", None if self.real_config else c / "a2")
        self.a2.plugins.overlay = self.overlay.plugin_command
        # eine Sprache für alles: die der allgemeinen Einstellungen (System → Allgemein)
        self.a2.on_language = self.set_language
        self.bus.on(LANGUAGE, self.a2.apply_language)

    def _sync_radar(self) -> None:
        """Name und Sprache ans Radar. Seine Datei liegt fest in ~/.config, Testinstanzen fassen sie nicht an."""
        if self.real_config:
            self.radar.sync_profile(self.settings.character_name, self.settings.language)

    def _initial_modules(self) -> set[str]:
        """Erster Start mit Modulen: was bisher eingerichtet war, bleibt an (Umstieg ohne Überraschung)."""
        c = self.config_dir
        ids = {"deck"}
        if self.settings.update_check:
            ids.add("updates")
        if (c / dps_settings_file).exists() and self.dps.settings.enabled:
            ids.add("aion2.dps")
        if (c / runs_settings_file).exists():
            ids.add("aion2.runs")
        if (c / bot_settings_file).exists():
            ids.add("discord.bot")
        unit = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "systemd" / "user" / OVERLAY_UNIT
        if self.real_config and unit.exists():
            ids.add("aion2.overlay")
        return ids

    # ---------------------------------------------------------------- Verdrahtung
    async def _on_combat(self, active: bool) -> None:
        await self.bar.devices.on_combat(active)

    async def _state_changed(self, diff: dict[str, Any]) -> None:
        await self.live.send({"type": "state", "values": diff})

    async def _modules_changed(self, _: object) -> None:
        await self.live.send({"type": "modules", "modules": self.modules_info()})

    async def _game_running(self) -> bool:
        """Läuft AION 2? Schaut der Mitschnitt ohnehin alle 5 s in /proc, gilt sein Blick."""
        game = self.dps.capture.game
        if self.modules.on("aion2.dps") and self.dps.settings.source == "capture" and game is not None:
            return game
        return await asyncio.to_thread(aion2_running)

    async def _capture_event(self, event: str, payload: Any) -> None:
        if event == "fights_saved":
            self.runs.wake()

    @staticmethod
    def _capture_build() -> str | None:
        """Build-Kennung von deckbar-capture (schreibt update.sh), für `recorder.capture` im NexLog."""
        try:
            return (history_root().parent / "capture-build-id").read_text().strip()[:80] or None
        except OSError:
            return None

    def _history_dir(self) -> Path:
        if self.dps.settings.source == "capture":
            return history_root() / "history"
        return a2tools_dir() / "history"

    async def close_clients(self) -> None:
        """Beim Beenden: Overlay-Streams, Geräte und Web-UI-Tabs trennen, damit aiohttp nicht auf offene
        Handler wartet. Geräte verbinden sich nach dem Neustart von selbst wieder."""
        self.overlay.close_clients()
        sockets = list(self.live.clients)
        if sockets:
            await asyncio.wait([asyncio.ensure_future(ws.close(code=WSCloseCode.GOING_AWAY, message=b"shutdown"))
                                for ws in sockets], timeout=2)
        await self.bar.devices.close_all()

    # ---------------------------------------------------------------- Stand
    def status(self) -> dict[str, Any]:
        return {"version": __version__, "port": self.settings.port, "name": self.settings.name,
                **self.bar.details()}

    def modules_info(self) -> dict[str, Any]:
        return {"categories": CATEGORIES, "modules": self.modules.info()}

    def settings_info(self) -> dict[str, Any]:
        s = self.settings.model_dump()
        s["token"] = MASK
        return {"settings": s, "schema": Settings.model_json_schema(), "config_dir": str(self.config_dir),
                "restart_fields": list(RESTART_FIELDS)}

    # ---------------------------------------------------------------- Web-API
    def routes(self, router: web.UrlDispatcher) -> None:
        router.add_get("/", self.index)
        router.add_get("/api/live", self.live.handler)
        router.add_get("/api/status", self.api_status)
        router.add_get("/api/modules", self.api_get_modules)
        router.add_put("/api/modules/{id}", self.api_put_module)
        router.add_get("/api/settings", self.api_get_settings)
        router.add_put("/api/settings", self.api_put_settings)
        router.add_post("/api/settings/token", self.api_get_token)
        router.add_post("/api/restart", self.api_restart)
        router.add_get("/api/m/{id}/settings", self.api_get_module_settings)
        router.add_put("/api/m/{id}/settings", self.api_put_module_settings)
        for module in self.web_modules:
            module.routes(router)
        router.add_static("/static/", WEB_DIR)

    def overlay_routes(self, app: web.Application) -> None:
        """Routen der Overlay-Seite (eigener Port): Overlay und die Karte des Radars."""
        self.overlay.add_routes(app)
        self.radar_module.overlay_routes(app.router)

    async def index(self, request: web.Request) -> web.FileResponse:
        return web.FileResponse(WEB_DIR / "index.html", headers={"Cache-Control": "no-cache"})

    async def api_status(self, request: web.Request) -> web.Response:
        return web.json_response({**self.status(), "devices": self.bar.devices.info(), "state": self.state.values})

    async def api_get_modules(self, request: web.Request) -> web.Response:
        return web.json_response(self.modules_info())

    async def api_put_module(self, request: web.Request) -> web.Response:
        mid = request.match_info["id"]
        on = (await read_object(request)).get("enabled")
        if not isinstance(on, bool):
            raise ApiError(400, 'erwartet {"enabled": true|false}')
        try:
            changed = await self.modules.set(mid, on)
        except KeyError as e:
            raise ApiError(404, f"Modul {mid} gibt es nicht") from e
        return ok(changed=changed, **self.modules_info())

    def _module_settings(self, request: web.Request) -> tuple[WebModule, SettingsStore[Any]]:
        mid = request.match_info["id"]
        for module in self.web_modules:
            if module.info.id == mid and module.store:
                return module, module.store
        raise ApiError(404, f"Modul {mid} gibt es nicht oder es hat keine Einstellungen")

    @staticmethod
    def _settings_body(store: SettingsStore[Any]) -> dict[str, Any]:
        """Einstellungen (Geheimnisse maskiert) und ihr Schema, aus dem die Web-UI das Formular baut."""
        return {"settings": store.public(), "schema": store.schema()}

    async def api_get_module_settings(self, request: web.Request) -> web.Response:
        _, store = self._module_settings(request)
        return web.json_response(self._settings_body(store))

    async def api_put_module_settings(self, request: web.Request) -> web.Response:
        module, store = self._module_settings(request)
        await module.update_settings(await read_object(request))
        return ok(**self._settings_body(store))

    async def api_get_settings(self, request: web.Request) -> web.Response:
        return web.json_response(self.settings_info())

    async def api_put_settings(self, request: web.Request) -> web.Response:
        """Allgemeine Einstellungen (config.yaml). Port, Adresse und Token wirken erst nach einem Neustart."""
        merged = self.settings.model_dump()
        for key, value in (await read_object(request)).items():
            if key == "token" and (not value or is_mask(value)):
                continue
            merged[key] = value
        restart = await self._apply_settings(Settings.model_validate(merged))
        return ok(restart=restart, **self.settings_info())

    async def set_language(self, language: str) -> None:
        """Sprachwahl im A2Tools-Meter: dieselbe Einstellung wie in der Web-UI (System → Allgemein)."""
        await self._apply_settings(Settings.model_validate({**self.settings.model_dump(), "language": language}))

    async def _apply_settings(self, settings: Settings) -> list[str]:
        """Speichern und übernehmen, was sofort wirken kann; zurück kommt, was erst nach einem Neustart wirkt."""
        save_settings(self.config_dir, settings)
        current, saved = self.settings.model_dump(), settings.model_dump()
        restart = [k for k in RESTART_FIELDS if saved[k] != current[k]]
        self.settings = settings.model_copy(update={k: current[k] for k in RESTART_FIELDS})
        self.bar.media.player = self.settings.player
        self._sync_radar()
        if saved["language"] != current["language"]:
            await self.bus.emit(LANGUAGE, self.settings.language)
        await self.live.send({"type": "settings", "settings": self.settings_info()})
        return restart

    async def api_get_token(self, request: web.Request) -> web.Response:
        """Geräte-Token im Klartext (für die Firmware-Konfiguration), nur auf ausdrückliche Anfrage."""
        return web.json_response({"token": self.settings.token})

    async def api_restart(self, request: web.Request) -> web.Response:
        self.restart_requested = True
        asyncio.get_running_loop().call_later(RESTART_DELAY_S, os.kill, os.getpid(), 15)  # SIGTERM → sauber beenden
        return ok()


def build_app(deck: NexBoard) -> web.Application:
    app = web.Application(middlewares=[local_only, api_errors], client_max_size=256 * 1024)
    deck.routes(app.router)

    async def cleanup(_app: web.Application) -> None:
        await deck.bar.art.close()
        await deck.bot.close()
        await deck.hub.close()

    app.on_cleanup.append(cleanup)
    return app
