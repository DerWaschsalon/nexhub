"""/vc: den eigenen Sprachkanal verwalten."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from bot.core import ModuleCog
from bot.errors import UserError

if TYPE_CHECKING:  # nur für die Typprüfung, das Modul übergibt sich selbst
    from . import TempVoice


def member_of(interaction: discord.Interaction) -> discord.Member:
    if not isinstance(interaction.user, discord.Member):
        raise UserError("Das geht nur auf einem Server.")
    return interaction.user


@app_commands.guild_only()
class TempVoiceCog(commands.GroupCog, ModuleCog, group_name="vc",
                   group_description="Deinen eigenen Sprachkanal verwalten"):
    module: "TempVoice"

    @app_commands.command(name="name", description="Deinen Kanal umbenennen")
    async def rename(self, interaction: discord.Interaction, name: app_commands.Range[str, 1, 90]) -> None:
        channel = await self.module.own_channel(member_of(interaction))
        await channel.edit(name=name)
        await interaction.response.send_message(f"Heißt jetzt **{discord.utils.escape_markdown(name)}**.",
                                                ephemeral=True)

    @app_commands.command(name="limit", description="Höchstzahl an Leuten (0 = unbegrenzt)")
    async def limit(self, interaction: discord.Interaction, anzahl: app_commands.Range[int, 0, 99]) -> None:
        channel = await self.module.own_channel(member_of(interaction))
        await channel.edit(user_limit=anzahl)
        await interaction.response.send_message(f"Limit: {anzahl or 'keins'}.", ephemeral=True)

    @app_commands.command(name="sperren", description="Niemand Neues kommt rein (außer Leuten, die du einlädst)")
    async def lock(self, interaction: discord.Interaction) -> None:
        member = member_of(interaction)
        channel = await self.module.own_channel(member)
        await channel.set_permissions(member.guild.default_role, connect=False)
        await interaction.response.send_message(
            "🔒 Gesperrt. Wer drin ist, bleibt drin. `/vc einladen` lässt Leute rein.", ephemeral=True)

    @app_commands.command(name="freigeben", description="Kanal wieder für alle öffnen")
    async def unlock(self, interaction: discord.Interaction) -> None:
        member = member_of(interaction)
        channel = await self.module.own_channel(member)
        await channel.set_permissions(member.guild.default_role, connect=None)
        await interaction.response.send_message("🔓 Offen.", ephemeral=True)

    @app_commands.command(name="einladen", description="Jemanden in deinen gesperrten Kanal lassen")
    async def invite(self, interaction: discord.Interaction, mitglied: discord.Member) -> None:
        channel = await self.module.own_channel(member_of(interaction))
        await channel.set_permissions(mitglied, connect=True, view_channel=True)
        await interaction.response.send_message(f"{mitglied.mention} darf jetzt rein.", ephemeral=True)

    @app_commands.command(name="uebernehmen", description="Kanal übernehmen, wenn der Besitzer weg ist")
    async def claim(self, interaction: discord.Interaction) -> None:
        await self.module.claim(member_of(interaction))
        await interaction.response.send_message("Der Kanal gehört jetzt dir.", ephemeral=True)
