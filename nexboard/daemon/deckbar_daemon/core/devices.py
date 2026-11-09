"""Geräte-WebSocket (/ws): Anmeldung, Layout, State, Cover, Hintergrund, DPS-Takt, Seitenwechsel.

Das Gerät kennt keine Aktionen: Ereignisse gehen an den angemeldeten Empfänger (Modul Touch-Leiste).
"""
from __future__ import annotations

import asyncio
import hmac
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from aiohttp import WSCloseCode, WSMsgType, web
from nexproto import device

from .. import __version__
from ..art import Art, bin_chunks, chunks
from ..background import Background
from ..config import Settings, device_message
from ..deck_layout import DeckLayout
from ..state import State
from .live import EventHandler, LiveHub, send_text

log = logging.getLogger(__name__)

# nur für Daemon/Web-UI; das Gerät bekommt das Cover als Bild per `art`
DEVICE_HIDDEN_KEYS = {"art_url"}
DPS_DEVICE_INTERVAL = 1.0  # DPS höchstens 1× pro Sekunde je Gerät (die Kachel zeigt ganze Sekunden)
SWIPED_STAY_S = 30  # selbst auf die DPS-Seite gewischt: so lange bleibt sie ohne Kampf stehen
CLOSE_MODULE_OFF = 4003


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
    dps_task: asyncio.Task[None] | None = None
    return_task: asyncio.Task[None] | None = None  # verzögerter Rückweg von der DPS-Seite (follow_combat)
    # Bildübertragungen pro Gerät nacheinander, damit sich Teile zweier Bilder nicht mischen
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def info(self) -> dict[str, Any]:
        return {
            "id": self.id, "model": self.model, "fw": self.fw, "sim": self.sim,
            "remote": self.remote, "page": self.page, "connected_at": self.connected_at,
        }

    def take_hello(self, hello: dict[str, Any]) -> None:
        info = hello.get("device") or {}
        self.id = str(info.get("id", "?"))[:64]
        self.model = str(info.get("model", ""))[:64]
        self.fw = str(info.get("fw", ""))[:32]
        self.sim = bool(info.get("sim", False))
        self.bg_id = str(hello.get("bg_id", ""))[:device.IMAGE_ID_MAX]
        caps = hello.get("caps")
        self.binary = isinstance(caps, list) and "bin" in caps
        page = hello.get("page")
        self.page = page if isinstance(page, str) and page else None

    def cancel_tasks(self) -> None:
        for task in (self.dps_task, self.return_task):
            if task:
                task.cancel()


async def send_bytes(ws: web.WebSocketResponse, data: bytes) -> None:
    if ws.closed:
        return
    try:
        await ws.send_bytes(data)
    except (ConnectionError, RuntimeError) as e:
        log.debug("Senden fehlgeschlagen: %s", e)


