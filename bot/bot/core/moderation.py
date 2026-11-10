"""Ereignisse, über die die Moderations-Module miteinander reden (nexcore-Bus), ohne sich zu kennen.

- LOG: etwas gehört in den Log-Kanal (moderation.log schreibt es)
- QUIET_DELETE: diese Nachrichten löscht der Bot selbst, nicht einzeln loggen
- WARN: jemand soll verwarnt werden (moderation.warnings trägt ein und straft ab der Schwelle)
"""

from __future__ import annotations

from dataclasses import dataclass

import discord

LOG = "moderation.log"
QUIET_DELETE = "moderation.quiet_delete"
WARN = "moderation.warn"

CLIP_DEFAULT = 1000


@dataclass(frozen=True)
class LogEntry:
    guild: discord.Guild
    embed: discord.Embed
    file: discord.File | None = None  # z. B. der Verlauf eines geschlossenen Tickets


@dataclass(frozen=True)
class WarnRequest:
    guild: discord.Guild
    member: discord.Member
    moderator: discord.abc.User
    reason: str


def clip(text: str | None, limit: int = CLIP_DEFAULT) -> str:
    """Text für ein Embed-Feld kürzen; leer wird „(kein Text)“."""
    if not text:
        return "*(kein Text)*"
    return text if len(text) <= limit else text[: limit - 1] + "…"


def channel_mention(channel: discord.abc.MessageableChannel) -> str:
    """Erwähnung eines Server-Kanals oder Threads; für Direktnachrichten „?“."""
    return channel.mention if isinstance(channel, discord.abc.GuildChannel | discord.Thread) else "?"


def can_moderate(guild: discord.Guild, member: discord.Member) -> bool:
    """Steht das Mitglied unter der Rolle des Bots und ist nicht Besitzer?"""
    return member.top_role < guild.me.top_role and member != guild.owner
