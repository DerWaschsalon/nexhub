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
from nexcore import Context, Module

from ..db import Database

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

    def every(self, seconds: float, job: Callable[[], Awaitable[Any]]) -> None:
        """job sofort nach dem Login und dann alle `seconds` Sekunden, solange das Modul an ist."""

        async def loop() -> None:
            await self.client.wait_until_ready()
            while True:
                await job()
                await asyncio.sleep(seconds)

        self.spawn(loop)
