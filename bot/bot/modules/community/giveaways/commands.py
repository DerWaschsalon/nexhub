"""/giveaway-erstellen und /giveaway-reroll."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands

from bot.core import ModuleCog
from bot.errors import UserError

if TYPE_CHECKING:
    from . import Giveaways


class GiveawaysCog(ModuleCog):
    module: "Giveaways"

    @app_commands.command(name="giveaway-erstellen", description="Giveaway mit Teilnahme-Button starten")
    @app_commands.describe(kanal="Kanal für das Giveaway", preis="Was es zu gewinnen gibt",
                           dauer="z. B. 2h, 30m, 1d2h", gewinner="Wie viele Gewinner ausgelost werden (Standard 1)")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def create(self, interaction: discord.Interaction, kanal: discord.TextChannel, preis: str, dauer: str,
                     gewinner: app_commands.Range[int, 1, 20] = 1) -> None:
        await self.module.begin(kanal, preis, dauer, gewinner, interaction.user.id)
        await interaction.response.send_message(f"Giveaway gestartet in {kanal.mention}.", ephemeral=True)

    @app_commands.command(name="giveaway-reroll", description="Neue Gewinner für ein beendetes Giveaway auslosen")
    @app_commands.describe(giveaway_nachricht_id="Nachrichten-ID des Giveaway-Posts")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def reroll(self, interaction: discord.Interaction, giveaway_nachricht_id: str) -> None:
        if not giveaway_nachricht_id.isdigit():
            raise UserError("Das ist keine gültige Nachrichten-ID.")
        assert interaction.guild_id is not None  # guild_only
        row = await self.module.store.get(interaction.guild_id, int(giveaway_nachricht_id))
        await interaction.response.send_message(await self.module.redraw(row), ephemeral=True)
