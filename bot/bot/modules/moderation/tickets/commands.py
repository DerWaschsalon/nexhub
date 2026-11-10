"""/ticket-panel."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands

from bot.core import ModuleCog
from bot.errors import UserError

from . import KINDS
from .views import TicketPanelView

if TYPE_CHECKING:
    from . import Tickets

DEFAULT_TEXT = "Klick auf einen Button, um ein Ticket zu eröffnen."


class TicketsCog(ModuleCog):
    module: "Tickets"

    @app_commands.command(name="ticket-panel", description="Panel posten, über das Mitglieder Tickets eröffnen können")
    @app_commands.describe(titel="Überschrift", text="Beschreibung unter der Überschrift")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def panel(self, interaction: discord.Interaction, titel: str = "Support", text: str = DEFAULT_TEXT) -> None:
        if interaction.guild is None or not isinstance(interaction.channel, discord.abc.Messageable):
            raise UserError("Das geht nur in einem Kanal eines Servers.")
        if not self.module.team(interaction.guild):
            raise UserError("Erst eine Team-Rolle einrichten: `/setup panel` → Tickets.")
        e = discord.Embed(title=titel, description=text.replace("\\n", "\n"), colour=discord.Colour.blurple())
        e.add_field(name="Optionen", value="\n".join(f"{emoji} {label}" for emoji, label, _ in KINDS.values()))
        await interaction.channel.send(embed=e, view=TicketPanelView())
        await interaction.response.send_message("Panel erstellt.", ephemeral=True)
