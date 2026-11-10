"""Bump-Erinnerung: erkennt die Bump-Bestätigung von DISBOARD im eingerichteten Kanal und erinnert
nach Ablauf des 2-Stunden-Cooldowns per Ping im selben Kanal. Rein passiv: Der Bot bumpt nicht selbst
(das wäre automatisiertes Verhalten und ein möglicher Verstoß gegen Disboards Regeln), er erinnert nur.
"""

from __future__ import annotations

import time
from typing import ClassVar

import discord
from nexcore import ModuleInfo

from bot.core import BotContext, BotModule, GuildSettings
from bot.core.module import Listener

from .settings import BumpSettings

DISBOARD_BOT_ID = 302050872383242240
BUMP_INTERVAL_S = 2 * 60 * 60
CHECK_EVERY_S = 60
REMINDER = "⏰ Bump ist wieder möglich – wer mag, tippt `/bump`!"


def is_bump_confirmation(message: discord.Message) -> bool:
    """Erfolgreiche Bump-Bestätigung von DISBOARD, nicht dessen Cooldown-Meldung bei zu frühem /bump."""
    if message.author.id != DISBOARD_BOT_ID or not message.embeds:
        return False
    embed = message.embeds[0]
    text = " ".join(filter(None, [embed.title, embed.description])).lower()
    return "bump done" in text or "bump erfolgreich" in text


def is_due(settings: BumpSettings, now: float) -> bool:
    if settings.bump_last is None or settings.bump_reminded:
        return False
    return now - settings.bump_last >= BUMP_INTERVAL_S


class Bump(BotModule):
    info: ClassVar[ModuleInfo] = ModuleInfo(
        id="community.bump", name="Bump-Erinnerung", category="Community", icon="mdi-bell-ring",
        summary="Erinnert nach DISBOARDs Cooldown daran, dass /bump wieder geht.",
    )
    Settings = BumpSettings

    def __init__(self, ctx: BotContext) -> None:
        super().__init__(ctx)
        self.settings = GuildSettings(ctx.db, BumpSettings)

    async def start(self) -> None:
        self.every(CHECK_EVERY_S, self.remind_due)

    def listeners(self) -> dict[str, Listener]:
        return {"on_message": self.on_message}

    async def on_message(self, message: discord.Message) -> None:
        if not message.guild or not is_bump_confirmation(message):
            return
        if self.settings.get(message.guild.id).bump_channel != message.channel.id:
            return
        await self.settings.update(message.guild.id, {"bump_last": time.time(), "bump_reminded": False})

    async def remind_due(self) -> None:
        now = time.time()
        for guild_id in self.settings.guilds_with("bump_channel"):
            if is_due(self.settings.get(guild_id), now):
                await self.remind(guild_id)
                await self.settings.update(guild_id, {"bump_reminded": True})

    async def remind(self, guild_id: int) -> None:
        settings = self.settings.get(guild_id)
        channel = self.client.get_channel(settings.bump_channel) if settings.bump_channel else None
        if not isinstance(channel, discord.TextChannel):
            return
        role = channel.guild.get_role(settings.bump_role) if settings.bump_role else None
        text = f"{role.mention} {REMINDER}" if role else REMINDER
        try:
            await channel.send(text, allowed_mentions=discord.AllowedMentions(roles=bool(role)))
        except discord.HTTPException as e:
            self.log.warning("Bump-Erinnerung %s: %r", guild_id, e)
