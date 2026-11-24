"""Signal: ein Ereignis eines Trackers, das Abnehmer der Reihe nach im Thread des Senders bekommen.

Die Pakete kommen aus dem Mitschnitt-Thread; der Ereignisbus von nexcore ist für die asyncio-Schleife.
Ein Fehler in einem Abnehmer wird geloggt und trifft weder den Sender noch die anderen Abnehmer.
"""
from __future__ import annotations

import logging
from collections.abc import Callable

log = logging.getLogger(__name__)


class Signal[*Args]:
    def __init__(self) -> None:
        self._handlers: list[Callable[[*Args], None]] = []

    def connect(self, handler: Callable[[*Args], None], first: bool = False) -> None:
        """`first`: vor allen bisherigen Abnehmern (Mitschreiber des Goldtests)."""
        self._handlers.insert(0 if first else len(self._handlers), handler)

    def emit(self, *args: *Args) -> None:
        for handler in list(self._handlers):
            try:
                handler(*args)
            except Exception:
                log.exception("Abnehmer %r fehlgeschlagen", handler)
