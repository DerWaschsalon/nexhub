"""Termin-Tafel für AION 2: eine Nachricht im eingestellten Kanal, die sich jede Minute selbst
aktualisiert (Riss, Shugo-Fest, Beritra-Luftangriff, Wächterin Kaira, Resets).

Die Zeiten stehen als Discord-Zeitstempel in der Nachricht, jeder sieht sie also in seiner Zeitzone.
5 Minuten vor einem Ereignis (nicht vor den Resets) kommt ein Ping an die eingestellte Rolle, der sich
nach Beginn selbst löscht. Die Termine stehen genau einmal im Monorepo: nexproto.termine.
"""

from __future__ import annotations

import time
from typing import ClassVar

import discord
from nexcore import ModuleInfo
from nexproto import termine

from bot.core import BotContext, BotModule, GuildSettings

from .settings import ScheduleSettings

UPDATE_EVERY_S = 60
PING_AHEAD_S = 5 * 60
FORGET_AFTER_S = 3600  # gemeldete Pings so lange merken, dann vergessen
MIN_PING_LIFETIME_S = 60
NO_PING = ("Tages-Reset", "Wochen-Reset")
COLOUR = 0x7DD8D8

Event = tuple[str, int]  # (Name, Beginn als Unix-Zeit)


def board(now: float) -> discord.Embed:
    """Die Tafel: je Termin der nächste Beginn, oder „läuft bis …“, solange er offen ist."""
    lines = []
    for name, start, open_until in termine.alle(now):
        if open_until:
            lines.append(f"🟢 **{name}** läuft, bis <t:{int(open_until)}:t> (<t:{int(open_until)}:R>)")
        else:
            lines.append(f"**{name}** <t:{int(start)}:t> (<t:{int(start)}:R>)")
    embed = discord.Embed(title="AION 2 · Termine", description="\n".join(lines), color=COLOUR)
    embed.set_footer(text="Zeiten in deiner Zeitzone · aktualisiert sich jede Minute · Riss bestätigt, Rest geschätzt")
    return embed


def due_pings(now: float, announced: set[Event]) -> list[Event]:
    """Ereignisse, die in den nächsten 5 Minuten beginnen und noch nicht gemeldet sind."""
    due = []
    for name, start, open_until in termine.alle(now):
        key = (name, int(start))
        if name in NO_PING or open_until or key in announced:
            continue
        if 0 < start - now <= PING_AHEAD_S:
            due.append(key)
    return due


class Schedule(BotModule):
    info: ClassVar[ModuleInfo] = ModuleInfo(
        id="aion2.schedule", name="Termin-Tafel", category="AION 2", icon="mdi-calendar-clock",
        summary="AION-2-Termine als Nachricht, die sich jede Minute aktualisiert, mit Ping vorher.",
    )
    Settings = ScheduleSettings

    def __init__(self, ctx: BotContext) -> None:
        super().__init__(ctx)
        self.settings = GuildSettings(ctx.db, ScheduleSettings)
        self.announced: dict[int, set[Event]] = {}  # Server → schon gepingte Termine

    async def start(self) -> None:
        self.every(UPDATE_EVERY_S, self.update_all)

    async def update_all(self) -> None:
        now = time.time()
        for guild_id in self.settings.guilds_with("termine_channel"):
            settings = self.settings.get(guild_id)
            channel = self.client.get_channel(settings.termine_channel or 0)
            if not isinstance(channel, discord.TextChannel):
                continue
            try:
                await self.show_board(guild_id, channel, settings, now)
                await self.ping(guild_id, channel, settings, now)
            except discord.HTTPException as e:
                self.log.warning("Termin-Tafel %s: %r", guild_id, e)

    async def show_board(self, guild_id: int, channel: discord.TextChannel, settings: ScheduleSettings,
                         now: float) -> None:
        """Eigene Nachricht bearbeiten; fehlt sie (gelöscht, Kanal gewechselt), eine neue schicken."""
        if settings.termine_message and settings.termine_message_channel == channel.id:
            try:
                await channel.get_partial_message(settings.termine_message).edit(embed=board(now))
                return
            except discord.NotFound:
                pass
        message = await channel.send(embed=board(now))
        await self.settings.update(guild_id, {"termine_message": message.id, "termine_message_channel": channel.id})

    async def ping(self, guild_id: int, channel: discord.TextChannel, settings: ScheduleSettings, now: float) -> None:
        role = channel.guild.get_role(settings.termine_role) if settings.termine_role else None
        if role is None:
            return
        announced = self.announced.setdefault(guild_id, set())
        for name, start in due_pings(now, announced):
            announced.add((name, start))
            await channel.send(f"{role.mention} **{name}** beginnt <t:{start}:R>.",
                               allowed_mentions=discord.AllowedMentions(roles=True),
                               delete_after=max(MIN_PING_LIFETIME_S, start - now + MIN_PING_LIFETIME_S))
        # Altes vergessen, damit die Menge nicht wächst
        announced.intersection_update({key for key in announced if key[1] > now - FORGET_AFTER_S})
