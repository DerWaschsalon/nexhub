"""/erinnere, /erinnerungen, /erinnerung-loeschen."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import discord
from discord import app_commands

from bot.core import ModuleCog
from bot.core.clock import TZ
from bot.core.when import parse_when

if TYPE_CHECKING:
    from . import Reminders

MAX_MESSAGE = 2000


class RemindersCog(ModuleCog):
    module: "Reminders"

    @app_commands.command(name="erinnere", description="Erinnerung setzen")
    @app_commands.describe(wann="z. B. 2h, 30m, 1d2h, 18:30, 24.12. 18:00", text="Woran erinnert werden soll",
                           privat="Per DM statt im Kanal (Standard: aus)")
    @app_commands.guild_only()
    async def remind(self, interaction: discord.Interaction, wann: str, text: str, privat: bool = False) -> None:
        assert interaction.guild_id is not None and interaction.channel_id is not None  # guild_only
        due = parse_when(wann, datetime.now(TZ))
        await self.module.store.add(interaction.guild_id, interaction.channel_id, interaction.user.id, text,
                                    due.timestamp(), privat)
        await interaction.response.send_message(
            f"Erinnere dich {discord.utils.format_dt(due, 'R')} ({discord.utils.format_dt(due, 'f')})"
            f"{' per DM' if privat else ''}: {text}", ephemeral=True)

    @app_commands.command(name="erinnerungen", description="Deine offenen Erinnerungen anzeigen")
    @app_commands.guild_only()
    async def list_own(self, interaction: discord.Interaction) -> None:
        assert interaction.guild_id is not None  # guild_only
        rows = await self.module.store.of_user(interaction.guild_id, interaction.user.id)
        if not rows:
            await interaction.response.send_message("Du hast keine offenen Erinnerungen.", ephemeral=True)
            return
        lines = [f"**#{r['id']}** {discord.utils.format_dt(datetime.fromtimestamp(r['due'], tz=TZ), 'R')} – "
                 f"{r['text']}" for r in rows]
        await interaction.response.send_message("\n".join(lines)[:MAX_MESSAGE], ephemeral=True)

    @app_commands.command(name="erinnerung-loeschen",
                          description="Eigene Erinnerung per ID löschen (siehe /erinnerungen)")
    @app_commands.guild_only()
    async def delete_own(self, interaction: discord.Interaction, erinnerung_id: int) -> None:
        assert interaction.guild_id is not None  # guild_only
        await self.module.store.delete_own(interaction.guild_id, interaction.user.id, erinnerung_id)
        await interaction.response.send_message(f"Erinnerung #{erinnerung_id} gelöscht.", ephemeral=True)
