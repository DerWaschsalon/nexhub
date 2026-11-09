"""Server-Sent Events an beliebig viele Zuhörer (Web-UI, Overlay-Seite), ohne Web-Framework.

Der Host schreibt die Stücke aus stream() in seine HTTP-Antwort. Ein langsamer Zuhörer verliert
seine ältesten Meldungen statt den Daemon zu bremsen.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Iterable
from typing import Any

QUEUE_MAX = 256
PING_S = 15.0  # Kommentarzeile, damit Proxys und Browser die Verbindung offen halten


def frame(event: str | None, data: Any) -> str:
    head = f"event: {event}\n" if event else ""
    return f"{head}data: {json.dumps(data, ensure_ascii=False)}\n\n"


class SseHub:
    def __init__(self, queue_max: int = QUEUE_MAX, ping_s: float = PING_S) -> None:
        self.queue_max = queue_max
        self.ping_s = ping_s
        self._clients: set[asyncio.Queue[str | None]] = set()

    @property
    def listeners(self) -> int:
        return len(self._clients)

    def publish(self, event: str | None, data: Any) -> None:
        text = frame(event, data)
        for queue in self._clients:
            self._put(queue, text)

    def close_all(self) -> None:
        """Beim Beenden: alle Streams sofort schließen (sonst wartet der Webserver auf sie)."""
        for queue in self._clients:
            self._put(queue, None)

    async def stream(self, first: Iterable[str] = ()) -> AsyncIterator[bytes]:
        """Alles für einen Zuhörer: Gruß, Anfangsstand (fertige Frames), dann jede Meldung."""
        queue: asyncio.Queue[str | None] = asyncio.Queue(self.queue_max)
        self._clients.add(queue)
        try:
            yield b": hallo\n\n"
            for opening in first:
                yield opening.encode()
            while True:
                text: str | None
                try:
                    text = await asyncio.wait_for(queue.get(), self.ping_s)
                except TimeoutError:
                    text = ": ping\n\n"
                if text is None:
                    return
                yield text.encode()
        finally:
            self._clients.discard(queue)

    @staticmethod
    def _put(queue: asyncio.Queue[str | None], text: str | None) -> None:
        while queue.full():
            queue.get_nowait()
        queue.put_nowait(text)
