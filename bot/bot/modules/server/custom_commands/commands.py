"""Slash-Befehle zum Anlegen, Löschen und Anzeigen eigener Befehle."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands

from bot.core import ModuleCog

if TYPE_CHECKING:
    from . import CustomCommands

MAX_MESSAGE = 2000


class CustomCommandsCog(ModuleCog):
    module: "CustomCommands"

    @app_commands.command(name="befehl-erstellen", description="Eigenen Befehl !name anlegen oder überschreiben")
    @app_commands.describe(name="Name ohne „!“, nur a-z 0-9 _ - (höchstens 32 Zeichen)",
                           antwort="Antworttext. Platzhalter: {user} (Erwähnung), {server}")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def create(self, interaction: discord.Interaction, name: str, antwort: str) -> None:
        assert interaction.guild_id is not None  # guild_only
        name = await self.module.store.put(interaction.guild_id, name, antwort)
        await interaction.response.send_message(f"`!{name}` gespeichert.", ephemeral=True)

    @app_commands.command(name="befehl-loeschen", description="Eigenen Befehl wieder löschen")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def delete(self, interaction: discord.Interaction, name: str) -> None:
        assert interaction.guild_id is not None  # guild_only
        name = await self.module.store.delete(interaction.guild_id, name)
        await interaction.response.send_message(f"`!{name}` gelöscht.", ephemeral=True)

    @app_commands.command(name="befehle", description="Alle eigenen Befehle dieses Servers anzeigen")
    @app_commands.guild_only()
    async def list_all(self, interaction: discord.Interaction) -> None:
        assert interaction.guild_id is not None  # guild_only
        rows = await self.module.store.of_guild(interaction.guild_id)
        if not rows:
            await interaction.response.send_message("Es gibt noch keine eigenen Befehle.", ephemeral=True)
            return
        names = ", ".join(f"`!{r['name']}`" for r in rows)
        await interaction.response.send_message(names[:MAX_MESSAGE], ephemeral=True)
