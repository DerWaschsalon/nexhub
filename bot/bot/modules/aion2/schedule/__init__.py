"""Termin-Tafel für AION 2: eine Nachricht im eingestellten Kanal, die sich jede Minute selbst
aktualisiert (Riss, Shugo-Fest, Beritra-Luftangriff, Wächterin Kaira, Resets, Belagerung, Nahma).

Die Zeiten stehen als Discord-Zeitstempel in der Nachricht, jeder sieht sie also in seiner Zeitzone.
Einige Minuten vor einem Ereignis (einstellbar, nicht vor den Resets) kommt ein Ping an die eingestellte
Rolle, der sich nach Beginn selbst löscht. Auf Wunsch stehen die Wochentermine (Belagerung, Nahma) sieben
Tage im Voraus im Event-Kalender des Servers. Die Termine stehen genau einmal im Monorepo: nexproto.termine.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import ClassVar

import discord
from nexcore import ModuleInfo
from nexproto import termine

from bot.core import BotContext, BotModule, GuildSettings

from .settings import ScheduleSettings

UPDATE_EVERY_S = 60
FORGET_AFTER_S = 3600  # gemeldete Pings so lange merken, dann vergessen
CALENDAR_AHEAD_S = 7 * 86400  # so weit im Voraus stehen die Wochentermine im Event-Kalender
CALENDAR_EVERY_S = 3600  # so oft den Kalender abgleichen
MIN_PING_LIFETIME_S = 60
NO_PING = ("daily_reset", "weekly_reset")  # Schlüssel aus nexproto.termine
COLOUR = 0x7DD8D8

Event = tuple[str, int]  # (Schlüssel aus nexproto.termine, Beginn als Unix-Zeit)


def decode_announced(text: str) -> set[Event]:
    """Gepingte Termine aus den Einstellungen („Schlüssel@Beginn“, durch Komma getrennt); Unlesbares fällt weg."""
    pairs = (part.rpartition("@") for part in text.split(",") if "@" in part)
    return {(key, int(start)) for key, _, start in pairs if start.isdigit()}


def encode_announced(announced: set[Event]) -> str:
    return ",".join(f"{key}@{start}" for key, start in sorted(announced))


def board(now: float) -> discord.Embed:
    """Die Tafel: je Termin der nächste Beginn, oder „läuft bis …“, solange er offen ist."""
    lines = []
    for event, start, open_until in termine.upcoming(now):
        if open_until:
            lines.append(f"🟢 **{event.name_de}** läuft, bis <t:{int(open_until)}:t> (<t:{int(open_until)}:R>)")
        else:
            lines.append(f"**{event.name_de}** <t:{int(start)}:t> (<t:{int(start)}:R>)")
    embed = discord.Embed(title="AION 2 · Termine", description="\n".join(lines), color=COLOUR)
    embed.set_footer(text="Zeiten in deiner Zeitzone · aktualisiert sich jede Minute · Uhr des EU-Servers")
    return embed


def due_pings(now: float, announced: set[Event], lead_s: float) -> list[Event]:
    """Ereignisse, die in den nächsten `lead_s` Sekunden beginnen und noch nicht gemeldet sind."""
    due = []
    for event, start, open_until in termine.upcoming(now):
        key = (event.key, int(start))
        if event.key in NO_PING or open_until or key in announced:
            continue
        if 0 < start - now <= lead_s:
            due.append(key)
    return due


def calendar_entries(now: float) -> list[tuple[termine.Event, float]]:
    """Die Wochentermine (feste Wochentage, ohne die Resets) der nächsten sieben Tage: (Termin, Beginn)."""
    weekly = (event for event in termine.EVENTS if event.weekdays and event.key not in NO_PING)
    return [(event, start) for event in weekly for start in termine.starts_between(event, now, now + CALENDAR_AHEAD_S)]


class Schedule(BotModule):
    info: ClassVar[ModuleInfo] = ModuleInfo(
        id="aion2.schedule", name="Termin-Tafel", category="AION 2", icon="mdi-calendar-clock",
        summary="AION-2-Termine als Nachricht, die sich jede Minute aktualisiert, mit Ping vorher.",
    )
    Settings = ScheduleSettings

    def __init__(self, ctx: BotContext) -> None:
        super().__init__(ctx)
        self.settings = GuildSettings(ctx.db, ScheduleSettings)

    async def start(self) -> None:
        self.every(UPDATE_EVERY_S, self.update_all)
        self.every(CALENDAR_EVERY_S, self.sync_calendars)

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
        announced = decode_announced(settings.termine_announced)
        due = due_pings(now, announced, settings.termine_lead_minutes * 60)
        for key, start in due:
            name = termine.EVENT_BY_KEY[key].name_de
            await channel.send(f"{role.mention} **{name}** beginnt <t:{start}:R>.",
                               allowed_mentions=discord.AllowedMentions(roles=True),
                               delete_after=max(MIN_PING_LIFETIME_S, start - now + MIN_PING_LIFETIME_S))
        # Altes vergessen, damit die Liste nicht wächst; gespeichert wird nur, wenn sich etwas ändert
        kept = {key for key in announced | set(due) if key[1] > now - FORGET_AFTER_S}
        if kept != announced:
            await self.settings.update(guild_id, {"termine_announced": encode_announced(kept)})

    async def sync_calendars(self) -> None:
        now = time.time()
        for guild_id in self.settings.guilds_with("termine_events"):
            guild = self.client.get_guild(guild_id)
            if guild is None or not self.settings.get(guild_id).termine_events:
                continue
            try:
                await self.sync_calendar(guild, now)
            except discord.Forbidden:
                self.log.warning("Event-Kalender %s: dem Bot fehlt das Recht „Events verwalten“", guild_id)
            except discord.HTTPException as e:
                self.log.warning("Event-Kalender %s: %r", guild_id, e)

    async def sync_calendar(self, guild: discord.Guild, now: float) -> None:
        """Fehlende Wochentermine anlegen. Was schon im Kalender steht (gleicher Name und Beginn), bleibt."""
        existing = {(e.name, int(e.start_time.timestamp())) for e in await guild.fetch_scheduled_events()}
        for event, start in calendar_entries(now):
            if (event.name_de, int(start)) in existing:
                continue
            await guild.create_scheduled_event(
                name=event.name_de, start_time=datetime.fromtimestamp(start, UTC),
                end_time=datetime.fromtimestamp(start + event.open_min * 60, UTC),
                entity_type=discord.EntityType.external, privacy_level=discord.PrivacyLevel.guild_only,
                location=event.place or "AION 2")
