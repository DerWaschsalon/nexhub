"""Modulvertrag des Bots: ein nexcore.Module mit Zugang zu Discord und der Datenbank.

Ein Modul meldet seine Discord-Ereignisse über listeners() an; der Host ruft sie nur, solange das
Modul an ist. Wiederkehrende Aufgaben laufen über every() (ersetzt discord.ext.tasks: wartet auf den
Login, startet nach einem Absturz neu, endet beim Ausschalten).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands
from nexcore import Context, Module

from ..db import Database
from ..hubpages import Page
from .web import RouteTable

Listener = Callable[..., Coroutine[Any, Any, None]]


@dataclass(frozen=True)
class BotContext(Context):
    db: Database
    client: discord.Client


class BotModule(Module):
    def __init__(self, ctx: BotContext) -> None:
        super().__init__(ctx)
        self.db = ctx.db
        self.client = ctx.client
        self.log = logging.getLogger(f"thewashbot.{self.info.id}")

    def listeners(self) -> dict[str, Listener]:
        """Discord-Ereignis (z. B. "on_message") → Methode."""
        return {}

    def cog(self) -> commands.Cog | None:
        """Slash-Befehle des Moduls als ModuleCog, oder None ohne Befehle."""
        return None

    def pages(self) -> list[Page]:
        """Seiten des Moduls im NexHub (Tabellen, Status, Aktionen; siehe bot/hubpages.py)."""
        return []

    def routes(self, r: RouteTable) -> None:
        """Web-Routen des Moduls: `r.control(...)` für die Steuer-API des Hubs, `r.open(...)` für
        öffentliche Endpunkte. Ist das Modul aus, antworten sie mit 503 (siehe ModuleHost)."""

    def every(self, seconds: float, job: Callable[[], Awaitable[Any]]) -> None:
        """job sofort nach dem Login und dann alle `seconds` Sekunden, solange das Modul an ist."""

        async def loop() -> None:
            await self.client.wait_until_ready()
            while True:
                await job()
                await asyncio.sleep(seconds)

        self.spawn(loop)


class ModuleCog(commands.Cog):
    """Discord-Befehle eines Moduls, nur die Oberfläche: Die Befehle rufen das Modul auf, das die
    Logik und den Zustand hält. Ist das Modul aus, antworten seine Befehle mit einem Hinweis."""

    def __init__(self, module: BotModule) -> None:
        self.module = module

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not self.module.active:
            raise app_commands.CheckFailure(f"„{self.module.info.name}“ ist gerade ausgeschaltet.")
        return True
