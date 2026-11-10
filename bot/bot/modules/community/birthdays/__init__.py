"""Geburtstage: Mitglieder tragen ihren Geburtstag ein, der Bot gratuliert täglich um 9 Uhr deutscher
Zeit im eingestellten Kanal. `birthday_last_run` verhindert mehrere Grüße am selben Tag."""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar

import discord
from discord.ext import commands
from nexcore import ModuleInfo

from bot.core import BotContext, BotModule, GuildSettings
from bot.core.clock import TZ
from bot.db import Database
from bot.errors import UserError
from bot.hubpages import Page

from .settings import BirthdaySettings

CHECK_EVERY_S = 30 * 60
GREETING_HOUR = 9
LEAP_YEAR = 2024  # zum Prüfen eines Datums: in einem Schaltjahr gibt es den 29.2.


def check_date(day: int, month: int) -> None:
    try:
        datetime(LEAP_YEAR, month, day)
    except ValueError:
        raise UserError("Dieses Datum gibt es nicht.") from None


class BirthdayStore:
    """Geburtstage in der Datenbank; geteilt von Befehlen, Gratulation und Hub."""

    def __init__(self, db: Database) -> None:
        self.db = db

    async def put(self, guild_id: int, user_id: int, day: int, month: int) -> None:
        check_date(day, month)
        await self.db.execute(
            "INSERT INTO birthdays (guild_id, user_id, day, month) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET day=excluded.day, month=excluded.month",
            (guild_id, user_id, day, month))

    async def delete(self, guild_id: int, user_id: int) -> None:
        await self.db.execute("DELETE FROM birthdays WHERE guild_id=? AND user_id=?", (guild_id, user_id))

    async def of(self, guild_id: int, user_id: int) -> Any:
        return await self.db.fetchone("SELECT day, month FROM birthdays WHERE guild_id=? AND user_id=?",
                                      (guild_id, user_id))

    async def on_day(self, guild_id: int, day: int, month: int) -> list[int]:
        rows = await self.db.fetchall("SELECT user_id FROM birthdays WHERE guild_id=? AND day=? AND month=?",
                                      (guild_id, day, month))
        return [int(r["user_id"]) for r in rows]

    async def of_guild(self, guild_id: int) -> list[Any]:
        return await self.db.fetchall("SELECT * FROM birthdays WHERE guild_id=? ORDER BY month, day", (guild_id,))


class Birthdays(BotModule):
    info: ClassVar[ModuleInfo] = ModuleInfo(
        id="community.birthdays", name="Geburtstage", category="Community", icon="mdi-cake-variant",
        summary="Gratuliert um 9 Uhr allen, die heute Geburtstag haben.",
    )
    Settings = BirthdaySettings

    def __init__(self, ctx: BotContext) -> None:
        super().__init__(ctx)
        self.settings = GuildSettings(ctx.db, BirthdaySettings)
        self.store = BirthdayStore(ctx.db)

    async def start(self) -> None:
        self.every(CHECK_EVERY_S, self.greet_today)

    def cog(self) -> commands.Cog:
        from .commands import BirthdaysCog

        return BirthdaysCog(self)

    def pages(self) -> list[Page]:
        from .hub import birthday_page

        return [birthday_page(self.store)]

    async def greet_today(self) -> None:
        now = datetime.now(TZ)
        if now.hour != GREETING_HOUR:
            return
        today = now.strftime("%Y-%m-%d")
        for guild_id in self.settings.guilds_with("birthday_channel"):
            if self.settings.get(guild_id).birthday_last_run == today:
                continue
            await self.greet(guild_id, now)
            await self.settings.update(guild_id, {"birthday_last_run": today})

    async def greet(self, guild_id: int, now: datetime) -> None:
        guild = self.client.get_guild(guild_id)
        channel_id = self.settings.get(guild_id).birthday_channel
        channel = guild.get_channel(channel_id) if guild and channel_id else None
        if guild is None or not isinstance(channel, discord.TextChannel):
            return
        for user_id in await self.store.on_day(guild_id, now.day, now.month):
            member = guild.get_member(user_id)
            if member is None:
                continue
            try:
                await channel.send(f"🎉 Alles Gute zum Geburtstag, {member.mention}! 🎂")
            except discord.HTTPException as e:
                self.log.warning("Geburtstagsgruß %s: %r", guild_id, e)
