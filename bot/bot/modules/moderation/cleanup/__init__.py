"""Aufräumen: alte Nachrichten löschen, alte Bots entfernen, Bericht über den Server. Alles, was etwas
löscht, zeigt erst eine Vorschau mit Rückfrage (bot.core.confirm).

Discord löscht Nachrichten jünger als 14 Tage in Blöcken zu 100; ältere einzeln, etwa eine je Sekunde.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import ClassVar

import discord
from discord.ext import commands
from nexcore import ModuleInfo

from bot.core import BotModule
from bot.core.moderation import QUIET_DELETE

SCAN_LIMIT = 5000
BULK_AGE = timedelta(days=14)  # ältere Nachrichten löscht Discord nur einzeln


@dataclass(frozen=True)
class MessageFilter:
    keep_pinned: bool
    author_id: int | None
    only_bots: bool

    def matches(self, message: discord.Message) -> bool:
        if self.keep_pinned and message.pinned:
            return False
        if self.author_id and message.author.id != self.author_id:
            return False
        return not self.only_bots or message.author.bot


def slow_count(messages: list[discord.Message], now: datetime) -> int:
    """Wie viele davon einzeln gelöscht werden müssen (älter als 14 Tage)."""
    return sum(1 for m in messages if now - m.created_at > BULK_AGE)


class Cleanup(BotModule):
    info: ClassVar[ModuleInfo] = ModuleInfo(
        id="moderation.cleanup", name="Aufräumen", category="Moderation", icon="mdi-broom",
        summary="Alte Nachrichten löschen, alte Bots entfernen, Bericht über Kanäle und Rollen.",
    )

    def cog(self) -> commands.Cog:
        from .commands import CleanupCog

        return CleanupCog(self)

    @staticmethod
    async def find(channel: discord.TextChannel, before: datetime | None, limit: int,
                   wanted: Callable[[discord.Message], bool]) -> list[discord.Message]:
        """Vorschau: die neuesten passenden Nachrichten, höchstens `limit`."""
        found: list[discord.Message] = []
        async for message in channel.history(limit=SCAN_LIMIT, before=before):
            if wanted(message):
                found.append(message)
                if len(found) >= limit:
                    break
        return found

    async def delete(self, channel: discord.TextChannel, messages: list[discord.Message], before: datetime | None,
                     reason: str) -> int:
        """Genau diese Nachrichten löschen, ohne Einzel-Logs; zurück kommt die Anzahl."""
        targets = {m.id for m in messages}
        await self.ctx.bus.emit(QUIET_DELETE, list(targets))
        oldest = min(m.created_at for m in messages) - timedelta(seconds=1)
        deleted = await channel.purge(limit=None, before=before, after=oldest, check=lambda m: m.id in targets,
                                      reason=reason)
        return len(deleted)
