"""Begrüßung neuer Mitglieder und Autorolle (sofort beim Beitritt, unabhängig von der Verifizierung,
die bei Bestätigung ihre eigene Rolle vergibt)."""

from __future__ import annotations

from typing import ClassVar

import discord
from nexcore import ModuleInfo

from bot.core import BotContext, BotModule, GuildSettings
from bot.core.discord_checks import can_assign
from bot.core.module import Listener

from .settings import DEFAULT_WELCOME, WelcomeSettings


def welcome_text(template: str, member: discord.Member) -> str:
    """Platzhalter {user} {name} {server} {anzahl} einsetzen."""
    guild = member.guild
    return (template.replace("{user}", member.mention)
                    .replace("{name}", discord.utils.escape_markdown(member.display_name))
                    .replace("{server}", guild.name)
                    .replace("{anzahl}", str(guild.member_count)))


def welcome_embed(member: discord.Member, text: str) -> discord.Embed:
    embed = discord.Embed(description=text, colour=discord.Colour.green())
    embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
    embed.set_footer(text=f"Mitglied Nr. {member.guild.member_count}")
    return embed


class Welcome(BotModule):
    info: ClassVar[ModuleInfo] = ModuleInfo(
        id="server.welcome", name="Begrüßung", category="Server", icon="mdi-hand-wave",
        summary="Begrüßt neue Mitglieder und gibt ihnen die Autorolle.",
    )
    Settings = WelcomeSettings

    def __init__(self, ctx: BotContext) -> None:
        super().__init__(ctx)
        self.settings = GuildSettings(ctx.db, WelcomeSettings)

    def listeners(self) -> dict[str, Listener]:
        return {"on_member_join": self.on_member_join}

    async def on_member_join(self, member: discord.Member) -> None:
        if member.bot:
            return
        settings = self.settings.get(member.guild.id)
        await self.give_autorole(member, settings)
        await self.greet(member, settings)

    async def give_autorole(self, member: discord.Member, settings: WelcomeSettings) -> None:
        role = member.guild.get_role(settings.autorole) if settings.autorole else None
        if role is None or not can_assign(member.guild, role):
            return
        try:
            await member.add_roles(role, reason="Autorolle")
        except discord.HTTPException as e:
            self.log.warning("Autorolle %s: %r", member.guild.id, e)

    async def greet(self, member: discord.Member, settings: WelcomeSettings) -> None:
        channel = member.guild.get_channel(settings.welcome_channel) if settings.welcome_channel else None
        if not isinstance(channel, discord.TextChannel):
            return
        text = welcome_text(settings.welcome_text or DEFAULT_WELCOME, member)
        try:
            await channel.send(content=member.mention, embed=welcome_embed(member, text),
                               allowed_mentions=discord.AllowedMentions(users=True))
        except discord.HTTPException as e:
            self.log.warning("Willkommen %s: %r", member.guild.id, e)
