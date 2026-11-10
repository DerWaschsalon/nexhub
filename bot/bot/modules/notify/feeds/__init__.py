"""Benachrichtigungen: neue Releases, Issues, Pull Requests, Commits (GitHub) oder Videos (YouTube) in
einen Kanal. Eingerichtet per Klick-Assistent (wizard.py) oder im NexHub; die Dienste stehen als
Provider in providers/ und melden sich in providers/manager.py an. Abgefragt wird alle POLL_MINUTES."""

from __future__ import annotations

import os
from typing import ClassVar

from nexcore import ModuleInfo

from bot.core import BotContext, BotModule
from bot.hubpages import Page

from .providers.manager import NotificationManager

POLL_MINUTES = max(1, int(os.getenv("NOTIFY_POLL_MINUTES", "10")))
MINUTE_S = 60


class NotificationFeeds(BotModule):
    info: ClassVar[ModuleInfo] = ModuleInfo(
        id="notify.feeds", name="Benachrichtigungen", category="Benachrichtigungen", icon="mdi-bell",
        summary="GitHub- und YouTube-Neuigkeiten automatisch in einen Kanal.",
    )

    def __init__(self, ctx: BotContext) -> None:
        super().__init__(ctx)
        self.manager = NotificationManager(ctx.db)

    async def start(self) -> None:
        self.every(POLL_MINUTES * MINUTE_S, self.poll_all)

    async def shutdown(self) -> None:
        await self.manager.close()
        await super().shutdown()

    def pages(self) -> list[Page]:
        from .hub import feeds_page

        return [feeds_page(self)]

    async def poll_all(self, guild_id: int | None = None) -> tuple[int, int]:
        """Aktive Feeds abfragen (alle oder die eines Servers); zurück: (geprüft, neu gepostet)."""
        if guild_id is None:
            feeds = await self.db.fetchall("SELECT * FROM feeds WHERE enabled=1")
        else:
            feeds = await self.db.fetchall("SELECT * FROM feeds WHERE guild_id=? AND enabled=1", (guild_id,))
        posted = 0
        for feed in feeds:
            posted += len(await self.manager.poll_feed(feed, self.client) or [])
        return len(feeds), posted