class DeviceHub:
    def __init__(self, settings: Callable[[], Settings], layout: DeckLayout, state: State, art: Art,
                 bg: Background, live: LiveHub, enabled: Callable[[], bool], on_event: EventHandler,
                 auto_page: Callable[[], str | None]) -> None:
        self.settings = settings
        self.layout = layout
        self.state = state
        self.art = art
        self.bg = bg
        self.live = live
        self.enabled = enabled
        self.on_event = on_event
        self.auto_page = auto_page  # DPS-Seite, zu der die Leiste im Kampf wechselt
        self.devices: set[Device] = set()
        live.section("devices", self.info)

    def info(self) -> list[dict[str, Any]]:
        return [d.info() for d in self.devices]

    async def changed(self) -> None:
        await self.live.send({"type": "devices", "devices": self.info()})

    # ---------------------------------------------------------------- Verteilung
    async def broadcast(self, text: str) -> None:
        await asyncio.gather(*(send_text(d.ws, text) for d in list(self.devices)))

    async def send_layout(self) -> None:
        await self.broadcast(device_message("layout", **self.layout.payload))

    async def on_state(self, diff: dict[str, Any]) -> None:
        if "art_url" in diff and any(d.art_size for d in self.devices):
            # ohne Gerät mit Media-Kachel nichts herunterladen; send_art holt es bei Bedarf nach
            asyncio.ensure_future(self.update_art(diff["art_url"]))
        dev_diff = {k: v for k, v in diff.items() if k not in DEVICE_HIDDEN_KEYS and k != "dps"}
        if dev_diff:
            await self.broadcast(device_message("state", full=False, values=dev_diff))
        if "dps" in diff:
            for dev in list(self.devices):
                self.queue_dps(dev)

    async def close_all(self, code: int = WSCloseCode.GOING_AWAY, message: bytes = b"shutdown") -> None:
        """Alle Geräte trennen; sie verbinden sich von selbst wieder."""
        sockets = [d.ws for d in list(self.devices)]
        if sockets:
            await asyncio.wait([asyncio.ensure_future(ws.close(code=code, message=message)) for ws in sockets],
                               timeout=2)

    # ---------------------------------------------------------------- DPS ans Gerät
    def dps_rows(self, dev: Device) -> int:
        """So viele Zeilen zeigt die aktuelle Seite des Geräts (0 = keine DPS-Kachel). Seite
        unbekannt (alte Firmware): die größte DPS-Kachel im Layout."""
        all_pages = self.layout.layout.pages
        pages = [p for p in all_pages if p.id == dev.page] or ([] if dev.page else all_pages)
        players = [it.players or device.DPS_DEFAULT_PLAYERS for p in pages for it in p.items if it.type == "dps"]
        return max(players, default=0)

    def dps_for(self, rows: int) -> dict[str, Any] | None:
        value = self.state.values.get("dps")
        if isinstance(value, dict) and len(value.get("rows") or []) > rows:
            value = {**value, "rows": value["rows"][:rows]}
        return value

    def queue_dps(self, dev: Device) -> None:
        """DPS höchstens alle DPS_DEVICE_INTERVAL s und nur, solange die Seite eine DPS-Kachel hat.
        Ein schon geplanter Versand nimmt beim Senden den dann neuesten Stand."""
        if dev.dps_task and not dev.dps_task.done():
            return
        if not self.dps_rows(dev):
            return
        wait = dev.dps_sent + DPS_DEVICE_INTERVAL - time.monotonic()
        dev.dps_task = asyncio.ensure_future(self._send_dps(dev, wait))

    async def _send_dps(self, dev: Device, wait: float) -> None:
        if wait > 0:
            await asyncio.sleep(wait)
        rows = self.dps_rows(dev)
        if not rows or dev.ws.closed:
            return
        text = device_message("state", full=False, values={"dps": self.dps_for(rows)})
        if text == dev.dps_last:
            return
        dev.dps_sent, dev.dps_last = time.monotonic(), text
        await send_text(dev.ws, text)

    # ---------------------------------------------------------------- Cover und Hintergrund
    async def update_art(self, url: str | None) -> None:
        if await self.art.set_url(url):
            await asyncio.gather(*(self.send_art(d) for d in list(self.devices) if d.art_size))

    async def send_art(self, dev: Device) -> None:
        async with dev.send_lock:
            await self.art.set_url(self.state.values.get("art_url"))  # nachholen, falls ohne Gerät übersprungen
            r = await self.art.render(dev.art_size)
            if r is None:
                if dev.art_have != "-":
                    await send_text(dev.ws, device_message("art", id=""))
                    dev.art_have = "-"
                return
            aid, data = r
            if aid == dev.art_have:  # hat das Gerät schon (Neuverbindung, zweites art_request)
                return
            if dev.binary:
                for frame in bin_chunks(b"a", aid, dev.art_size, dev.art_size, data):
                    await send_bytes(dev.ws, frame)
            else:
                for part in chunks(aid, dev.art_size, dev.art_size, data):
                    await send_text(dev.ws, device_message("art", **part))
            dev.art_have = aid

    async def send_bg(self, dev: Device) -> None:
        async with dev.send_lock:
            bid, data = self.bg.id, self.bg.data
            if bid == dev.bg_id:
                return
            if not bid or data is None:
                await send_text(dev.ws, device_message("bg", id=""))
            elif dev.binary:
                for frame in bin_chunks(b"b", bid, device.SCREEN_W, device.SCREEN_H, data):
                    if dev.ws.closed:
                        return
                    await send_bytes(dev.ws, frame)
            else:
                for part in chunks(bid, device.SCREEN_W, device.SCREEN_H, data):
                    if dev.ws.closed:
                        return
                    await send_text(dev.ws, device_message("bg", **part))
            dev.bg_id = bid

    async def send_bg_all(self) -> None:
        await asyncio.gather(*(self.send_bg(d) for d in list(self.devices)))

    # ---------------------------------------------------------------- Seite im Kampf
    async def on_combat(self, active: bool) -> None:
        for dev in list(self.devices):
            await self.follow_combat(dev, combat_start=active)

    async def follow_combat(self, dev: Device, combat_start: bool = False, delay: float = 0) -> None:
        """Die DPS-Seite nur, solange wirklich ein Kampf läuft; sonst die erste Seite.
        Im Kampf darf man selbst wegwischen. delay: Rückweg erst nach so vielen Sekunden, falls dann
        immer noch kein Kampf läuft (selbst hingewischt)."""
        page = self.auto_page()
        page_ids = [p.id for p in self.layout.layout.pages]
        if not page or page not in page_ids:
            return
        if combat_start:
            target = page
        elif dev.page == page and not self.state.values.get("dps_active"):
            target = page_ids[0]
        else:
            return
        if dev.page == target:
            return
        if delay:
            dev.return_task = asyncio.ensure_future(self._return_later(dev, delay))
            return
        log.info("%s wechselt zu Seite '%s'", dev.id, target)
        await send_text(dev.ws, device_message("goto", page=target))

    async def _return_later(self, dev: Device, delay: float) -> None:
        await asyncio.sleep(delay)
        await self.follow_combat(dev)

    # ---------------------------------------------------------------- Verbindung
    async def handler(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(max_msg_size=device.MAX_MESSAGE_BYTES, heartbeat=None)
        await ws.prepare(request)
        if not self.enabled():
            await self._refuse(ws, "disabled", "Modul Touch-Leiste ist ausgeschaltet", CLOSE_MODULE_OFF, b"module off")
            return ws
        dev = Device(ws=ws, remote=request.remote or "?")
        if not await self._login(dev):
            return ws
        self.devices.add(dev)
        log.info("Gerät verbunden: %s (%s) von %s", dev.id, dev.model or "?", dev.remote)
        await self.changed()
        heartbeat = asyncio.ensure_future(self._heartbeat(dev))
        try:
            async for m in ws:
                if m.type == WSMsgType.TEXT:
                    dev.last_seen = time.monotonic()
                    await self._message(dev, m.data)
        finally:
            heartbeat.cancel()
            dev.cancel_tasks()
            self.devices.discard(dev)
            log.info("Gerät getrennt: %s", dev.id)
            await self.changed()
        return ws

    async def _refuse(self, ws: web.WebSocketResponse, code: str, text: str, close: int = WSCloseCode.OK,
                      reason: bytes = b"") -> None:
        await send_text(ws, device_message("error", code=code, message=text))
        await ws.close(code=close, message=reason)

    async def _login(self, dev: Device) -> bool:
        """hello innerhalb von HELLO_TIMEOUT_S prüfen, dann begrüßen und den ganzen Stand schicken."""
        ws, settings = dev.ws, self.settings()
        try:
            first = await ws.receive(timeout=device.HELLO_TIMEOUT_S)
        except TimeoutError:
            await ws.close(code=4000, message=b"hello timeout")
            return False
        if first.type != WSMsgType.TEXT:
            await ws.close()
            return False
        try:
            hello = json.loads(first.data)
        except json.JSONDecodeError:
            hello = {}
        if hello.get("type") != "hello":
            await self._refuse(ws, "bad_request", "erste Nachricht muss hello sein")
            return False
        if hello.get("v") != device.PROTO_VERSION:
            await self._refuse(ws, "version", f"Daemon spricht v{device.PROTO_VERSION}")
            return False
        if not hmac.compare_digest(str(hello.get("token", "")).encode(), settings.token.encode()):
            log.warning("Gerät %s: falsches Token", dev.remote)
            await self._refuse(ws, "auth", "falsches Token", 4001, b"auth")
            return False
        dev.take_hello(hello)
        await send_text(ws, device_message("welcome", server={"name": settings.name, "version": __version__},
                                           heartbeat=settings.heartbeat))
        if hello.get("layout_hash") != self.layout.payload["hash"]:
            await send_text(ws, device_message("layout", **self.layout.payload))
        values = {k: v for k, v in self.state.values.items() if k not in DEVICE_HIDDEN_KEYS}
        if "dps" in values:
            values["dps"] = self.dps_for(self.dps_rows(dev) or device.DPS_DEFAULT_PLAYERS)
        await send_text(ws, device_message("state", full=True, values=values))
        asyncio.ensure_future(self.send_bg(dev))
        await self.follow_combat(dev)
        return True

    async def _heartbeat(self, dev: Device) -> None:
        interval = self.settings().heartbeat
        while not dev.ws.closed:
            await asyncio.sleep(interval)
            if time.monotonic() - dev.last_seen > 3 * interval:
                log.warning("Gerät %s antwortet nicht mehr, trenne", dev.id)
                await dev.ws.close(code=4002, message=b"heartbeat")
                return
            await send_text(dev.ws, device_message("ping", t=int(time.time() * 1000)))

    async def _message(self, dev: Device, data: str) -> None:
        try:
            msg = json.loads(data)
        except json.JSONDecodeError:
            await send_text(dev.ws, device_message("error", code="bad_request", message="kein JSON"))
            return
        kind = msg.get("type")
        if kind == "ping":
            await send_text(dev.ws, device_message("pong", t=msg.get("t", 0)))
        elif kind == "art_request":
            self._art_request(dev, msg)
        elif kind == "event":
            await self._event(dev, msg)
        elif kind != "pong":
            log.debug("Gerät %s: unbekannter Typ %r", dev.id, kind)

    def _art_request(self, dev: Device, msg: dict[str, Any]) -> None:
        size = msg.get("size")
        dev.art_size = size if isinstance(size, int) and device.ART_MIN <= size <= device.ART_MAX else 0
        have = msg.get("have")
        dev.art_have = have[:device.IMAGE_ID_MAX] if isinstance(have, str) else ""
        if dev.art_size:
            asyncio.ensure_future(self.send_art(dev))

    async def _event(self, dev: Device, msg: dict[str, Any]) -> None:
        if msg.get("event") == "page_change":
            dev.page = msg.get("page")
            if dev.return_task:
                dev.return_task.cancel()
            self.queue_dps(dev)  # auf eine DPS-Seite gewechselt: aktuellen Stand nachreichen
            await self.changed()
            await self.follow_combat(dev, delay=SWIPED_STAY_S)
        err = await self.on_event(msg, dev.id)
        if err:
            await send_text(dev.ws, device_message("error", code="bad_request", message=err))
