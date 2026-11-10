"""Erinnerungen: /erinnere, /erinnerungen, /erinnerung-loeschen. Fällige Erinnerungen gehen alle
30 Sekunden raus, im Kanal mit Erwähnung oder als Direktnachricht."""

from __future__ import annotations

import time
from typing import Any, ClassVar

import discord
from discord.ext import commands
from nexcore import ModuleInfo

from bot.core import BotContext, BotModule
from bot.db import Database
from bot.errors import UserError
from bot.hubpages import Page

CHECK_EVERY_S = 30
HUB_LIMIT = 200


class ReminderStore:
    """Erinnerungen in der Datenbank; geteilt von Befehlen, Takt und Hub."""

    def __init__(self, db: Database) -> None:
        self.db = db

    async def add(self, guild_id: int, channel_id: int, user_id: int, text: str, due: float, private: bool) -> None:
        await self.db.execute(
            "INSERT INTO reminders (guild_id, channel_id, user_id, text, due, private) VALUES (?, ?, ?, ?, ?, ?)",
            (guild_id, channel_id, user_id, text, due, int(private)))

    async def of_user(self, guild_id: int, user_id: int) -> list[Any]:
        return await self.db.fetchall("SELECT id, text, due FROM reminders WHERE guild_id=? AND user_id=? ORDER BY due",
                                      (guild_id, user_id))

    async def of_guild(self, guild_id: int) -> list[Any]:
        return await self.db.fetchall("SELECT * FROM reminders WHERE guild_id=? ORDER BY due LIMIT ?",
                                      (guild_id, HUB_LIMIT))

    async def delete_own(self, guild_id: int, user_id: int, reminder_id: int) -> None:
        row = await self.db.fetchone("SELECT id FROM reminders WHERE id=? AND guild_id=? AND user_id=?",
                                     (reminder_id, guild_id, user_id))
        if row is None:
            raise UserError(f"Keine eigene Erinnerung mit der ID {reminder_id} gefunden.")
        await self.delete(guild_id, reminder_id)

    async def delete(self, guild_id: int, reminder_id: int) -> None:
        await self.db.execute("DELETE FROM reminders WHERE id=? AND guild_id=?", (reminder_id, guild_id))

    async def due(self, now: float) -> list[Any]:
        return await self.db.fetchall("SELECT * FROM reminders WHERE due <= ?", (now,))


class Reminders(BotModule):
    info: ClassVar[ModuleInfo] = ModuleInfo(
        id="community.reminders", name="Erinnerungen", category="Community", icon="mdi-alarm",
        summary="Erinnerungen im Kanal oder per Direktnachricht.",
    )

    def __init__(self, ctx: BotContext) -> None:
        super().__init__(ctx)
        self.store = ReminderStore(ctx.db)

    async def start(self) -> None:
        self.every(CHECK_EVERY_S, self.send_due)

    def cog(self) -> commands.Cog:
        from .commands import RemindersCog

        return RemindersCog(self)

    def pages(self) -> list[Page]:
        from .hub import reminder_page

        return [reminder_page(self.store)]

    async def send_due(self) -> None:
        for row in await self.store.due(time.time()):
            await self.send(row)
            await self.store.delete(row["guild_id"], row["id"])

    async def send(self, row: Any) -> None:
        try:
            user = self.client.get_user(row["user_id"]) or await self.client.fetch_user(row["user_id"])
        except discord.HTTPException:
            return
        text = f"⏰ Erinnerung: {row['text']}"
        channel = user if row["private"] else self.client.get_channel(row["channel_id"])
        if not isinstance(channel, discord.abc.Messageable):
            return
        if not row["private"]:
            text = f"{user.mention} {text}"
        try:
            await channel.send(text, allowed_mentions=discord.AllowedMentions(users=True))
        except discord.HTTPException as e:
            self.log.debug("Erinnerung #%s: %r", row["id"], e)
