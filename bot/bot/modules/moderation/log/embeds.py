"""Wie die Einträge im Log-Kanal aussehen."""

from __future__ import annotations

import discord

from bot.core.moderation import channel_mention, clip

MAX_FIELD = 1000


def deleted(message: discord.Message) -> discord.Embed:
    e = discord.Embed(title="🗑️ Nachricht gelöscht", colour=discord.Colour.red(), description=clip(message.content))
    e.add_field(name="Von", value=f"{message.author.mention} ({message.author})")
    e.add_field(name="Kanal", value=channel_mention(message.channel))
    if message.attachments:
        e.add_field(name="Anhänge", value="\n".join(a.filename for a in message.attachments)[:MAX_FIELD],
                    inline=False)
    return e


def bulk_deleted(messages: list[discord.Message]) -> discord.Embed:
    return discord.Embed(title="🗑️ Mehrere Nachrichten gelöscht", colour=discord.Colour.red(),
                         description=f"{len(messages)} Nachrichten in {channel_mention(messages[0].channel)}")


def edited(before: discord.Message, after: discord.Message) -> discord.Embed:
    e = discord.Embed(title="✏️ Nachricht bearbeitet", colour=discord.Colour.gold(), url=after.jump_url)
    e.add_field(name="Vorher", value=clip(before.content), inline=False)
    e.add_field(name="Nachher", value=clip(after.content), inline=False)
    e.add_field(name="Von", value=f"{after.author.mention} ({after.author})")
    e.add_field(name="Kanal", value=channel_mention(after.channel))
    return e


def joined(member: discord.Member, is_new: bool) -> discord.Embed:
    e = discord.Embed(title="📥 Beigetreten", colour=discord.Colour.green(), description=f"{member.mention} ({member})")
    e.add_field(name="Konto erstellt",
                value=discord.utils.format_dt(member.created_at, "R") + (" ⚠️ neu" if is_new else ""))
    e.set_thumbnail(url=member.display_avatar.url)
    return e


def left(member: discord.Member) -> discord.Embed:
    e = discord.Embed(title="📤 Verlassen", colour=discord.Colour.dark_grey(),
                      description=f"{member.mention} ({member})")
    if member.joined_at:
        e.add_field(name="Dabei seit", value=discord.utils.format_dt(member.joined_at, "R"))
    roles = [r.mention for r in member.roles if not r.is_default()]
    if roles:
        e.add_field(name="Rollen", value=" ".join(roles)[:MAX_FIELD], inline=False)
    return e


def banned(user: discord.User | discord.Member, reason: str | None) -> discord.Embed:
    description = f"{user.mention} ({user})" + (f"\n{reason}" if reason else "")
    return discord.Embed(title="🔨 Gebannt", colour=discord.Colour.dark_red(), description=description)


def unbanned(user: discord.User) -> discord.Embed:
    return discord.Embed(title="🔓 Entbannt", colour=discord.Colour.teal(), description=f"{user.mention} ({user})")


def member_changed(before: discord.Member, after: discord.Member) -> discord.Embed | None:
    """Rollen dazu oder weg, neuer Spitzname; None, wenn nichts davon passiert ist."""
    changes = []
    added = [r for r in after.roles if r not in before.roles]
    removed = [r for r in before.roles if r not in after.roles]
    if added:
        changes.append("➕ " + " ".join(r.mention for r in added))
    if removed:
        changes.append("➖ " + " ".join(r.mention for r in removed))
    if before.nick != after.nick:
        changes.append(f"Spitzname: {before.nick or '–'} → {after.nick or '–'}")
    if not changes:
        return None
    return discord.Embed(title="👤 Mitglied geändert", colour=discord.Colour.blue(),
                         description=f"{after.mention} ({after})\n" + "\n".join(changes))
