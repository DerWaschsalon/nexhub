"""Log-Kanal: gelöschte und bearbeitete Nachrichten, Beitritte (mit Warnung bei neuen Konten),
Austritte, Banns, Rollen- und Spitznamen-Änderungen, dazu alles, was andere Module über das Ereignis
LOG melden. Nachrichten, die der Bot selbst löscht (QUIET_DELETE), erscheinen nicht einzeln."""

from __future__ import annotations

from datetime import timedelta
from typing import ClassVar

import discord
from nexcore import ModuleInfo

from bot.core import BotContext, BotModule, GuildSettings
from bot.core.moderation import LOG, QUIET_DELETE, LogEntry
from bot.core.module import Listener

from . import embeds
from .settings import LogSettings

NEW_ACCOUNT = timedelta(days=7)
BAN_LOOKUP = 5  # so viele Audit-Log-Einträge reichen, um den Grund eines frischen Banns zu finden


class ModerationLog(BotModule):
    info: ClassVar[ModuleInfo] = ModuleInfo(
        id="moderation.log", name="Moderations-Log", category="Moderation", icon="mdi-text-box-search",
        summary="Log-Kanal für Löschungen, Bearbeitungen, Beitritte, Banns und Rollen.",
    )
    Settings = LogSettings

    def __init__(self, ctx: BotContext) -> None:
        super().__init__(ctx)
        self.settings = GuildSettings(ctx.db, LogSettings)
        self.quiet: set[int] = set()

    async def start(self) -> None:
        self.on(LOG, self.on_log)
        self.on(QUIET_DELETE, self.on_quiet_delete)

    def listeners(self) -> dict[str, Listener]:
        return {"on_message_delete": self.on_message_delete, "on_bulk_message_delete": self.on_bulk_delete,
                "on_message_edit": self.on_message_edit, "on_member_join": self.on_member_join,
                "on_member_remove": self.on_member_remove, "on_member_ban": self.on_member_ban,
                "on_member_unban": self.on_member_unban, "on_member_update": self.on_member_update}

    async def on_log(self, entry: LogEntry) -> None:
        await self.write(entry.guild, entry.embed, entry.file)

    async def on_quiet_delete(self, message_ids: list[int]) -> None:
        self.quiet.update(message_ids)

    async def write(self, guild: discord.Guild, embed: discord.Embed, file: discord.File | None = None) -> None:
        channel_id = self.settings.get(guild.id).log_channel
        channel = guild.get_channel(channel_id) if channel_id else None
        if not isinstance(channel, discord.TextChannel):
            return
        embed.timestamp = discord.utils.utcnow()
        try:
            if file is None:
                await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            else:
                await channel.send(embed=embed, file=file, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException as e:
            self.log.warning("Log %s: %r", guild.id, e)

    def is_log_channel(self, channel: discord.abc.MessageableChannel) -> bool:
        if not isinstance(channel, discord.abc.GuildChannel | discord.Thread):
            return False
        return channel.id == self.settings.get(channel.guild.id).log_channel

    async def on_message_delete(self, message: discord.Message) -> None:
        if message.id in self.quiet:
            self.quiet.discard(message.id)
            return
        if message.guild is None or message.author.bot or self.is_log_channel(message.channel):
            return
        await self.write(message.guild, embeds.deleted(message))

    async def on_bulk_delete(self, messages: list[discord.Message]) -> None:
        first = messages[0] if messages else None
        if first is None or first.guild is None or self.is_log_channel(first.channel):
            return
        if all(m.id in self.quiet for m in messages):
            self.quiet.difference_update(m.id for m in messages)
            return
        await self.write(first.guild, embeds.bulk_deleted(messages))

    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if after.guild is None or after.author.bot or before.content == after.content:
            return
        await self.write(after.guild, embeds.edited(before, after))

    async def on_member_join(self, member: discord.Member) -> None:
        is_new = discord.utils.utcnow() - member.created_at < NEW_ACCOUNT
        await self.write(member.guild, embeds.joined(member, is_new))

    async def on_member_remove(self, member: discord.Member) -> None:
        await self.write(member.guild, embeds.left(member))

    async def on_member_ban(self, guild: discord.Guild, user: discord.User | discord.Member) -> None:
        # Grund aus dem Audit-Log: /ban und Banns direkt in Discord erzeugen so nur einen Eintrag
        await self.write(guild, embeds.banned(user, await self.ban_reason(guild, user.id)))

    async def ban_reason(self, guild: discord.Guild, user_id: int) -> str | None:
        if not guild.me.guild_permissions.view_audit_log:
            return None
        try:
            async for entry in guild.audit_logs(action=discord.AuditLogAction.ban, limit=BAN_LOOKUP):
                if entry.target and entry.target.id == user_id:
                    return entry.reason
        except discord.HTTPException:
            return None
        return None

    async def on_member_unban(self, guild: discord.Guild, user: discord.User) -> None:
        await self.write(guild, embeds.unbanned(user))

    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        embed = embeds.member_changed(before, after)
        if embed is not None:
            await self.write(after.guild, embed)
