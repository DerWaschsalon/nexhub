"""Host der Module: baut sie mit ihrem Kontext, hängt ihre Ereignisse an den Discord-Client,
sammelt ihre Web-Routen für den WebHost und schaltet sie über die nexcore-Registry.

Was nicht zu einem Modul gehört (Steuer-API-Grundgerüst, /setup), kommt aus `bot/admin` und wird
beim Start über `admin` hereingereicht; der Kern kennt keine Module beim Namen. Welche Module an
sind, steht in modules.yaml neben der Datenbank; neu ist jedes an.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, TypeVar

from discord.ext import commands
from nexcore import EventBus, Paths, Registry

from ..db import Database
from ..hubpages import Page
from .module import BotContext, BotModule, Listener
from .web import Route, RouteTable, WebHost, only_while_on

M = TypeVar("M", bound=BotModule)


def only_while_active(module: BotModule, handler: Listener) -> Listener:
    """Ausgeschaltete Module bekommen keine Discord-Ereignisse."""

    async def call(*args: Any) -> None:
        if module.active:
            await handler(*args)

    return call


def module_routes(module: BotModule, table: RouteTable) -> None:
    """Routen eines Moduls in die gemeinsame Tabelle, abgesichert für den Fall, dass es aus ist."""
    own = RouteTable()
    module.routes(own)

    def guarded(r: Route) -> Route:
        return Route(r.method, r.path, only_while_on(lambda: module.active, module.info.name, r.handler))

    table.public.extend(guarded(r) for r in own.public)
    table.internal.extend(guarded(r) for r in own.internal)
    table.public_max_body = max(table.public_max_body, own.public_max_body)


class ModuleHost:
    def __init__(self, client: commands.Bot, db: Database, types: Sequence[type[BotModule]], state_file: Path) -> None:
        self.client = client
        ctx = BotContext(bus=EventBus(), paths=Paths("thewashbot"), db=db, client=client)
        self.modules = [module_type(ctx) for module_type in types]
        all_ids = {m.info.id for m in self.modules}
        self.registry = Registry(ctx.bus, self.modules, state_file, initial=lambda: all_ids)
        self.web = WebHost()

    def module(self, mid: str, kind: type[M]) -> M:
        """Ein Modul mit seinem genauen Typ, für Teile außerhalb der Module (Steuer-API, /setup)."""
        found = next(m for m in self.modules if m.info.id == mid)
        if not isinstance(found, kind):
            raise TypeError(f"{mid} ist kein {kind.__name__}")
        return found

    def routes(self, admin: Callable[[RouteTable], None] | None = None) -> RouteTable:
        """Alle Web-Routen: die der Verwaltung (immer an) und die der Module."""
        table = RouteTable()
        if admin:
            admin(table)
        for m in self.modules:
            module_routes(m, table)
        return table

    async def start(self, admin: Callable[[RouteTable], None] | None = None) -> None:
        for m in self.modules:
            for event, handler in m.listeners().items():
                self.client.add_listener(only_while_active(m, handler), event)
            cog = m.cog()
            if cog is not None:
                await self.client.add_cog(cog)
        await self.registry.start()
        await self.web.start(self.routes(admin))

    def pages(self) -> list[Page]:
        """Hub-Seiten aller Module, für die Steuer-API (bot/admin/control.py)."""
        return [page for m in self.modules for page in m.pages()]

    async def stop(self) -> None:
        await self.web.stop()
        await self.registry.shutdown()
