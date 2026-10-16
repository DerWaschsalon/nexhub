"""WebSocket-Server für Geräte, REST/Live-API und Auslieferung der Web-UI."""
from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
import time
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

import yaml
from aiohttp import ClientSession, ClientTimeout, WSCloseCode, WSMsgType, web
from pydantic import ValidationError

from . import __version__
from .actions import Executor
from .art import MAX_SIZE as ART_MAX_SIZE
from .art import Art, bin_chunks, chunks
from .background import UPLOAD_MAX, Background, save_upload
from .bot import DiscordBot
from .capture import aion2_running, history_root
from .audio import Audio
from .config import Layout, Page, Settings, load_layout, save_layout, save_settings
from .config import config_dir as default_config_dir
from .dps import STATUS_TEXT, DpsFeed, DpsSettings
from .mdns import Announcer
from .modules import ModuleManager
from .overlay import UNIT as OVERLAY_UNIT, Overlay
from .updates import Updates
from .runs import DungeonRuns, RunSettings, a2tools_dir, render_run
from .media import Media
from .proc import have
from .state import State
from .usb import UsbBridge

log = logging.getLogger(__name__)

PROTO_V = 1
# Einstellungen, die erst nach einem Neustart des Daemons wirken
RESTART_FIELDS = ("host", "port", "token", "mdns", "usb", "heartbeat")
BUILTIN_KEYS = ("out_volume", "out_muted", "mic_volume", "mic_muted", "playing", "track", "art_url", "dps", "dps_active")
# nur für Daemon/Web-UI; das Gerät bekommt das Cover als Bild per `art`
DEVICE_HIDDEN_KEYS = {"art_url"}
MAX_MSG = 16 * 1024
DPS_DEVICE_INTERVAL = 1.0  # DPS höchstens 1× pro Sekunde je Gerät (die Kachel zeigt ganze Sekunden)
DPS_DEFAULT_PLAYERS = 5    # wie in shared-ui (build_dps)
LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost"}
WEB_DIR = Path(str(resources.files("deckbar_daemon").joinpath("web")))


@dataclass(eq=False)
class Device:
    ws: web.WebSocketResponse
    remote: str
    id: str = "?"
    model: str = ""
    fw: str = ""
    sim: bool = False
    page: str | None = None
    connected_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.monotonic)
    art_size: int = 0  # Kantenlänge des Covers laut art_request, 0 = keins gewünscht
    bg_id: str = ""    # Hintergrund, den das Gerät gerade zeigt ("" = eingebauter)
    art_have: str = ""  # Cover, das das Gerät schon hat (art_request.have bzw. zuletzt geschickt)
    binary: bool = False  # Bildteile als Binärframes (hello.caps "bin")
    dps_sent: float = 0.0  # monotonic des letzten DPS-Versands
    dps_last: str = ""     # zuletzt geschickte DPS-Nachricht (gleiche nicht nochmal)
    dps_task: asyncio.Task | None = None
    return_page: str | None = None  # Seite vor dem automatischen Wechsel zur DPS-Seite
    # Bildübertragungen pro Gerät nacheinander, damit sich Teile zweier Bilder nicht mischen
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def info(self) -> dict:
        return {
            "id": self.id, "model": self.model, "fw": self.fw, "sim": self.sim,
            "remote": self.remote, "page": self.page, "connected_at": self.connected_at,
        }


def _msg(type_: str, **fields: Any) -> str:
    return json.dumps({"v": PROTO_V, "type": type_, **fields}, ensure_ascii=False, separators=(",", ":"))


def _validation_text(e: ValidationError) -> str:
    parts = []
    for err in e.errors():
        loc = ".".join(str(x) for x in err["loc"])
        parts.append(f"{loc}: {err['msg']}" if loc else err["msg"])
    return "\n".join(parts)


