"""Slash-Befehle des Levelsystems: Rang, Rangliste, XP von Hand, Belohnungen, Ausnahmen."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands

from bot.core import ModuleCog
from bot.core.discord_checks import can_assign
from bot.errors import UserError

from .rankcard import render_rank_card
from .store import level_from_xp
from .voice import format_duration

if TYPE_CHECKING:
    from . import Levels

AVATAR_SIZE = 256


def member_of(interaction: discord.Interaction, chosen: discord.Member | None) -> discord.Member:
    member = chosen or interaction.user
    if not isinstance(member, discord.Member):
        raise UserError("Das geht nur auf einem Server.")
    return member


class LevelsCog(ModuleCog):
    module: "Levels"

    @app_commands.command(name="rang", description="Deine Rangkarte anzeigen (oder die eines anderen Mitglieds)")
    @app_commands.guild_only()
    async def rank(self, interaction: discord.Interaction, nutzer: discord.Member | None = None) -> None:
        member = member_of(interaction, nutzer)
        place, xp = await self.module.store.rank_and_xp(member.guild.id, member.id)
        level, into_level, needed = level_from_xp(xp)
        await interaction.response.defer()
        try:
            avatar = await member.display_avatar.with_size(AVATAR_SIZE).read()
            image = render_rank_card(avatar, member.display_name, level, place, into_level, needed)
            await interaction.followup.send(file=discord.File(image, filename="rang.png"))
        except (discord.HTTPException, OSError, ValueError) as e:  # Bild ist Zugabe, Text geht immer
            self.module.log.warning("Rangkarte für %s: %r", member.id, e)
            await interaction.followup.send(f"{member.mention}: Level {level} ({into_level}/{needed} XP), "
                                            f"Rang #{place}.")

    @app_commands.command(name="rangliste", description="Die 10 Mitglieder mit den meisten XP anzeigen")
    @app_commands.guild_only()
    async def leaderboard(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None  # guild_only
        rows = await self.module.store.top(interaction.guild.id)
        if not rows:
            await interaction.response.send_message("Noch keine XP gesammelt.", ephemeral=True)
            return
        lines = []
        for place, row in enumerate(rows, start=1):
            member = interaction.guild.get_member(row["user_id"])
            name = member.mention if member else f"(ausgetreten: {row['user_id']})"
            lines.append(f"**#{place}** {name} – Level {level_from_xp(row['xp'])[0]} ({row['xp']} XP)")
        embed = discord.Embed(title="🏆 Rangliste", description="\n".join(lines), colour=discord.Colour.gold())
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="level-xp-geben", description="XP eines Mitglieds von Hand ändern (auch negativ)")
    @app_commands.describe(mitglied="Betroffenes Mitglied", menge="XP-Änderung, z. B. 100 oder -50")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def give_xp(self, interaction: discord.Interaction, mitglied: discord.Member,
                      menge: app_commands.Range[int, -1_000_000, 1_000_000]) -> None:
        _place, xp = await self.module.store.rank_and_xp(mitglied.guild.id, mitglied.id)
        new_xp = max(0, xp + menge)
        await self.module.store.set_xp(mitglied.guild.id, mitglied.id, new_xp)
        await interaction.response.send_message(
            f"{mitglied.mention}: jetzt {new_xp} XP (Level {level_from_xp(new_xp)[0]}).", ephemeral=True)

    @app_commands.command(name="level-belohnung",
                          description="Rolle als Belohnung ab einem bestimmten Level setzen oder entfernen")
    @app_commands.describe(level="Ab diesem Level wird die Rolle vergeben", rolle="Die Belohnungsrolle",
                           entfernen="Diese Belohnung wieder entfernen, statt sie zu setzen")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def set_reward(self, interaction: discord.Interaction, level: app_commands.Range[int, 1, 1000],
                         rolle: discord.Role, entfernen: bool = False) -> None:
        if entfernen:
            await self.module.store.set_reward(rolle.guild.id, level, None)
            await interaction.response.send_message(f"Belohnung für Level {level} entfernt.", ephemeral=True)
            return
        if not can_assign(rolle.guild, rolle):
            raise UserError(f"{rolle.mention} kann ich nicht vergeben. Meine Rolle muss in den "
                            "Servereinstellungen über ihr stehen.")
        await self.module.store.set_reward(rolle.guild.id, level, rolle.id)
        await interaction.response.send_message(f"Ab Level {level}: {rolle.mention}.", ephemeral=True)

    @app_commands.command(name="level-kanal-ohne-xp",
                          description="Kanal zur Liste ohne XP-Sammeln hinzufügen/entfernen")
    @app_commands.describe(kanal="Betroffener Kanal", entfernen="Aus der Liste entfernen statt hinzuzufügen")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def no_xp_channel(self, interaction: discord.Interaction, kanal: discord.TextChannel,
                            entfernen: bool = False) -> None:
        await self.module.toggle_exception(kanal.guild.id, "level_no_xp_channels", kanal.id, entfernen)
        await interaction.response.send_message(
            f"{kanal.mention} {'sammelt wieder XP.' if entfernen else 'sammelt keine XP mehr.'}", ephemeral=True)

    @app_commands.command(name="level-rolle-ohne-xp",
                          description="Rolle zur Liste ohne XP-Sammeln hinzufügen/entfernen")
    @app_commands.describe(rolle="Betroffene Rolle", entfernen="Aus der Liste entfernen statt hinzuzufügen")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def no_xp_role(self, interaction: discord.Interaction, rolle: discord.Role, entfernen: bool = False) -> None:
        await self.module.toggle_exception(rolle.guild.id, "level_no_xp_roles", rolle.id, entfernen)
        await interaction.response.send_message(
            f"{rolle.mention} {'sammelt wieder XP.' if entfernen else 'sammelt keine XP mehr.'}", ephemeral=True)

    @app_commands.command(name="sprachzeit",
                          description="Verbrachte Zeit im Sprachkanal anzeigen (leer = deine eigene)")
    @app_commands.guild_only()
    async def voice_time(self, interaction: discord.Interaction, nutzer: discord.Member | None = None) -> None:
        member = member_of(interaction, nutzer)
        row = await self.module.store.entry(member.guild.id, member.id)
        seconds = int(row["voice_seconds"]) if row else 0
        await interaction.response.send_message(f"{member.mention} war {format_duration(seconds)} im Sprachkanal.",
                                                ephemeral=True)
