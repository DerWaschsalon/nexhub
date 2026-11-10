"""Levelsystem: 15–25 XP je Nachricht (60 s Abklingzeit je Mitglied), Sprachzeit mit XP je Minute
(voice.py), Rangkarte, Rollen-Belohnungen, Kanäle und Rollen ohne XP. Aus, bis ein Server es im
Klick-Panel einschaltet, damit kein Server ungefragt ein neues Verhalten bekommt."""

from __future__ import annotations

import random
import time
from typing import ClassVar

import discord
from discord.ext import commands
from nexcore import ModuleInfo

from bot.core import BotContext, BotModule, GuildSettings
from bot.core.discord_checks import can_assign
from bot.core.module import Listener
from bot.core.web import RouteTable
from bot.hubpages import Page

from .settings import LevelSettings
from .store import LevelStore, level_from_xp
from .voice import TICK_S, qualifies

XP_MIN, XP_MAX = 15, 25
XP_COOLDOWN_S = 60


def earns_xp(message: discord.Message, settings: LevelSettings) -> bool:
    """Bringt diese Nachricht XP? (Levelsystem an, Kanal und Rollen nicht ausgenommen)"""
    if not settings.level_system_enabled or message.channel.id in settings.level_no_xp_channels:
        return False
    author = message.author
    roles = {r.id for r in author.roles} if isinstance(author, discord.Member) else set()
    return not roles & set(settings.level_no_xp_roles)


class Levels(BotModule):
    info: ClassVar[ModuleInfo] = ModuleInfo(
        id="community.levels", name="Levelsystem", category="Community", icon="mdi-trophy",
        summary="XP für Nachrichten und Sprachzeit, Rangkarte, Rangliste und Rollen-Belohnungen.",
    )
    Settings = LevelSettings

    def __init__(self, ctx: BotContext) -> None:
        super().__init__(ctx)
        self.settings = GuildSettings(ctx.db, LevelSettings)
        self.store = LevelStore(ctx.db)

    async def start(self) -> None:
        self.every(TICK_S, self.count_voice)

    def listeners(self) -> dict[str, Listener]:
        return {"on_message": self.on_message}

    async def count_voice(self) -> None:
        """Jede Minute: Sprachzeit (und XP je Minute) für alle, die gerade zählen."""
        for guild in self.client.guilds:
            xp_per_minute = self.settings.get(guild.id).voice_xp_per_minute
            for channel in guild.voice_channels:
                for member in channel.members:
                    if qualifies(member, channel):
                        await self.store.add_voice(guild.id, member.id, TICK_S, xp_per_minute)

    def cog(self) -> commands.Cog:
        from .commands import LevelsCog

        return LevelsCog(self)

    def pages(self) -> list[Page]:
        from .hub import level_page

        return [level_page()]

    def routes(self, r: RouteTable) -> None:
        from .hub import level_routes

        level_routes(self, r)

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None or not isinstance(message.author, discord.Member):
            return
        settings = self.settings.get(message.guild.id)
        if not earns_xp(message, settings):
            return
        guild_id, user_id = message.guild.id, message.author.id
        row = await self.store.entry(guild_id, user_id)
        now = time.time()
        if row and now - (row["last_xp"] or 0) < XP_COOLDOWN_S:
            await self.store.count_message(guild_id, user_id)
            return
        old_xp = int(row["xp"]) if row else 0
        new_xp = old_xp + random.randint(XP_MIN, XP_MAX)
        await self.store.award_message(guild_id, user_id, new_xp, now)
        new_level = level_from_xp(new_xp)[0]
        if new_level > level_from_xp(old_xp)[0]:
            await self.level_up(message, message.author, new_level, settings)

    async def level_up(self, message: discord.Message, member: discord.Member, level: int,
                       settings: LevelSettings) -> None:
        guild = member.guild
        channel = guild.get_channel(settings.level_announce_channel) if settings.level_announce_channel else None
        target = channel if isinstance(channel, discord.TextChannel) else message.channel
        try:
            await target.send(f"🎉 {member.mention} ist jetzt **Level {level}**!")
        except discord.HTTPException as e:
            self.log.warning("Level-Up-Nachricht %s: %r", guild.id, e)
        await self.give_rewards(member, level)

    async def give_rewards(self, member: discord.Member, level: int) -> None:
        for role_id in await self.store.rewards_up_to(member.guild.id, level):
            role = member.guild.get_role(role_id)
            if role is None or role in member.roles or not can_assign(member.guild, role):
                continue
            try:
                await member.add_roles(role, reason=f"Levelsystem: Level {level} erreicht")
            except discord.HTTPException as e:
                self.log.warning("Rollen-Belohnung %s für %s: %r", role.id, member.id, e)

    async def toggle_exception(self, guild_id: int, field: str, item_id: int, remove: bool) -> None:
        """Kanal oder Rolle in die Liste ohne XP aufnehmen oder daraus entfernen."""
        ids: list[int] = getattr(self.settings.get(guild_id), field)
        ids = [i for i in ids if i != item_id] if remove else list(dict.fromkeys([*ids, item_id]))
        await self.settings.update(guild_id, {field: ids})
