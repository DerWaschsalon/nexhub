"""Host der Module: baut sie mit ihrem Kontext, hängt ihre Ereignisse an den Discord-Client und
schaltet sie über die nexcore-Registry.

Bis alle Cogs umgezogen sind, laufen alte Cogs und neue Module nebeneinander (__main__.COGS und
MODULES). Welche Module an sind, steht in modules.yaml neben der Datenbank; neu ist jedes an.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from discord.ext import commands
from nexcore import EventBus, Paths, Registry

from ..db import Database
from ..hubpages import Page
from .module import BotContext, BotModule, Listener


def only_while_active(module: BotModule, handler: Listener) -> Listener:
    """Ausgeschaltete Module bekommen keine Discord-Ereignisse."""

    async def call(*args: Any) -> None:
        if module.active:
            await handler(*args)

    return call


class ModuleHost:
    def __init__(self, client: commands.Bot, db: Database, types: Sequence[type[BotModule]], state_file: Path) -> None:
        self.client = client
        ctx = BotContext(bus=EventBus(), paths=Paths("thewashbot"), db=db, client=client)
        self.modules = [module_type(ctx) for module_type in types]
        all_ids = {m.info.id for m in self.modules}
        self.registry = Registry(ctx.bus, self.modules, state_file, initial=lambda: all_ids)

    def module(self, mid: str) -> BotModule:
        return next(m for m in self.modules if m.info.id == mid)

    async def start(self) -> None:
        for m in self.modules:
            for event, handler in m.listeners().items():
                self.client.add_listener(only_while_active(m, handler), event)
            cog = m.cog()
            if cog is not None:
                await self.client.add_cog(cog)
        await self.registry.start()

    def pages(self) -> list[Page]:
        """Hub-Seiten aller Module, für die Steuer-API (cogs/control.py)."""
        return [page for m in self.modules for page in m.pages()]

    async def stop(self) -> None:
        await self.registry.shutdown()
