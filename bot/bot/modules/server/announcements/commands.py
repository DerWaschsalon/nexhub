"""Slash-Befehle der Ankündigungen."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands

from bot.core import ModuleCog
from bot.core.discord_checks import can_send
from bot.errors import UserError

if TYPE_CHECKING:
    from . import Announcements

MAX_MESSAGE = 2000
PREVIEW = 60


class AnnouncementsCog(ModuleCog):
    module: "Announcements"

    @app_commands.command(name="ankuendigung-erstellen",
                          description="Text alle X Minuten automatisch in einen Kanal posten")
    @app_commands.describe(kanal="Kanal für die Ankündigung", text="Der anzukündigende Text",
                           intervall_minuten="Alle wie viele Minuten gepostet wird (mindestens 5)")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def create(self, interaction: discord.Interaction, kanal: discord.TextChannel, text: str,
                     intervall_minuten: app_commands.Range[int, 5, 10080]) -> None:
        if not can_send(kanal):
            raise UserError(f"Ich darf in {kanal.mention} nicht schreiben.")
        assert interaction.guild_id is not None  # guild_only
        row_id = await self.module.store.add(interaction.guild_id, kanal.id, text, intervall_minuten)
        await interaction.response.send_message(
            f"Ankündigung #{row_id} angelegt: alle {intervall_minuten} Min. in {kanal.mention}.", ephemeral=True)

    @app_commands.command(name="ankuendigungen",
                          description="Alle zeitgesteuerten Ankündigungen dieses Servers anzeigen")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def list_all(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None  # guild_only
        rows = await self.module.store.of_guild(interaction.guild.id)
        if not rows:
            await interaction.response.send_message("Keine Ankündigungen eingerichtet.", ephemeral=True)
            return
        lines = []
        for r in rows:
            channel = interaction.guild.get_channel(r["channel_id"])
            where = channel.mention if channel else "(gelöschter Kanal)"
            lines.append(f"**#{r['id']}** {where} – alle {r['interval_minutes']} Min. – „{r['text'][:PREVIEW]}“")
        await interaction.response.send_message("\n".join(lines)[:MAX_MESSAGE], ephemeral=True)

    @app_commands.command(name="ankuendigung-loeschen", description="Zeitgesteuerte Ankündigung per ID löschen")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def delete(self, interaction: discord.Interaction, ankuendigung_id: int) -> None:
        assert interaction.guild_id is not None  # guild_only
        await self.module.store.delete(interaction.guild_id, ankuendigung_id)
        await interaction.response.send_message(f"Ankündigung #{ankuendigung_id} gelöscht.", ephemeral=True)
