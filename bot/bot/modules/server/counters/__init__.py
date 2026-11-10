"""Zähler-Kanäle: Namen von Sprachkanälen zeigen laufend Mitglieder- und Bot-Anzahl.

Discord erlaubt Namensänderungen an einem Kanal nur begrenzt oft (grob zweimal je 10 Minuten), deshalb
je Kanal höchstens alle 10 Minuten von selbst, dazu einmal sofort nach dem Einrichten.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import ClassVar

import discord
from nexcore import ModuleInfo

from bot.core import BotContext, BotModule, GuildSettings
from bot.core.module import Listener

from .settings import CounterSettings

UPDATE_INTERVAL_S = 10 * 60
SECTION = "community"  # Bereich in bot/forms.py, in dem die Zähler eingestellt werden


def member_channel_name(guild: discord.Guild) -> str:
    return f"👥 Mitglieder: {guild.member_count}"


def bots_channel_name(guild: discord.Guild) -> str:
    return f"🤖 Bots: {sum(1 for m in guild.members if m.bot)}"


@dataclass(frozen=True)
class Counter:
    channel_key: str  # Feld mit dem Kanal
    last_key: str  # Feld mit dem Zeitpunkt der letzten Namensänderung
    name: Callable[[discord.Guild], str]


COUNTERS = (
    Counter("member_count_channel", "member_count_last", member_channel_name),
    Counter("bots_count_channel", "bots_count_last", bots_channel_name),
)


class Counters(BotModule):
    info: ClassVar[ModuleInfo] = ModuleInfo(
        id="server.counters", name="Zähler-Kanäle", category="Server", icon="mdi-counter",
        summary="Sprachkanäle, deren Name die Mitglieder- oder Bot-Anzahl zeigt.",
    )
    Settings = CounterSettings

    def __init__(self, ctx: BotContext) -> None:
        super().__init__(ctx)
        self.settings = GuildSettings(ctx.db, CounterSettings)

    async def start(self) -> None:
        self.every(UPDATE_INTERVAL_S, self.refresh_all)

    def listeners(self) -> dict[str, Listener]:
        return {"on_member_join": self.on_member_change, "on_member_remove": self.on_member_change,
                "on_settings_changed": self.on_settings_changed}

    async def on_member_change(self, member: discord.Member) -> None:
        await self.update(member.guild, throttled=True)

    async def on_settings_changed(self, guild: discord.Guild, section_id: str) -> None:
        """Neu eingerichtete Zähler (Hub, Panel, /setup ändern) gleich anzeigen, nicht erst im Takt."""
        if section_id == SECTION:
            await self.update(guild, throttled=False)

    async def refresh_all(self) -> None:
        guild_ids = {gid for counter in COUNTERS for gid in self.settings.guilds_with(counter.channel_key)}
        for guild_id in guild_ids:
            guild = self.client.get_guild(guild_id)
            if guild:
                await self.update(guild, throttled=False)

    async def update(self, guild: discord.Guild, *, throttled: bool) -> None:
        settings = self.settings.get(guild.id).model_dump()
        for counter in COUNTERS:
            last = settings[counter.last_key]
            if throttled and last and time.time() - last < UPDATE_INTERVAL_S:
                continue
            await self.rename(guild, counter, settings[counter.channel_key])

    async def rename(self, guild: discord.Guild, counter: Counter, channel_id: int | None) -> None:
        channel = guild.get_channel(channel_id) if channel_id else None
        name = counter.name(guild)
        if channel is None or channel.name == name:
            return
        try:
            await channel.edit(name=name, reason="Statistik-Kanal")
        except discord.HTTPException as e:
            self.log.warning("Statistik-Kanal %s (%s): %r", guild.id, counter.channel_key, e)
            return
        await self.settings.update(guild.id, {counter.last_key: time.time()})
