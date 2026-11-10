"""Server-Bericht für /aufraeumen bericht: Kanäle mit letzter Aktivität, Rollen, Bots, als Markdown."""

from __future__ import annotations

from datetime import datetime

import discord

QUIET_DAYS = 90  # so lange ohne Nachricht gilt ein Kanal als tot
KIND_NAMES = {discord.ChannelType.text: "Text", discord.ChannelType.voice: "Sprache",
              discord.ChannelType.forum: "Forum", discord.ChannelType.news: "Ankündigung",
              discord.ChannelType.stage_voice: "Bühne"}


def last_activity(channel: discord.TextChannel | discord.VoiceChannel, now: datetime) -> str:
    if not channel.last_message_id:
        return "nie / unbekannt"
    days = (now - discord.utils.snowflake_time(channel.last_message_id)).days
    return f"vor {days} Tagen" + ("  ⚠️" if days > QUIET_DAYS else "")


def channel_lines(guild: discord.Guild, now: datetime) -> list[str]:
    out = ["## Kanäle"]
    for category, channels in guild.by_category():
        out.append(f"\n### {category.name if category else '(ohne Kategorie)'}")
        for channel in channels:
            line = f"- #{channel.name} ({KIND_NAMES.get(channel.type, str(channel.type))})"
            if isinstance(channel, discord.TextChannel | discord.VoiceChannel):
                line += f" – letzte Nachricht {last_activity(channel, now)}"
            if not channel.permissions_for(guild.default_role).view_channel:
                line += " – privat"
            out.append(line)
    return out


def role_lines(guild: discord.Guild) -> list[str]:
    out = ["\n## Rollen"]
    for role in reversed(guild.roles):
        if role.is_default():
            continue
        flags = []
        if role.managed:
            flags.append("gehört zu Bot/Integration")
        if role.permissions.administrator:
            flags.append("Administrator")
        if not role.members and not role.managed:
            flags.append("⚠️ niemand hat sie")
        out.append(f"- {role.name} – {len(role.members)} Mitglieder" + (f" – {', '.join(flags)}" if flags else ""))
    return out


def bot_lines(guild: discord.Guild) -> list[str]:
    out = ["\n## Bots"]
    for member in guild.members:
        if member.bot:
            out.append(f"- {member} – seit {member.joined_at:%d.%m.%Y}" if member.joined_at else f"- {member}")
    return out


def server_report(guild: discord.Guild, now: datetime) -> str:
    head = [f"# Server-Bericht: {guild.name}", f"Stand: {now:%d.%m.%Y %H:%M} UTC · {guild.member_count} Mitglieder", ""]
    return "\n".join(head + channel_lines(guild, now) + role_lines(guild) + bot_lines(guild))
