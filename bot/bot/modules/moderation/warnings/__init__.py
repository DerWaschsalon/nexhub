"""Verwarnungen und Strafen: /warn, /warnungen, /warnung-loeschen, /timeout, /kick, /ban, /unban und
dieselben Maßnahmen im NexHub. Ab einer einstellbaren Zahl Verwarnungen straft der Bot von selbst.
Andere Module (Automod) verwarnen über das Ereignis WARN."""

from __future__ import annotations

from datetime import timedelta
from typing import ClassVar

import discord
from discord.ext import commands
from nexcore import ModuleInfo

from bot.core import BotContext, BotModule, GuildSettings
from bot.core.moderation import LOG, WARN, LogEntry, WarnRequest, can_moderate
from bot.core.module import Listener
from bot.errors import UserError
from bot.hubpages import Page

from .settings import WarningSettings
from .store import WarningStore

SECTION = "verwarnungen"  # Bereich in bot/forms.py
AUTO_TIMEOUT = timedelta(hours=1)
SECONDS_PER_DAY = 86_400


def reason_line(reason: str | None) -> str:
    return f"\nGrund: {reason}" if reason else ""


class Warnings(BotModule):
    info: ClassVar[ModuleInfo] = ModuleInfo(
        id="moderation.warnings", name="Verwarnungen und Strafen", category="Moderation", icon="mdi-alert",
        summary="Verwarnungen mit Verlauf, Timeout, Kick, Bann und automatische Strafe ab einer Schwelle.",
    )
    Settings = WarningSettings

    def __init__(self, ctx: BotContext) -> None:
        super().__init__(ctx)
        self.settings = GuildSettings(ctx.db, WarningSettings)
        self.store = WarningStore(ctx.db)

    async def start(self) -> None:
        self.on(WARN, self.on_warn_request)

    def listeners(self) -> dict[str, Listener]:
        return {"on_settings_changed": self.on_settings_changed}

    def cog(self) -> commands.Cog:
        from .commands import WarningsCog

        return WarningsCog(self)

    def pages(self) -> list[Page]:
        from .hub import moderation_page

        return [moderation_page(self)]

    async def on_settings_changed(self, guild: discord.Guild, section_id: str) -> None:
        """Ohne Schwelle gibt es keine Strafe: die Aktion fällt dann auf ihren Standard zurück."""
        if section_id == SECTION and not self.settings.get(guild.id).warn_threshold:
            await self.db.set(guild.id, "warn_action", None)

    async def on_warn_request(self, request: WarnRequest) -> None:
        await self.warn(request.guild, request.member, request.moderator, request.reason)

    async def report(self, guild: discord.Guild, embed: discord.Embed) -> None:
        await self.ctx.bus.emit(LOG, LogEntry(guild, embed))

    async def warn(self, guild: discord.Guild, member: discord.Member, moderator: discord.abc.User,
                   reason: str) -> int:
        """Eintragen, per DM Bescheid geben, loggen und ab der Schwelle strafen; zurück kommt die Nummer."""
        if member.bot:
            raise UserError("Bots kann ich nicht verwarnen.")
        count = await self.store.add(guild.id, member.id, moderator.id, reason)
        await tell(member, f"Du wurdest auf **{guild.name}** verwarnt (Nr. {count}).\nGrund: {reason}")
        await self.report(guild, discord.Embed(
            title=f"⚠️ Verwarnung Nr. {count}", colour=discord.Colour.yellow(),
            description=f"{member.mention} ({member})\nVon {moderator.mention}\nGrund: {reason}"))
        settings = self.settings.get(guild.id)
        if settings.warn_threshold and count == settings.warn_threshold:
            await self.auto_punish(member, settings.warn_action, count)
        return count

    async def auto_punish(self, member: discord.Member, action: str, count: int) -> None:
        guild = member.guild
        if not can_moderate(guild, member):
            return
        reason = f"Automatisch: {count} Verwarnungen"
        perms = guild.me.guild_permissions
        try:
            if action == "timeout" and perms.moderate_members:
                await member.timeout(AUTO_TIMEOUT, reason=reason)
            elif action == "kick" and perms.kick_members:
                await member.kick(reason=reason)
            elif action == "ban" and perms.ban_members:
                await member.ban(reason=reason, delete_message_seconds=0)
            else:
                return
        except discord.HTTPException as e:
            self.log.warning("Automatische Strafe %s: %r", member.id, e)
            return
        if action != "ban":  # ein Bann landet von selbst im Log (moderation.log, on_member_ban)
            await self.report(guild, discord.Embed(
                title=f"🚨 Automatisch: {action}", colour=discord.Colour.dark_red(),
                description=f"{member.mention} ({member}) nach {count} Verwarnungen"))

    async def timeout(self, member: discord.Member, minutes: int, by: str, reason: str | None) -> None:
        check(member, "stummschalten")
        await member.timeout(timedelta(minutes=minutes), reason=f"{by}: {reason or 'ohne Grund'}")
        await self.report(member.guild, discord.Embed(
            title="⏳ Timeout", colour=discord.Colour.orange(),
            description=f"{member.mention} für {minutes} Min.\nVon {by}{reason_line(reason)}"))

    async def kick(self, member: discord.Member, by: str, reason: str | None) -> None:
        check(member, "entfernen")
        await tell(member, f"Du wurdest von **{member.guild.name}** entfernt.{reason_line(reason)}")
        await member.kick(reason=f"{by}: {reason or 'ohne Grund'}")
        await self.report(member.guild, discord.Embed(
            title="👢 Kick", colour=discord.Colour.orange(),
            description=f"{member.mention} ({member})\nVon {by}{reason_line(reason)}"))

    async def ban(self, member: discord.Member, by: str, reason: str | None, days: int) -> None:
        """Bannen; im Log steht es über on_member_ban (moderation.log), mit Grund aus dem Audit-Log."""
        check(member, "bannen")
        await tell(member, f"Du wurdest von **{member.guild.name}** gebannt.{reason_line(reason)}")
        await member.ban(reason=f"{by}: {reason or 'ohne Grund'}", delete_message_seconds=days * SECONDS_PER_DAY)

    @staticmethod
    async def unban(guild: discord.Guild, user_id: int, reason: str) -> None:
        try:
            await guild.unban(discord.Object(id=user_id), reason=reason)
        except discord.NotFound:
            raise UserError("Dieser Nutzer ist nicht gebannt.") from None


def check(member: discord.Member, what: str) -> None:
    if not can_moderate(member.guild, member):
        raise UserError(f"{member.display_name} kann ich nicht {what}.")


async def tell(member: discord.Member, text: str) -> None:
    """Direktnachricht, wenn das Mitglied sie zulässt."""
    try:
        await member.send(text)
    except discord.HTTPException:
        pass
