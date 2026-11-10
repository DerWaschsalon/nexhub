"""Modul Touch-Leiste: Layout, Hintergrund, Ereignisse der Kacheln und die Verbindung zu den Geräten."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml
from aiohttp import web
from nexcore import Context, ModuleInfo, SettingsStore
from nexcore.errors import ApiError
from pydantic import Field, ValidationError

from ..actions import Executor
from ..art import Art
from ..audio import Audio
from ..background import UPLOAD_MAX, Background, save_upload
from ..claude import ClaudeUsage
from ..config import ID, Layout, Settings, _Strict
from ..core.devices import CLOSE_MODULE_OFF, DeviceHub
from ..core.http import ok, read_object
from ..core.live import LiveHub
from ..core.topics import DPS_RESET
from ..deck_layout import DeckLayout, error_text
from ..mdns import Announcer
from ..media import Media
from ..proc import have
from ..state import DEFAULTS, State
from ..usb import UsbBridge
from .base import WebModule

log = logging.getLogger(__name__)

WEB_DIR_DEFAULT_BG = "bg.png"
BACKGROUND_POLL_S = 5
LAYOUT_POLL_S = 1
STATE_KEY_MAX = 32
SETTINGS_FILE = "deck.yaml"  # im Konfig-Ordner, benannt nach dem Modul
SETTINGS_HEADER = "Touch-Leiste – wird von der Web-UI überschrieben. Layout steht in layout.yaml."


class DeckSettings(_Strict):
    auto_page: ID | None = Field(None, title="Im Kampf zur Seite",
                                 description="Bei Kampfbeginn zeigt die Leiste diese Seite, danach wieder die erste",
                                 json_schema_extra={"choices": "pages"})


class DeckModule(WebModule):
    info = ModuleInfo(
        "deck", "Touch-Leiste", "bar", "gesture-tap-button",
        "Seiten, Kacheln und Aktionen für die Touch-Leiste (ESP32) und den Simulator: Medien, "
        "Lautstärke, Hotkeys, Befehle, Links.",
        default=True, tags=("Hardware", "Makros"),
    )

    def __init__(self, ctx: Context, live: LiveHub, settings: Callable[[], Settings], state: State,
                 config_dir: Path, web_dir: Path, mdns: bool) -> None:
        super().__init__(ctx, live)
        self.settings = settings
        self.state = state
        self.web_dir = web_dir
        self.mdns = mdns
        self.upload_dir = config_dir / "backgrounds"
        self.layout = DeckLayout(config_dir / "layout.yaml")
        self._store = SettingsStore(config_dir / SETTINGS_FILE, DeckSettings, header=SETTINGS_HEADER)
        self.audio = Audio(state)
        self.media = Media(state, settings().player)
        self.executor = Executor(self.audio, self.media)
        self.art = Art()
        self.bg = Background()
        self.claude = ClaudeUsage(state, lambda: self.layout.layout.has_type("claude"))
        self.devices = DeviceHub(settings, self.layout, state, self.art, self.bg, live,
                                 enabled=lambda: self.active, on_event=self.handle_event,
                                 auto_page=lambda: self._store.value.auto_page)
        state.subscribe(self.devices.on_state)
        live.section("layout", self.layout.json)
        live.section("error", lambda: self.layout.error)
        live.handle_events(self.handle_event)

    @property
    def store(self) -> SettingsStore[Any]:
        return self._store

    # ------------------------------------------------------------ Lebenszyklus
    async def start(self) -> None:
        port = self.settings().port
        usb = UsbBridge(self.settings().usb, f"ws://127.0.0.1:{port}/ws")
        for job in (self.audio.watch, self.media.watch, self.watch_layout_file, self.watch_background,
                    usb.watch, self.announce, self.claude.watch):
            self.spawn(job)

    async def stop(self) -> None:
        await self.devices.close_all(CLOSE_MODULE_OFF, b"module off")

    def status(self) -> dict[str, Any]:
        pages = self.layout.layout.pages
        return {"devices": len(self.devices.devices), "pages": len(pages),
                "items": sum(len(p.items) for p in pages), "error": bool(self.layout.error)}

    def details(self) -> dict[str, Any]:
        """Für /api/status: Werkzeuge, letzter Fehler einer Aktion, Hintergrund."""
        return {
            "layout_path": str(self.layout.path),
            "tools": {t: have(t) for t in ("wpctl", "pactl", "playerctl", "ydotool", "xdg-open")},
            "last_error": self.executor.last_error,
            "background": {"mode": self.bg.mode, "source": str(self.bg.source) if self.bg.source else None,
                           "id": self.bg.id},
        }

    async def announce(self) -> None:
        """mDNS-Anzeige für Geräte, solange die Touch-Leiste an ist."""
        if not self.mdns:
            return
        settings = self.settings()
        announcer = Announcer(settings.name, settings.port)
        try:
            await announcer.start()
        except OSError as e:
            log.warning("mDNS nicht verfügbar: %s", e)
            return
        try:
            await asyncio.Event().wait()
        finally:
            await announcer.stop()

    # ------------------------------------------------------------ Layout und Hintergrund
    async def apply_layout(self, layout: Layout, save: bool) -> None:
        self.layout.set(layout, save)
        log.info("Layout aktualisiert (hash %s), an %d Gerät(e)", self.layout.payload["hash"],
                 len(self.devices.devices))
        await self.devices.send_layout()
        await self.live.send({"type": "layout", "layout": self.layout.json(), "error": None})
        await self.update_background(layout.theme.background)

    async def watch_layout_file(self) -> None:
        """Übernimmt Handänderungen an layout.yaml ohne Neustart."""
        while True:
            await asyncio.sleep(LAYOUT_POLL_S)
            if not self.layout.changed_on_disk():
                continue
            try:
                await self.apply_layout(self.layout.read(), save=False)
            except (yaml.YAMLError, ValidationError) as e:
                self.layout.error = error_text(e)
                log.error("layout.yaml ungültig, altes Layout bleibt aktiv:\n%s", self.layout.error)
                await self.live.send({"type": "layout_error", "error": self.layout.error})

    async def update_background(self, mode: str | None = None) -> None:
        if await self.bg.update(mode):
            await self.devices.send_bg_all()
            await self.live.send({"type": "background", "id": self.bg.id})

    async def watch_background(self) -> None:
        """Folgt einem neuen Desktop-Hintergrund (bzw. geänderter Bilddatei)."""
        await self.update_background(self.layout.layout.theme.background)
        while True:
            await asyncio.sleep(BACKGROUND_POLL_S)
            await self.update_background()

    # ------------------------------------------------------------ Ereignisse
    async def handle_event(self, msg: dict[str, Any], source: str) -> str | None:
        event = msg.get("event")
        if event == "page_change":
            return None
        item_id = msg.get("item")
        item = self.layout.layout.find_item(item_id) if isinstance(item_id, str) else None
        if item is None:
            return f"unbekanntes Item '{item_id}'"
        value = msg.get("value")
        if value is not None and not isinstance(value, int):
            return "value muss eine Ganzzahl sein"
        part = msg.get("part")
        log.debug("%s: %s %s value=%s part=%s", source, event, item_id, value, part)
        if item.type == "dps" and event == "button_press" and part == "reset":
            await self.ctx.bus.emit(DPS_RESET)
            return None
        await self.executor.on_event(item, event, value, part)
        return None

    # ------------------------------------------------------------ Web-API
    def routes(self, router: web.UrlDispatcher) -> None:
        router.add_get("/ws", self.devices.handler)
        router.add_get("/api/layout", self.api_get_layout)
        router.add_put("/api/layout", self.api_put_layout)
        router.add_post("/api/trigger", self.api_trigger)
        router.add_post("/api/state", self.api_post_state)
        router.add_get("/api/background.png", self.api_background)
        router.add_post("/api/background", self.api_upload_background)

    async def api_get_layout(self, request: web.Request) -> web.Response:
        return web.json_response({"layout": self.layout.json(), "error": self.layout.error,
                                  "device_payload": self.layout.payload})

    async def api_put_layout(self, request: web.Request) -> web.Response:
        layout = Layout.model_validate(await read_object(request))
        await self.apply_layout(layout, save=True)
        return ok(hash=self.layout.payload["hash"])

    async def api_trigger(self, request: web.Request) -> web.Response:
        err = await self.handle_event(await read_object(request), "api")
        if err:
            raise ApiError(400, err)
        return ok(error=self.executor.last_error)

    async def api_post_state(self, request: web.Request) -> web.Response:
        """Eigene State-Schlüssel setzen, z. B. aus Skripten:
        curl -X POST localhost:8765/api/state -d '{"obs_rec": true}'"""
        data = await read_object(request)
        builtin = DEFAULTS.keys() & data.keys()
        if builtin:
            raise ApiError(400, f"eingebaute Schlüssel sind schreibgeschützt: {', '.join(sorted(builtin))}")
        if any(not key or len(key) > STATE_KEY_MAX for key in data):
            raise ApiError(400, f"Schlüssel: 1–{STATE_KEY_MAX} Zeichen")
        self.state.update(**data)
        return ok()

    async def api_background(self, request: web.Request) -> web.StreamResponse:
        """Aktueller Hintergrund als PNG (Vorschau in der Web-UI)."""
        if self.bg.png is None:
            return web.FileResponse(self.web_dir / WEB_DIR_DEFAULT_BG, headers={"Cache-Control": "no-cache"})
        return web.Response(body=self.bg.png, content_type="image/png", headers={"Cache-Control": "no-cache"})

    async def api_upload_background(self, request: web.Request) -> web.Response:
        """Bild aus der Web-UI annehmen (roher Body). Antwortet mit dem Pfad für theme.background."""
        data = bytearray()
        async for chunk in request.content.iter_chunked(64 * 1024):
            data += chunk
            if len(data) > UPLOAD_MAX:
                raise ApiError(413, f"Bild zu groß (max. {UPLOAD_MAX >> 20} MB)")
        try:
            path = await asyncio.to_thread(save_upload, bytes(data), self.upload_dir)
        except ValueError as e:
            raise ApiError(422, str(e)) from e
        log.info("Hintergrund hochgeladen: %s", path)
        return ok(path=str(path))
