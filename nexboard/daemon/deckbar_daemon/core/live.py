"""Live-Verbindung der Web-UI (/api/live): Begrüßung mit dem Gesamtstand, danach jede Änderung.

Jedes Modul meldet seinen Teil der Begrüßung selbst an (section) und schickt Änderungen mit send().
Die Vorschau der Leiste in der Web-UI verhält sich wie ein Gerät: ihre Ereignisse gehen an den
angemeldeten Empfänger.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiohttp import WSMsgType, web
from nexcore import EventBus

log = logging.getLogger(__name__)

OPENED = "ui.opened"  # Thema auf dem Bus: erste Web-UI geöffnet
EventHandler = Callable[[dict[str, Any], str], Awaitable[str | None]]


async def send_text(ws: web.WebSocketResponse, text: str) -> None:
    if ws.closed:
        return
    try:
        await ws.send_str(text)
    except (ConnectionError, RuntimeError) as e:  # ConnectionError umfasst Reset + Broken Pipe
        log.debug("Senden fehlgeschlagen: %s", e)


class LiveHub:
    def __init__(self, bus: EventBus) -> None:
        self.bus = bus
        self.clients: set[web.WebSocketResponse] = set()
        self._sections: dict[str, Callable[[], Any]] = {}
        self._on_event: EventHandler | None = None

    @property
    def watching(self) -> bool:
        return bool(self.clients)

    def section(self, key: str, provider: Callable[[], Any]) -> None:
        """Teil der Begrüßung: key → aktueller Stand."""
        self._sections[key] = provider

    def handle_events(self, handler: EventHandler) -> None:
        self._on_event = handler

    async def send(self, obj: dict[str, Any]) -> None:
        if not self.clients:
            return
        text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
        await asyncio.gather(*(send_text(ws, text) for ws in list(self.clients)))

    async def handler(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(heartbeat=20)
        await ws.prepare(request)
        if not self.clients:
            await self.bus.emit(OPENED)
        self.clients.add(ws)
        hello = {"type": "hello", **{key: provider() for key, provider in self._sections.items()}}
        await send_text(ws, json.dumps(hello, ensure_ascii=False))
        try:
            async for m in ws:
                if m.type == WSMsgType.TEXT:
                    await self._message(ws, m.data)
        finally:
            self.clients.discard(ws)
        return ws

    async def _message(self, ws: web.WebSocketResponse, data: str) -> None:
        try:
            msg = json.loads(data)
        except json.JSONDecodeError:
            return
        if msg.get("type") != "event" or not self._on_event:
            return
        err = await self._on_event(msg, "web-ui")
        if err:
            await send_text(ws, json.dumps({"type": "error", "error": err}))
