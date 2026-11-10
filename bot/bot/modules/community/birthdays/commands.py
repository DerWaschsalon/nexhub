"""Slash-Befehle der Geburtstage."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands

from bot.core import ModuleCog

if TYPE_CHECKING:
    from . import Birthdays


class BirthdaysCog(ModuleCog):
    module: "Birthdays"

    @app_commands.command(name="geburtstag-setzen",
                          description="Deinen Geburtstag eintragen (für die tägliche Gratulation)")
    @app_commands.describe(tag="Tag (1-31)", monat="Monat (1-12)")
    @app_commands.guild_only()
    async def set_birthday(self, interaction: discord.Interaction, tag: app_commands.Range[int, 1, 31],
                           monat: app_commands.Range[int, 1, 12]) -> None:
        assert interaction.guild_id is not None  # guild_only
        await self.module.store.put(interaction.guild_id, interaction.user.id, tag, monat)
        await interaction.response.send_message(f"Geburtstag gespeichert: {tag}.{monat}.", ephemeral=True)

    @app_commands.command(name="geburtstag-loeschen", description="Deinen eingetragenen Geburtstag wieder löschen")
    @app_commands.guild_only()
    async def delete_birthday(self, interaction: discord.Interaction) -> None:
        assert interaction.guild_id is not None  # guild_only
        await self.module.store.delete(interaction.guild_id, interaction.user.id)
        await interaction.response.send_message("Geburtstag gelöscht.", ephemeral=True)

    @app_commands.command(name="geburtstag",
                          description="Eingetragenen Geburtstag eines Mitglieds anzeigen (leer = dein eigener)")
    @app_commands.guild_only()
    async def show_birthday(self, interaction: discord.Interaction, nutzer: discord.Member | None = None) -> None:
        assert interaction.guild_id is not None  # guild_only
        member = nutzer or interaction.user
        row = await self.module.store.of(interaction.guild_id, member.id)
        text = f"{member.mention}: {row['day']}.{row['month']}." if row else \
            f"{member.mention} hat keinen Geburtstag eingetragen."
        await interaction.response.send_message(text, ephemeral=True)
