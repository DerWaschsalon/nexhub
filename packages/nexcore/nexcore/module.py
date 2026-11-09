"""Modulvertrag: jedes einzeln schaltbare Teil ist eine Unterklasse von Module.

Ein Modul beschreibt sich selbst (info, Settings), bekommt im Konstruktor nur den Kontext und
startet seine Aufgaben über spawn() und Abos über on(). Ausschalten räumt beides von selbst ab,
Unterklassen müssen dafür nichts tun.
"""
from __future__ import annotations

import asyncio
import logging
from abc import ABC
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, ClassVar

from pydantic import BaseModel

from .bus import EventBus, Handler
from .paths import Paths

log = logging.getLogger("nexcore.module")

RESTART_AFTER_S = 10  # abgestürzte Aufgabe: so lange warten, dann neu starten


@dataclass(frozen=True)
class ModuleInfo:
    id: str
    name: str
    category: str
    icon: str  # Material-Design-Icon
    summary: str
    requires: tuple[str, ...] = ()
    default: bool = False  # bei einer frischen Installation an
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class Context:
    """Was jedes Modul vom Host bekommt; mehr nicht (keine anderen Module, kein ganzer Daemon)."""
    bus: EventBus
    paths: Paths


class Module(ABC):
    info: ClassVar[ModuleInfo]
    Settings: ClassVar[type[BaseModel] | None] = None  # Schema der Einstellungen, None = keine

    def __init__(self, ctx: Context) -> None:
        self.ctx = ctx
        self.log = logging.getLogger(f"nexboard.{self.info.id}")
        self.active = False  # eingeschaltet und gestartet
        self._tasks: list[asyncio.Task[None]] = []
        self._subscriptions: list[Callable[[], None]] = []

    # ------------------------------------------------------------ für Unterklassen
    async def start(self) -> None:
        """Beim Einschalten: Aufgaben mit spawn(), Abos mit on()."""

    async def stop(self) -> None:
        """Beim Ausschalten durch den Nutzer, nach dem Abräumen der Aufgaben (z. B. ein Fenster schließen)."""

    def status(self) -> dict[str, Any]:
        """Kurzstand fürs Dashboard."""
        return {}

    def spawn(self, job: Callable[[], Awaitable[None]]) -> None:
        """Aufgabe, solange das Modul an ist; stürzt sie ab, startet sie nach kurzer Pause neu."""
        self._tasks.append(asyncio.ensure_future(self._guard(job)))

    def on(self, topic: str, handler: Handler) -> None:
        self._subscriptions.append(self.ctx.bus.on(topic, handler))

    # ------------------------------------------------------------ für die Registry
    async def activate(self) -> None:
        self.active = True
        await self.start()

    async def deactivate(self) -> None:
        await self.shutdown()
        await self.stop()

    async def shutdown(self) -> None:
        """Nur abräumen: beim Beenden des Hosts bleibt, was nach außen läuft (z. B. das Overlay)."""
        self.active = False
        for off in self._subscriptions:
            off()
        tasks, self._tasks, self._subscriptions = self._tasks, [], []
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _guard(self, job: Callable[[], Awaitable[None]]) -> None:
        while True:
            try:
                await job()
                return
            except asyncio.CancelledError:
                raise
            except Exception:
                self.log.exception("Aufgabe abgestürzt, starte in %d s neu", RESTART_AFTER_S)
                await asyncio.sleep(RESTART_AFTER_S)
