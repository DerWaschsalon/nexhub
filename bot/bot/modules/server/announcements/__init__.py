"""Zeitgesteuerte Ankündigungen: ein Text geht alle X Minuten in einen Kanal (Tabelle `scheduled`,
`next_run` als Unix-Zeit). Angelegt per /ankuendigung-erstellen oder im NexHub."""

from __future__ import annotations

import time
from typing import Any, ClassVar

import discord
from discord.ext import commands
from nexcore import ModuleInfo

from bot.core import BotContext, BotModule
from bot.db import Database
from bot.errors import UserError

CHECK_EVERY_S = 60
MINUTE_S = 60


class AnnouncementStore:
    """Ankündigungen in der Datenbank; geteilt von Befehlen, Takt und Hub."""

    def __init__(self, db: Database) -> None:
        self.db = db

    async def add(self, guild_id: int, channel_id: int, text: str, interval_minutes: int) -> int:
        return await self.db.execute(
            "INSERT INTO scheduled (guild_id, channel_id, text, interval_minutes, next_run) VALUES (?, ?, ?, ?, ?)",
            (guild_id, channel_id, text, interval_minutes, time.time()))

    async def of_guild(self, guild_id: int) -> list[Any]:
        return await self.db.fetchall(
            "SELECT id, channel_id, interval_minutes, next_run, text FROM scheduled WHERE guild_id=? ORDER BY id",
            (guild_id,))

    async def delete(self, guild_id: int, announcement_id: int) -> None:
        row = await self.db.fetchone("SELECT id FROM scheduled WHERE id=? AND guild_id=?", (announcement_id, guild_id))
        if row is None:
            raise UserError(f"Keine Ankündigung mit der ID {announcement_id} auf diesem Server gefunden.")
        await self.db.execute("DELETE FROM scheduled WHERE id=?", (announcement_id,))

    async def due(self, now: float) -> list[Any]:
        return await self.db.fetchall("SELECT * FROM scheduled WHERE next_run <= ?", (now,))

    async def reschedule(self, row: Any, now: float) -> None:
        await self.db.execute("UPDATE scheduled SET next_run=? WHERE id=?",
                              (now + row["interval_minutes"] * MINUTE_S, row["id"]))


class Announcements(BotModule):
    info: ClassVar[ModuleInfo] = ModuleInfo(
        id="server.announcements", name="Ankündigungen", category="Server", icon="mdi-bullhorn",
        summary="Ein Text geht alle X Minuten automatisch in einen Kanal.",
    )

    def __init__(self, ctx: BotContext) -> None:
        super().__init__(ctx)
        self.store = AnnouncementStore(ctx.db)

    async def start(self) -> None:
        self.every(CHECK_EVERY_S, self.post_due)

    def cog(self) -> commands.Cog:
        from .commands import AnnouncementsCog

        return AnnouncementsCog(self)

    async def post_due(self) -> None:
        now = time.time()
        for row in await self.store.due(now):
            await self.post(row)
            await self.store.reschedule(row, now)

    async def post(self, row: Any) -> None:
        channel = self.client.get_channel(row["channel_id"])
        if not isinstance(channel, discord.abc.Messageable):
            return
        try:
            await channel.send(row["text"])
        except discord.HTTPException as e:
            self.log.warning("Ankündigung #%s: %r", row["id"], e)
