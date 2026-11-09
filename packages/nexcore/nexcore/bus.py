"""Ereignisbus: Module reden über Themen miteinander statt über Listen von Rückrufen.

Themen sind Punkt-Namen wie "game.started", "combat.ended" oder "modules.changed". Ein Fehler in
einem Empfänger wird geloggt und trifft weder den Sender noch die anderen Empfänger.
"""
from __future__ import annotations

import asyncio
import inspect
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

log = logging.getLogger("nexcore.bus")

Handler = Callable[[Any], Awaitable[None] | None]


class EventBus:
    def __init__(self) -> None:
        self._handlers: defaultdict[str, list[Handler]] = defaultdict(list)
        self._pending: set[asyncio.Task[None]] = set()  # Referenzen, sonst räumt asyncio laufende Tasks weg

    def on(self, topic: str, handler: Handler) -> Callable[[], None]:
        """Empfänger anmelden; zurück kommt die Abmeldung (mehrfach aufrufen schadet nicht)."""
        handlers = self._handlers[topic]
        handlers.append(handler)

        def off() -> None:
            if handler in handlers:
                handlers.remove(handler)
        return off

    async def emit(self, topic: str, payload: Any = None) -> None:
        """An alle Empfänger des Themas, der Reihe nach; wartet, bis alle fertig sind."""
        for handler in list(self._handlers.get(topic, ())):
            try:
                result = handler(payload)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                log.exception("Empfänger von %s fehlgeschlagen", topic)

    def publish(self, topic: str, payload: Any = None) -> None:
        """Wie emit, aber ohne zu warten: für Code, der selbst nicht async ist."""
        task = asyncio.get_running_loop().create_task(self.emit(topic, payload))
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)
