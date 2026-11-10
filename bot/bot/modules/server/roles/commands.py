"""Slash-Befehl des Rollen-Panels."""

from __future__ import annotations

import discord
from discord import app_commands

from bot.core import ModuleCog
from bot.errors import UserError

from . import PanelView, panel_embed, parse_roles

DEFAULT_TEXT = "Klick auf einen Button, um die Rolle zu nehmen oder abzugeben."


class RolesCog(ModuleCog):
    @app_commands.command(name="rollen-panel",
                          description="Nachricht mit Buttons, über die man sich Rollen selbst gibt")
    @app_commands.describe(
        rollen="Rollen erwähnen, optional mit Emoji davor, z. B. „🎮 @Gamer 🎵 @Musik“",
        titel="Überschrift",
        text="Beschreibung unter der Überschrift",
    )
    @app_commands.default_permissions(manage_roles=True)
    @app_commands.guild_only()
    async def panel(self, interaction: discord.Interaction, rollen: str, titel: str = "Rollen",
                    text: str = DEFAULT_TEXT) -> None:
        if interaction.guild is None or not isinstance(interaction.channel, discord.abc.Messageable):
            raise UserError("Das geht nur in einem Kanal eines Servers.")
        roles, emojis = parse_roles(interaction.guild, rollen)
        await interaction.channel.send(embed=panel_embed(titel, text, roles, emojis), view=PanelView(roles, emojis))
        await interaction.response.send_message("Panel erstellt.", ephemeral=True)
