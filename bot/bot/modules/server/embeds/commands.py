"""/embed-erstellen mit seinem Formular."""

from __future__ import annotations

from typing import Any

import discord
from discord import app_commands

from bot.core import ModuleCog
from bot.core.discord_checks import can_send
from bot.errors import UserError

from . import build_embed


class EmbedModal(discord.ui.Modal, title="Embed erstellen"):
    def __init__(self, channel: discord.TextChannel) -> None:
        super().__init__()
        self.channel = channel
        self.titel: discord.ui.TextInput[Any] = discord.ui.TextInput(label="Titel", max_length=256, required=False)
        self.beschreibung: discord.ui.TextInput[Any] = discord.ui.TextInput(
            label="Beschreibung", style=discord.TextStyle.paragraph, max_length=4000, required=False)
        self.farbe: discord.ui.TextInput[Any] = discord.ui.TextInput(
            label="Farbe (Hex, z. B. #5865F2)", required=False, max_length=7)
        self.bild_url: discord.ui.TextInput[Any] = discord.ui.TextInput(label="Bild-URL", required=False,
                                                                        max_length=500)
        for item in (self.titel, self.beschreibung, self.farbe, self.bild_url):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            embed = build_embed(str(self.titel.value), str(self.beschreibung.value), str(self.farbe.value),
                                str(self.bild_url.value))
        except UserError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return
        if not can_send(self.channel):
            await interaction.response.send_message(f"Ich darf in {self.channel.mention} nicht schreiben.",
                                                    ephemeral=True)
            return
        await self.channel.send(embed=embed)
        await interaction.response.send_message(f"Embed gepostet in {self.channel.mention}.", ephemeral=True)


class EmbedsCog(ModuleCog):
    @app_commands.command(name="embed-erstellen", description="Eigenes Embed per Formular erstellen und posten")
    @app_commands.describe(kanal="Kanal, in den das Embed gepostet wird (leer lassen = dieser Kanal)")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def create(self, interaction: discord.Interaction, kanal: discord.TextChannel | None = None) -> None:
        channel = kanal or interaction.channel
        if not isinstance(channel, discord.TextChannel):
            raise UserError("Bitte einen Textkanal angeben.")
        await interaction.response.send_modal(EmbedModal(channel))
