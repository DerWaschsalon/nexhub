"""Spamschutz: greift nicht bei Bots und bei Leuten mit „Nachrichten verwalten“.

- mehr als SPAM_COUNT Nachrichten in SPAM_WINDOW_S Sekunden: Nachrichten weg, 5 Minuten Timeout
- mehr als MENTION_LIMIT Erwähnungen in einer Nachricht: Nachricht weg, 10 Minuten Timeout
- Discord-Einladungslinks (außer „Einladungslinks erlauben“ ist an): Nachricht weg
"""

from __future__ import annotations

import re
import time
from collections import defaultdict, deque
from datetime import timedelta
from typing import ClassVar

import discord
from nexcore import ModuleInfo

from bot.core import BotContext, BotModule, GuildSettings
from bot.core.moderation import LOG, QUIET_DELETE, LogEntry, can_moderate, channel_mention, clip
from bot.core.module import Listener

from .settings import AntispamSettings

SPAM_COUNT = 6
SPAM_WINDOW_S = 8.0
MENTION_LIMIT = 6
SPAM_TIMEOUT = timedelta(minutes=5)
MENTION_TIMEOUT = timedelta(minutes=10)
NOTICE_SECONDS = 15
REMEMBERED = 20  # so viele Nachrichten je Mitglied merkt sich der Spamschutz
INVITE_RE = re.compile(r"(?:discord(?:app)?\.com/invite|discord\.gg)/[\w-]+", re.I)

Recent = deque[tuple[float, discord.Message]]


def exempt(message: discord.Message) -> bool:
    """Bots, Direktnachrichten und Leute mit „Nachrichten verwalten“ prüft der Spamschutz nicht."""
    author, channel = message.author, message.channel
    if message.guild is None or author.bot or not isinstance(author, discord.Member):
        return True
    return isinstance(channel, discord.abc.GuildChannel) and channel.permissions_for(author).manage_messages


def mention_count(message: discord.Message) -> int:
    return len(message.raw_mentions) + len(message.raw_role_mentions)


class Antispam(BotModule):
    info: ClassVar[ModuleInfo] = ModuleInfo(
        id="moderation.antispam", name="Spamschutz", category="Moderation", icon="mdi-shield",
        summary="Löscht Nachrichtenfluten, Massen-Erwähnungen und Einladungslinks.",
    )
    Settings = AntispamSettings

    def __init__(self, ctx: BotContext) -> None:
        super().__init__(ctx)
        self.settings = GuildSettings(ctx.db, AntispamSettings)
        self.recent: defaultdict[tuple[int, int], Recent] = defaultdict(lambda: deque(maxlen=REMEMBERED))

    def listeners(self) -> dict[str, Listener]:
        return {"on_message": self.on_message}

    async def on_message(self, message: discord.Message) -> None:
        if exempt(message):
            return
        assert message.guild is not None  # von exempt geprüft
        settings = self.settings.get(message.guild.id)
        if not settings.antispam:
            return
        if not settings.allow_invites and INVITE_RE.search(message.content):
            await self.punish(message, [message], None, "Einladungslink")
        elif mention_count(message) > MENTION_LIMIT:
            await self.punish(message, [message], MENTION_TIMEOUT, "Massen-Erwähnung")
        else:
            await self.count(message)

    async def count(self, message: discord.Message) -> None:
        assert message.guild is not None
        recent = self.recent[(message.guild.id, message.author.id)]
        now = time.monotonic()
        recent.append((now, message))
        in_window = [m for t, m in recent if now - t <= SPAM_WINDOW_S]
        if len(in_window) > SPAM_COUNT:
            recent.clear()
            await self.punish(message, in_window, SPAM_TIMEOUT, "Spam")

    async def punish(self, message: discord.Message, messages: list[discord.Message], timeout: timedelta | None,
                     reason: str) -> None:
        await self.ctx.bus.emit(QUIET_DELETE, [m.id for m in messages])
        for m in messages:
            try:
                await m.delete()
            except discord.HTTPException:
                pass  # schon weg
        muted = await self.mute(message, timeout, reason)
        notice = f"{message.author.mention}, deine Nachricht wurde entfernt ({reason})."
        if muted and timeout:
            notice += f" Du kannst {int(timeout.total_seconds() // 60)} Minuten nicht schreiben."
        try:
            await message.channel.send(notice, delete_after=NOTICE_SECONDS)
        except discord.HTTPException:
            pass
        await self.report(message, messages, timeout if muted else None, reason)

    async def mute(self, message: discord.Message, timeout: timedelta | None, reason: str) -> bool:
        member, guild = message.author, message.guild
        if timeout is None or guild is None or not isinstance(member, discord.Member):
            return False
        if not guild.me.guild_permissions.moderate_members or not can_moderate(guild, member):
            return False
        try:
            await member.timeout(timeout, reason=f"Spamschutz: {reason}")
        except discord.HTTPException:
            return False
        return True

    async def report(self, message: discord.Message, messages: list[discord.Message], timeout: timedelta | None,
                     reason: str) -> None:
        assert message.guild is not None
        e = discord.Embed(title=f"🛡️ Spamschutz: {reason}", colour=discord.Colour.orange(),
                          description=clip(message.content, 500))
        e.add_field(name="Mitglied", value=f"{message.author.mention} ({message.author})")
        e.add_field(name="Kanal", value=channel_mention(message.channel))
        action = f"{len(messages)} Nachricht(en) gelöscht"
        if timeout:
            action += f", Timeout {int(timeout.total_seconds() // 60)} Min."
        e.add_field(name="Maßnahme", value=action)
        await self.ctx.bus.emit(LOG, LogEntry(message.guild, e))
