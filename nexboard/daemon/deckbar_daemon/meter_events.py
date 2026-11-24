"""Die Tauri-Events der Meter-Oberfläche (dps-update, ping-update, setting-changed …) als Server-Sent
Events. Je Browser-Profil hängt ein Strom daran (web/a2events.js), auch die Plugin-Seiten hören darüber mit."""
from __future__ import annotations

import asyncio
import json
from typing import Any

from aiohttp import web

from .capture import Capture

# Je Client; ein hängender Client verliert lieber alte dps-update. Plugin-Ereignisse dürfen hier nicht
# verloren gehen.
QUEUE_MAX = 256
KEEPALIVE_S = 15


class EventStream:
    def __init__(self, capture: Capture) -> None:
        self.capture = capture
        self.clients: set[asyncio.Queue] = set()
        capture.data_listeners.append(self.on_capture)

    async def on_capture(self, event: str, payload: Any) -> None:
        if event == "dps_data":
            await self.emit_raw("dps-update", payload)
        elif event == "ping" and payload is not None:
            await self.emit("ping-update", payload)

    async def emit(self, event: str, payload: Any) -> None:
        if self.clients:
            await self.emit_raw(event, json.dumps(payload, ensure_ascii=False))

    async def emit_raw(self, event: str, payload_json: str) -> None:
        """payload schon als JSON-Text: die volle DpsData (bis 100 KB) wird nicht geparst und neu geschrieben."""
        if not self.clients:
            return
        text = f'data: {{"event": {json.dumps(event)}, "payload": {payload_json}}}\n\n'
        for q in list(self.clients):
            if q.full():
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            q.put_nowait(text)

    def close(self) -> None:
        """Beim Beenden: offene Ströme sofort schließen (sonst wartet aiohttp darauf)."""
        for q in list(self.clients):
            while q.full():
                q.get_nowait()
            q.put_nowait(None)

    async def handle(self, request: web.Request) -> web.StreamResponse:
        resp = web.StreamResponse(headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"})
        await resp.prepare(request)
        q: asyncio.Queue = asyncio.Queue(QUEUE_MAX)
        self.clients.add(q)
        await self.capture.set_full(True)
        # Die Oberfläche braucht sofort einen Stand (dpsData ist sonst null bis zur nächsten Änderung)
        if self.capture.running:
            try:
                snap = await self.capture.request("snapshot", timeout=10)
                q.put_nowait(f"data: {json.dumps({'event': 'dps-update', 'payload': snap}, ensure_ascii=False)}\n\n")
            except (RuntimeError, TimeoutError):
                pass
        try:
            await resp.write(b": hallo\n\n")
            while True:
                try:
                    text = await asyncio.wait_for(q.get(), KEEPALIVE_S)
                except TimeoutError:
                    text = ": ping\n\n"
                if text is None:  # close(): Daemon fährt herunter
                    break
                await resp.write(text.encode())
        except ConnectionResetError:
            pass
        finally:
            self.clients.discard(q)
            if not self.clients:
                await self.capture.set_full(False)
        return resp