class NexBoard:
    def __init__(self, settings: Settings, config_dir: Path, mdns: bool = True) -> None:
        self.settings = settings
        self.config_dir = config_dir
        self.mdns = mdns and settings.mdns
        self.restart_requested = False
        self.layout_path = config_dir / "layout.yaml"
        self.upload_dir = config_dir / "backgrounds"
        self.layout_error: str | None = None
        try:
            self.layout: Layout = load_layout(self.layout_path)
        except (yaml.YAMLError, ValidationError) as e:
            # nicht abstürzen (systemd-Neustartschleife), sondern Fehler in der Web-UI zeigen
            self.layout_error = _validation_text(e) if isinstance(e, ValidationError) else str(e)
            log.error("layout.yaml ungültig, starte mit leerem Layout:\n%s", self.layout_error)
            self.layout = Layout(pages=[Page(id="main", name="Fehler", items=[])])
        self.layout_payload = self.layout.device_payload()
        self._layout_mtime = self.layout_path.stat().st_mtime
        self.state = State()
        self.audio = Audio(self.state)
        self.media = Media(self.state, settings.player)
        self.executor = Executor(self.audio, self.media)
        self.art = Art()
        self.bg = Background()
        self.dps = DpsFeed(self.state, config_dir, self._on_combat)
        self.dps.status_listeners.append(self._dps_changed)
        self.runs = DungeonRuns(config_dir)
        self.runs.history_dir = self._history_dir
        self.runs.listeners.append(self._runs_changed)
        self.updates = Updates()
        self.updates.listeners.append(self._updates_changed)
        self.bot = DiscordBot(config_dir)
        self.bot.listeners.append(self._bot_changed)
        self.dps.fight_listeners.append(self.bot.on_fight)
        self.runs.run_listeners.append(self.bot.on_run)
        # Nur der Daemon mit der echten Konfiguration steuert den Overlay-Dienst (nicht Testinstanzen)
        self.real_config = config_dir.resolve() == default_config_dir().resolve()
        self.overlay = Overlay(config_dir, manage_unit=self.real_config)
        self.overlay.listeners.append(self._overlay_changed)
        self.overlay.game_check = self._game_running
        self.devices: set[Device] = set()
        self.ui_clients: set[web.WebSocketResponse] = set()
        self.state.subscribe(self._on_state)
        self.modules = ModuleManager(config_dir, self._initial_modules)
        self.modules.listeners.append(self._modules_changed)
        self._register_modules()

    # ---------------------------------------------------------------- Module
    def _initial_modules(self) -> set[str]:
        """Erster Start mit Modulen: was bisher eingerichtet war, bleibt an (Umstieg ohne Überraschung)."""
        c = self.config_dir
        ids = {"deck"}
        if self.settings.update_check:
            ids.add("updates")
        if (c / "dps.yaml").exists() and self.dps.settings.enabled:
            ids.add("aion2.dps")
        if (c / "runs.yaml").exists():
            ids.add("aion2.runs")
        if (c / "bot.yaml").exists():
            ids.add("discord.bot")
        unit = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "systemd" / "user" / OVERLAY_UNIT
        if self.real_config and unit.exists():
            ids.add("aion2.overlay")
        return ids

    def _register_modules(self) -> None:
        m = self.modules
        usb_url = f"ws://127.0.0.1:{self.settings.port}/ws"
        m.register("deck", self.audio.watch, self.media.watch, self.watch_layout_file, self.watch_background,
                   UsbBridge(self.settings.usb, usb_url).watch, self._announce,
                   hook=self._deck_toggled, status=self._deck_status)
        m.register("aion2.dps", self.dps.watch, hook=self._dps_toggled, status=self._dps_status)
        m.register("aion2.runs", self.runs.watch, status=self._runs_status)
        m.register("aion2.overlay", self.overlay.watch, hook=self.overlay.on_module, status=self._overlay_status)
        m.register("discord.bot", hook=self._bot_toggled, status=self._bot_status)
        m.register("updates", self.updates.watch, status=self._updates_status)

    async def _announce(self) -> None:
        """mDNS-Anzeige für Geräte, solange die Touch-Leiste an ist."""
        if not self.mdns:
            return
        announcer = Announcer(self.settings.name, self.settings.port)
        try:
            await announcer.start()
        except OSError as e:
            log.warning("mDNS nicht verfügbar: %s", e)
            return
        try:
            await asyncio.Event().wait()
        finally:
            await announcer.stop()

    async def _deck_toggled(self, on: bool) -> None:
        if not on:
            for dev in list(self.devices):
                await dev.ws.close(code=4003, message=b"module off")

    async def _dps_toggled(self, on: bool) -> None:
        if on and not self.dps.settings.enabled:
            self.dps.save(self.dps.settings.model_copy(update={"enabled": True}))
        if not on:
            self.dps.status, self.dps.detail = "off", ""
            self.state.update(dps=None, dps_active=False)
            await self._dps_changed()

    async def _bot_toggled(self, on: bool) -> None:
        self.bot.enabled = on
        if not on:
            await self.bot.close()

    def _deck_status(self) -> dict:
        return {"devices": len(self.devices), "pages": len(self.layout.pages),
                "items": sum(len(p.items) for p in self.layout.pages), "error": bool(self.layout_error)}

    def _dps_status(self) -> dict:
        top = (self.state.values.get("dps") or {}).get("rows") or []
        return {"status": self.dps.status, "text": STATUS_TEXT[self.dps.status], "active": bool(self.state.values.get("dps_active")),
                "target": (self.state.values.get("dps") or {}).get("target"), "top": top[:3]}

    def _runs_status(self) -> dict:
        r = self.runs
        return {"open_run": bool(r.tracker.run), "posting": bool(r.settings.enabled and r.settings.webhook),
                "last": {"name": r.last.name, "end": r.last.end_ms, "kills": r.last.kills} if r.last else None,
                "result": r.result}

    def _overlay_status(self) -> dict:
        return {"unit": self.overlay.unit, "clients": len(self.overlay.clients)}

    def _bot_status(self) -> dict:
        s = self.bot.settings
        return {"dps": bool(s.dps_enabled and s.dps_url), "runs": bool(s.runs_enabled and s.runs_url and s.runs_token),
                "result": self.bot.result}

    def _updates_status(self) -> dict:
        u = self.updates.state
        return {"available": u.get("available"), "checked_at": u.get("checked_at"), "error": u.get("error")}

    async def _game_running(self) -> bool:
        """Läuft AION 2? Schaut der Mitschnitt ohnehin alle 5 s in /proc, gilt sein Blick."""
        game = self.dps.capture.game
        if self.modules.on("aion2.dps") and self.dps.settings.source == "capture" and game is not None:
            return game
        return await asyncio.to_thread(aion2_running)

    def _history_dir(self) -> Path:
        if self.dps.settings.source == "capture":
            return history_root() / "history"
        return a2tools_dir() / "history"

    # ---------------------------------------------------------------- Verteilung
    async def _send(self, ws: web.WebSocketResponse, text: str) -> None:
        if ws.closed:
            return
        try:
            await ws.send_str(text)
        except (ConnectionError, RuntimeError) as e:  # ConnectionError umfasst Reset + Broken Pipe
            log.debug("Senden fehlgeschlagen: %s", e)

    async def _broadcast_devices(self, text: str) -> None:
        await asyncio.gather(*(self._send(d.ws, text) for d in list(self.devices)))

    async def _broadcast_ui(self, obj: dict) -> None:
        text = json.dumps(obj, ensure_ascii=False)
        await asyncio.gather(*(self._send(ws, text) for ws in list(self.ui_clients)))

    async def _on_state(self, diff: dict) -> None:
        if diff.get("dps"):
            self.runs.observe(diff["dps"])
        await self.overlay.on_state(diff)
        if "art_url" in diff:
            asyncio.ensure_future(self._update_art(diff["art_url"]))
        dev_diff = {k: v for k, v in diff.items() if k not in DEVICE_HIDDEN_KEYS and k != "dps"}
        if dev_diff:
            await self._broadcast_devices(_msg("state", full=False, values=dev_diff))
        if "dps" in diff:
            for dev in list(self.devices):
                self._queue_dps(dev)
        await self._broadcast_ui({"type": "state", "values": diff})

    # ---------------------------------------------------------------- DPS ans Gerät
    def _dps_rows(self, dev: Device) -> int:
        """So viele Zeilen zeigt die aktuelle Seite des Geräts (0 = keine DPS-Kachel). Seite
        unbekannt (alte Firmware): die größte DPS-Kachel im Layout."""
        pages = [p for p in self.layout.pages if p.id == dev.page] or ([] if dev.page else self.layout.pages)
        return max((it.players or DPS_DEFAULT_PLAYERS for p in pages for it in p.items if it.type == "dps"), default=0)

    def _dps_for(self, dev: Device, rows: int) -> dict | None:
        value = self.state.values.get("dps")
        if isinstance(value, dict) and len(value.get("rows") or []) > rows:
            value = {**value, "rows": value["rows"][:rows]}
        return value

    def _queue_dps(self, dev: Device) -> None:
        """DPS höchstens alle DPS_DEVICE_INTERVAL s und nur, solange die Seite eine DPS-Kachel hat.
        Ein schon geplanter Versand nimmt beim Senden den dann neuesten Stand."""
        if dev.dps_task and not dev.dps_task.done():
            return
        if not self._dps_rows(dev):
            return
        wait = dev.dps_sent + DPS_DEVICE_INTERVAL - time.monotonic()
        dev.dps_task = asyncio.ensure_future(self._send_dps(dev, wait))

    async def _send_dps(self, dev: Device, wait: float) -> None:
        if wait > 0:
            await asyncio.sleep(wait)
        rows = self._dps_rows(dev)
        if not rows or dev.ws.closed:
            return
        text = _msg("state", full=False, values={"dps": self._dps_for(dev, rows)})
        if text == dev.dps_last:
            return
        dev.dps_sent, dev.dps_last = time.monotonic(), text
        await self._send(dev.ws, text)

    # ---------------------------------------------------------------- Cover
    async def _update_art(self, url: str | None) -> None:
        if await self.art.set_url(url):
            await asyncio.gather(*(self._send_art(d) for d in list(self.devices) if d.art_size))

    async def _send_bytes(self, ws: web.WebSocketResponse, data: bytes) -> None:
        if ws.closed:
            return
        try:
            await ws.send_bytes(data)
        except (ConnectionError, RuntimeError) as e:
            log.debug("Senden fehlgeschlagen: %s", e)

    async def _send_art(self, dev: Device) -> None:
        async with dev.send_lock:
            r = await self.art.render(dev.art_size)
            if r is None:
                if dev.art_have != "-":
                    await self._send(dev.ws, _msg("art", id=""))
                    dev.art_have = "-"
                return
            aid, data = r
            if aid == dev.art_have:  # hat das Gerät schon (Neuverbindung, zweites art_request)
                return
            if dev.binary:
                for frame in bin_chunks(b"a", aid, dev.art_size, dev.art_size, data):
                    await self._send_bytes(dev.ws, frame)
            else:
                for part in chunks(aid, dev.art_size, dev.art_size, data):
                    await self._send(dev.ws, _msg("art", **part))
            dev.art_have = aid

    # ---------------------------------------------------------------- Hintergrund
    async def _send_bg(self, dev: Device) -> None:
        async with dev.send_lock:
            bid, data = self.bg.id, self.bg.data
            if bid == dev.bg_id:
                return
            if not bid or data is None:
                await self._send(dev.ws, _msg("bg", id=""))
            elif dev.binary:
                for frame in bin_chunks(b"b", bid, 640, 172, data):
                    if dev.ws.closed:
                        return
                    await self._send_bytes(dev.ws, frame)
            else:
                for part in chunks(bid, 640, 172, data):
                    if dev.ws.closed:
                        return
                    await self._send(dev.ws, _msg("bg", **part))
            dev.bg_id = bid

    async def update_background(self, mode: str | None = None) -> None:
        if await self.bg.update(mode):
            await asyncio.gather(*(self._send_bg(d) for d in list(self.devices)))
            await self._broadcast_ui({"type": "background", "id": self.bg.id})

    async def watch_background(self) -> None:
        """Folgt einem neuen Desktop-Hintergrund (bzw. geänderter Bilddatei)."""
        await self.update_background(self.layout.theme.background)
        while True:
            await asyncio.sleep(5)
            await self.update_background()

    # ---------------------------------------------------------------- DPS-Meter
    async def _dps_changed(self) -> None:
        await self._broadcast_ui({"type": "dps", "dps": self.dps.info()})

    async def _updates_changed(self) -> None:
        await self._broadcast_ui({"type": "updates", "updates": self.updates.info()})

    async def _runs_changed(self) -> None:
        await self._broadcast_ui({"type": "runs", "runs": self.runs.info()})

    async def _bot_changed(self) -> None:
        await self._broadcast_ui({"type": "bot", "bot": self.bot.info()})

    async def _overlay_changed(self) -> None:
        await self._broadcast_ui({"type": "overlay", "overlay": self.overlay.info()})

    async def _modules_changed(self) -> None:
        await self._broadcast_ui({"type": "modules", "modules": self.modules.info()})

    async def _on_combat(self, active: bool) -> None:
        """Kampfbeginn: auf die DPS-Seite wechseln; Kampfende: zurück, wenn dort noch."""
        page = self.dps.settings.auto_page
        page_ids = [p.id for p in self.layout.pages]
        if not page or page not in page_ids:
            return
        for dev in list(self.devices):
            if active:
                if dev.page != page:
                    dev.return_page = dev.page or page_ids[0]
                    log.info("Kampfbeginn: %s wechselt zu Seite '%s'", dev.id, page)
                    await self._send(dev.ws, _msg("goto", page=page))
            else:
                back, dev.return_page = dev.return_page, None
                # nur zurück, wenn niemand inzwischen selbst weggewischt hat
                if back and back in page_ids and dev.page == page and self.dps.settings.return_after:
                    log.info("Kampfende: %s zurück zu Seite '%s'", dev.id, back)
                    await self._send(dev.ws, _msg("goto", page=back))

    async def _devices_changed(self) -> None:
        await self._broadcast_ui({"type": "devices", "devices": [d.info() for d in self.devices]})

    async def apply_layout(self, layout: Layout, save: bool) -> None:
        if save:
            save_layout(self.layout_path, layout)
            self._layout_mtime = self.layout_path.stat().st_mtime
        self.layout = layout
        self.layout_payload = layout.device_payload()
        self.layout_error = None
        log.info("Layout aktualisiert (hash %s), an %d Gerät(e)", self.layout_payload["hash"], len(self.devices))
        await self._broadcast_devices(_msg("layout", **self.layout_payload))
        await self._broadcast_ui({"type": "layout", "layout": self.layout_json(), "error": None})
        await self.update_background(layout.theme.background)

    def layout_json(self) -> dict:
        return self.layout.model_dump(mode="json", exclude_none=True)

    async def watch_layout_file(self) -> None:
        """Übernimmt Handänderungen an layout.yaml ohne Neustart."""
        while True:
            await asyncio.sleep(1)
            try:
                mtime = self.layout_path.stat().st_mtime
            except FileNotFoundError:
                continue
            if mtime == self._layout_mtime:
                continue
            self._layout_mtime = mtime
            try:
                data = yaml.safe_load(self.layout_path.read_text()) or {}
                await self.apply_layout(Layout.model_validate(data), save=False)
            except (yaml.YAMLError, ValidationError) as e:
                text = _validation_text(e) if isinstance(e, ValidationError) else str(e)
                self.layout_error = text
                log.error("layout.yaml ungültig, altes Layout bleibt aktiv:\n%s", text)
                await self._broadcast_ui({"type": "layout_error", "error": text})

    # ---------------------------------------------------------------- Ereignisse
    async def handle_event(self, msg: dict, source: str) -> str | None:
        event = msg.get("event")
        if event == "page_change":
            return None
        item_id = msg.get("item")
        item = self.layout.find_item(item_id) if isinstance(item_id, str) else None
        if item is None:
            return f"unbekanntes Item '{item_id}'"
        value = msg.get("value")
        if value is not None and not isinstance(value, int):
            return "value muss eine Ganzzahl sein"
        part = msg.get("part")
        log.debug("%s: %s %s value=%s part=%s", source, event, item_id, value, part)
        await self.executor.on_event(item, event, value, part)
        return None

    async def close_clients(self) -> None:
        """Beim Beenden: Geräte, Web-UI-Tabs und Overlay-Streams trennen, damit aiohttp nicht auf
        offene Handler wartet. Geräte verbinden sich nach dem Neustart von selbst wieder."""
        self.overlay.close_clients()
        sockets = [d.ws for d in list(self.devices)] + list(self.ui_clients)
        if sockets:
            await asyncio.wait([asyncio.ensure_future(ws.close(code=WSCloseCode.GOING_AWAY, message=b"shutdown"))
                                for ws in sockets], timeout=2)

    # ---------------------------------------------------------------- Geräte-WebSocket
    async def ws_device(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(max_msg_size=MAX_MSG, heartbeat=None)
        await ws.prepare(request)
        if not self.modules.on("deck"):
            await self._send(ws, _msg("error", code="disabled", message="Modul Touch-Leiste ist ausgeschaltet"))
            await ws.close(code=4003, message=b"module off")
            return ws
        dev = Device(ws=ws, remote=request.remote or "?")
        hb = self.settings.heartbeat

        # 1. hello innerhalb von 5 s
        try:
            first = await ws.receive(timeout=5)
        except TimeoutError:
            await ws.close(code=4000, message=b"hello timeout")
            return ws
        if first.type != WSMsgType.TEXT:
            await ws.close()
            return ws
        try:
            hello = json.loads(first.data)
        except json.JSONDecodeError:
            hello = {}
        if hello.get("type") != "hello":
            await self._send(ws, _msg("error", code="bad_request", message="erste Nachricht muss hello sein"))
            await ws.close()
            return ws
        if hello.get("v") != PROTO_V:
            await self._send(ws, _msg("error", code="version", message=f"Daemon spricht v{PROTO_V}"))
            await ws.close()
            return ws
        token = str(hello.get("token", ""))
        if not hmac.compare_digest(token.encode(), self.settings.token.encode()):
            log.warning("Gerät %s: falsches Token", dev.remote)
            await self._send(ws, _msg("error", code="auth", message="falsches Token"))
            await ws.close(code=4001, message=b"auth")
            return ws

        info = hello.get("device") or {}
        dev.id = str(info.get("id", "?"))[:64]
        dev.model = str(info.get("model", ""))[:64]
        dev.fw = str(info.get("fw", ""))[:32]
        dev.sim = bool(info.get("sim", False))
        dev.bg_id = str(hello.get("bg_id", ""))[:16]
        caps = hello.get("caps")
        dev.binary = isinstance(caps, list) and "bin" in caps
        page = hello.get("page")
        dev.page = page if isinstance(page, str) and page else None
        self.devices.add(dev)
        log.info("Gerät verbunden: %s (%s) von %s", dev.id, dev.model or "?", dev.remote)
        await self._devices_changed()

        await self._send(ws, _msg("welcome", server={"name": self.settings.name, "version": __version__}, heartbeat=hb))
        if hello.get("layout_hash") != self.layout_payload["hash"]:
            await self._send(ws, _msg("layout", **self.layout_payload))
        values = {k: v for k, v in self.state.values.items() if k not in DEVICE_HIDDEN_KEYS}
        if "dps" in values:
            values["dps"] = self._dps_for(dev, self._dps_rows(dev) or DPS_DEFAULT_PLAYERS)
        await self._send(ws, _msg("state", full=True, values=values))
        asyncio.ensure_future(self._send_bg(dev))

        async def heartbeat():
            while not ws.closed:
                await asyncio.sleep(hb)
                if time.monotonic() - dev.last_seen > 3 * hb:
                    log.warning("Gerät %s antwortet nicht mehr, trenne", dev.id)
                    await ws.close(code=4002, message=b"heartbeat")
                    return
                await self._send(ws, _msg("ping", t=int(time.time() * 1000)))

        hb_task = asyncio.ensure_future(heartbeat())
        try:
            async for m in ws:
                if m.type != WSMsgType.TEXT:
                    continue
                dev.last_seen = time.monotonic()
                try:
                    msg = json.loads(m.data)
                except json.JSONDecodeError:
                    await self._send(ws, _msg("error", code="bad_request", message="kein JSON"))
                    continue
                t = msg.get("type")
                if t == "pong":
                    continue
                if t == "ping":
                    await self._send(ws, _msg("pong", t=msg.get("t", 0)))
                elif t == "art_request":
                    size = msg.get("size")
                    dev.art_size = size if isinstance(size, int) and 0 < size <= ART_MAX_SIZE else 0
                    have = msg.get("have")
                    dev.art_have = have[:16] if isinstance(have, str) else ""
                    if dev.art_size:
                        asyncio.ensure_future(self._send_art(dev))
                elif t == "event":
                    if msg.get("event") == "page_change":
                        dev.page = msg.get("page")
                        self._queue_dps(dev)  # auf eine DPS-Seite gewechselt: aktuellen Stand nachreichen
                        await self._devices_changed()
                    err = await self.handle_event(msg, dev.id)
                    if err:
                        await self._send(ws, _msg("error", code="bad_request", message=err))
                else:
                    log.debug("Gerät %s: unbekannter Typ %r", dev.id, t)
        finally:
            hb_task.cancel()
            if dev.dps_task:
                dev.dps_task.cancel()
            self.devices.discard(dev)
            log.info("Gerät getrennt: %s", dev.id)
            await self._devices_changed()
        return ws

    # ---------------------------------------------------------------- Web-UI / API
    async def ws_ui(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(heartbeat=20)
        await ws.prepare(request)
        self.ui_clients.add(ws)
        await self._send(ws, json.dumps({
            "type": "hello",
            "layout": self.layout_json(),
            "error": self.layout_error,
            "state": self.state.values,
            "devices": [d.info() for d in self.devices],
            "status": self.status(),
            "dps": self.dps.info(),
            "runs": self.runs.info(),
            "updates": self.updates.info(),
            "modules": self.modules.info(),
            "bot": self.bot.info(),
            "overlay": self.overlay.info(),
            "settings": self.settings_info(),
        }, ensure_ascii=False))
        try:
            async for m in ws:
                if m.type != WSMsgType.TEXT:
                    continue
                try:
                    msg = json.loads(m.data)
                except json.JSONDecodeError:
                    continue
                # Die Vorschau in der Web-UI verhält sich wie ein Gerät
                if msg.get("type") == "event":
                    err = await self.handle_event(msg, "web-ui")
                    if err:
                        await self._send(ws, json.dumps({"type": "error", "error": err}))
        finally:
            self.ui_clients.discard(ws)
        return ws

    def status(self) -> dict:
        return {
            "version": __version__,
            "port": self.settings.port,
            "name": self.settings.name,
            "layout_path": str(self.layout_path),
            "tools": {t: have(t) for t in ("wpctl", "pactl", "playerctl", "ydotool", "xdg-open")},
            "last_error": self.executor.last_error,
            "background": {"mode": self.bg.mode, "source": str(self.bg.source) if self.bg.source else None,
                           "id": self.bg.id},
        }

    async def api_get_layout(self, request: web.Request) -> web.Response:
        return web.json_response({"layout": self.layout_json(), "error": self.layout_error,
                                  "device_payload": self.layout_payload})

    async def api_put_layout(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            layout = Layout.model_validate(data)
        except json.JSONDecodeError:
            return web.json_response({"error": "kein JSON"}, status=400)
        except ValidationError as e:
            return web.json_response({"error": _validation_text(e)}, status=422)
        await self.apply_layout(layout, save=True)
        return web.json_response({"ok": True, "hash": self.layout_payload["hash"]})

    async def api_status(self, request: web.Request) -> web.Response:
        return web.json_response({**self.status(), "devices": [d.info() for d in self.devices],
                                  "state": self.state.values})

    async def api_trigger(self, request: web.Request) -> web.Response:
        msg = await request.json()
        err = await self.handle_event(msg, "api")
        if err:
            return web.json_response({"error": err}, status=400)
        return web.json_response({"ok": True, "error": self.executor.last_error})

    async def api_post_state(self, request: web.Request) -> web.Response:
        """Eigene State-Schlüssel setzen, z. B. aus Skripten:
        curl -X POST localhost:8765/api/state -d '{"obs_rec": true}'"""
        try:
            data = await request.json()
        except json.JSONDecodeError:
            return web.json_response({"error": "kein JSON"}, status=400)
        if not isinstance(data, dict):
            return web.json_response({"error": "Objekt erwartet"}, status=400)
        builtin = set(BUILTIN_KEYS) & data.keys()
        if builtin:
            return web.json_response({"error": f"eingebaute Schlüssel sind schreibgeschützt: {', '.join(sorted(builtin))}"}, status=400)
        bad = [k for k in data if not isinstance(k, str) or not k or len(k) > 32]
        if bad:
            return web.json_response({"error": "Schlüssel: 1–32 Zeichen"}, status=400)
        self.state.update(**data)
        return web.json_response({"ok": True})

    async def api_get_dps(self, request: web.Request) -> web.Response:
        return web.json_response(self.dps.info())

    async def api_put_dps(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            if not isinstance(data, dict):
                raise ValueError
        except ValueError:
            return web.json_response({"error": "kein JSON-Objekt"}, status=400)
        # Platzhalter aus info() = Schlüssel unverändert lassen
        if "key" not in data or set(str(data["key"])) == {"•"}:
            data["key"] = self.dps.settings.key
        try:
            settings = DpsSettings.model_validate(data)
        except ValidationError as e:
            return web.json_response({"error": _validation_text(e)}, status=422)
        self.dps.save(settings)
        await self._dps_changed()
        return web.json_response({"ok": True, **self.dps.info()})

    async def api_get_updates(self, request: web.Request) -> web.Response:
        return web.json_response(self.updates.info())

    async def api_check_updates(self, request: web.Request) -> web.Response:
        await self.updates.check()
        return web.json_response(self.updates.info())

    async def api_run_update(self, request: web.Request) -> web.Response:
        try:
            result = await self.updates.run()
        except (RuntimeError, OSError) as e:
            return web.json_response({"error": str(e)}, status=500)
        return web.json_response({"ok": True, "result": result})

    async def api_get_runs(self, request: web.Request) -> web.Response:
        return web.json_response(self.runs.info())

    async def api_put_runs(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            if not isinstance(data, dict):
                raise ValueError
        except ValueError:
            return web.json_response({"error": "kein JSON-Objekt"}, status=400)
        # Platzhalter aus info() = Webhook unverändert lassen
        if "webhook" not in data or set(str(data["webhook"])) == {"•"}:
            data["webhook"] = self.runs.settings.webhook
        try:
            settings = RunSettings.model_validate(data)
        except ValidationError as e:
            return web.json_response({"error": _validation_text(e)}, status=422)
        self.runs.save(settings)
        await self._runs_changed()
        return web.json_response({"ok": True, **self.runs.info()})

    async def api_runs_preview(self, request: web.Request) -> web.Response:
        """Letzter Run als PNG, so wie er nach Discord ginge."""
        run = await asyncio.to_thread(self.runs.latest_run)
        if not run:
            return web.json_response({"error": "noch kein Dungeon-Run in der History"}, status=404)
        png = await asyncio.to_thread(render_run, run)
        return web.Response(body=png, content_type="image/png", headers={"Cache-Control": "no-store"})

    async def api_runs_test(self, request: web.Request) -> web.Response:
        """Letzten Run jetzt nach Discord schicken (Knopf in der Web-UI)."""
        if not self.runs.settings.webhook:
            return web.json_response({"error": "keine Webhook-URL eingetragen"}, status=400)
        run = await asyncio.to_thread(self.runs.latest_run)
        if not run:
            return web.json_response({"error": "noch kein Dungeon-Run in der History"}, status=404)
        async with ClientSession(timeout=ClientTimeout(total=30)) as session:
            ok = await self.runs.post(session, run)
        await self._runs_changed()
        if not ok:
            return web.json_response({"error": self.runs.result}, status=502)
        return web.json_response({"ok": True, **self.runs.info()})

    async def api_background(self, request: web.Request) -> web.StreamResponse:
        """Aktueller Hintergrund als PNG (Vorschau in der Web-UI)."""
        if self.bg.png is None:
            return web.FileResponse(WEB_DIR / "bg.png", headers={"Cache-Control": "no-cache"})
        return web.Response(body=self.bg.png, content_type="image/png", headers={"Cache-Control": "no-cache"})

    async def api_upload_background(self, request: web.Request) -> web.Response:
        """Bild aus der Web-UI annehmen (roher Body). Antwortet mit dem Pfad für theme.background."""
        data = bytearray()
        async for chunk in request.content.iter_chunked(64 * 1024):
            data += chunk
            if len(data) > UPLOAD_MAX:
                return web.json_response({"error": "Bild zu groß (max. 20 MB)"}, status=413)
        try:
            path = await asyncio.to_thread(save_upload, bytes(data), self.upload_dir)
        except ValueError as e:
            return web.json_response({"error": str(e)}, status=422)
        log.info("Hintergrund hochgeladen: %s", path)
        return web.json_response({"ok": True, "path": str(path)})

    # ---------------------------------------------------------------- Module, Einstellungen
    async def api_get_modules(self, request: web.Request) -> web.Response:
        return web.json_response(self.modules.info())

    async def api_put_module(self, request: web.Request) -> web.Response:
        mid = request.match_info["id"]
        try:
            data = await request.json()
            on = data["enabled"]
            if not isinstance(on, bool):
                raise TypeError
        except (ValueError, KeyError, TypeError):
            return web.json_response({"error": 'erwartet {"enabled": true|false}'}, status=400)
        try:
            changed = await self.modules.set(mid, on)
        except KeyError:
            return web.json_response({"error": f"Modul {mid} gibt es nicht"}, status=404)
        return web.json_response({"ok": True, "changed": changed, **self.modules.info()})

    def settings_info(self) -> dict:
        s = self.settings.model_dump()
        s["token"] = "•" * 8
        return {"settings": s, "config_dir": str(self.config_dir), "restart_fields": list(RESTART_FIELDS)}

    async def api_get_settings(self, request: web.Request) -> web.Response:
        return web.json_response(self.settings_info())

    async def api_put_settings(self, request: web.Request) -> web.Response:
        """Allgemeine Einstellungen (config.yaml). Port, Adresse und Token wirken erst nach einem Neustart."""
        try:
            data = await request.json()
            if not isinstance(data, dict):
                raise ValueError
        except ValueError:
            return web.json_response({"error": "kein JSON-Objekt"}, status=400)
        merged = self.settings.model_dump()
        for k, v in data.items():
            if k == "token" and (not v or set(str(v)) == {"•"}):
                continue
            merged[k] = v
        try:
            settings = Settings.model_validate(merged)
        except ValidationError as e:
            return web.json_response({"error": _validation_text(e)}, status=422)
        save_settings(self.config_dir, settings)
        restart = [k for k in RESTART_FIELDS if getattr(settings, k) != getattr(self.settings, k)]
        # was sofort wirken kann, gleich übernehmen
        live = settings.model_copy(update={k: getattr(self.settings, k) for k in RESTART_FIELDS})
        self.settings = live
        self.media.player = live.player
        await self._broadcast_ui({"type": "settings", "settings": self.settings_info()})
        return web.json_response({"ok": True, "restart": restart, **self.settings_info()})

    async def api_get_token(self, request: web.Request) -> web.Response:
        """Geräte-Token im Klartext (für die Firmware-Konfiguration), nur auf ausdrückliche Anfrage."""
        return web.json_response({"token": self.settings.token})

    async def api_restart(self, request: web.Request) -> web.Response:
        self.restart_requested = True
        asyncio.get_running_loop().call_later(0.3, os.kill, os.getpid(), 15)  # SIGTERM → sauber beenden
        return web.json_response({"ok": True})

    # ---------------------------------------------------------------- Discord-Bot
    async def api_get_bot(self, request: web.Request) -> web.Response:
        return web.json_response(self.bot.info())

    async def api_put_bot(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            if not isinstance(data, dict):
                raise ValueError
        except ValueError:
            return web.json_response({"error": "kein JSON-Objekt"}, status=400)
        try:
            self.bot.update(data)
        except ValidationError as e:
            return web.json_response({"error": _validation_text(e)}, status=422)
        await self._bot_changed()
        return web.json_response({"ok": True, **self.bot.info()})

    async def api_bot_test(self, request: web.Request) -> web.Response:
        if not self.modules.on("discord.bot"):
            return web.json_response({"error": "Modul Discord-Bot ist aus"}, status=409)
        kind = request.match_info["kind"]
        if kind == "dps":
            ok, text = await self.bot.test_fight()
        else:
            run = await asyncio.to_thread(self.runs.latest_run)
            ok, text = await self.bot.test_run(run)
        if not ok:
            return web.json_response({"error": text}, status=502 if "antwortet" in text or ":" in text else 400)
        return web.json_response({"ok": True, "text": text, **self.bot.info()})

    # ---------------------------------------------------------------- Overlay
    async def api_get_overlay(self, request: web.Request) -> web.Response:
        if self.modules.on("aion2.overlay"):
            await self.overlay.refresh_unit()
        return web.json_response(self.overlay.info())

    async def api_put_overlay(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            if not isinstance(data, dict):
                raise ValueError
        except ValueError:
            return web.json_response({"error": "kein JSON-Objekt"}, status=400)
        try:
            await self.overlay.update(data)
        except ValidationError as e:
            return web.json_response({"error": _validation_text(e)}, status=422)
        return web.json_response({"ok": True, **self.overlay.info()})

    async def api_overlay_command(self, request: web.Request) -> web.Response:
        try:
            cmd = str((await request.json())["cmd"])
            await self.overlay.command(cmd)
        except (ValueError, KeyError, TypeError) as e:
            return web.json_response({"error": str(e) or "erwartet {cmd}"}, status=400)
        except RuntimeError as e:
            return web.json_response({"error": str(e)}, status=409)
        return web.json_response({"ok": True})

    async def api_overlay_service(self, request: web.Request) -> web.Response:
        """Overlay-Programm neu starten (nach Änderungen an Monitor oder GPU)."""
        if not self.modules.on("aion2.overlay"):
            return web.json_response({"error": "Modul Overlay ist aus"}, status=409)
        code, out = await self.overlay._systemctl("restart", OVERLAY_UNIT)
        await self.overlay.refresh_unit()
        await self._overlay_changed()
        if code:
            return web.json_response({"error": out or "Neustart ging nicht"}, status=500)
        return web.json_response({"ok": True, **self.overlay.info()})

    async def index(self, request: web.Request) -> web.FileResponse:
        return web.FileResponse(WEB_DIR / "index.html", headers={"Cache-Control": "no-cache"})


@web.middleware
async def local_only(request: web.Request, handler):
    """Alles außer /ws nur von localhost, plus Host-/Origin-Prüfung gegen DNS-Rebinding."""
    if request.path == "/ws":
        return await handler(request)
    remote = request.remote or ""
    if remote.startswith("::ffff:"):
        remote = remote[7:]
    host = (request.host or "").rsplit(":", 1)[0].strip("[]")
    if remote not in LOCAL_HOSTS or host not in LOCAL_HOSTS:
        raise web.HTTPForbidden(text="Die NexBoard-Konfiguration ist nur über localhost erreichbar.")
    origin = request.headers.get("Origin")
    if origin and request.method not in ("GET", "HEAD"):
        o_host = origin.split("://", 1)[-1].rsplit(":", 1)[0].strip("[]")
        if o_host not in LOCAL_HOSTS:
            raise web.HTTPForbidden(text="fremder Origin")
    return await handler(request)


def build_app(deck: NexBoard) -> web.Application:
    app = web.Application(middlewares=[local_only], client_max_size=256 * 1024)
    app.router.add_get("/ws", deck.ws_device)
    app.router.add_get("/", deck.index)
    app.router.add_get("/api/live", deck.ws_ui)
    app.router.add_get("/api/layout", deck.api_get_layout)
    app.router.add_put("/api/layout", deck.api_put_layout)
    app.router.add_get("/api/status", deck.api_status)
    app.router.add_post("/api/trigger", deck.api_trigger)
    app.router.add_post("/api/state", deck.api_post_state)
    app.router.add_get("/api/background.png", deck.api_background)
    app.router.add_post("/api/background", deck.api_upload_background)
    app.router.add_get("/api/dps", deck.api_get_dps)
    app.router.add_put("/api/dps", deck.api_put_dps)
    app.router.add_get("/api/runs", deck.api_get_runs)
    app.router.add_get("/api/updates", deck.api_get_updates)
    app.router.add_post("/api/updates/check", deck.api_check_updates)
    app.router.add_post("/api/updates/run", deck.api_run_update)
    app.router.add_put("/api/runs", deck.api_put_runs)
    app.router.add_get("/api/runs/preview.png", deck.api_runs_preview)
    app.router.add_post("/api/runs/test", deck.api_runs_test)
    app.router.add_get("/api/modules", deck.api_get_modules)
    app.router.add_put("/api/modules/{id}", deck.api_put_module)
    app.router.add_get("/api/settings", deck.api_get_settings)
    app.router.add_put("/api/settings", deck.api_put_settings)
    app.router.add_post("/api/settings/token", deck.api_get_token)
    app.router.add_post("/api/restart", deck.api_restart)
    app.router.add_get("/api/bot", deck.api_get_bot)
    app.router.add_put("/api/bot", deck.api_put_bot)
    app.router.add_post("/api/bot/test/{kind:dps|runs}", deck.api_bot_test)
    app.router.add_get("/api/overlay", deck.api_get_overlay)
    app.router.add_put("/api/overlay", deck.api_put_overlay)
    app.router.add_post("/api/overlay/command", deck.api_overlay_command)
    app.router.add_post("/api/overlay/restart", deck.api_overlay_service)
    app.router.add_static("/static/", WEB_DIR)

    async def cleanup(_app: web.Application) -> None:
        await deck.art.close()
        await deck.bot.close()

    app.on_cleanup.append(cleanup)
    return app
