"""Knöpfe unter „Läuft gerade“, mit derselben Rechteprüfung wie die Befehle."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import discord

from bot.errors import UserError

from .player import LOOP_LABELS

if TYPE_CHECKING:
    from . import MusicPlayer


class PlayerView(discord.ui.View):
    def __init__(self, module: "MusicPlayer") -> None:
        super().__init__(timeout=None)
        self.module = module

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item[Any]) -> None:
        text = str(error) if isinstance(error, UserError) else "Das hat nicht geklappt."
        await interaction.response.send_message(text, ephemeral=True)

    @discord.ui.button(emoji="⏯️", style=discord.ButtonStyle.secondary)
    async def pause(self, interaction: discord.Interaction, _button: discord.ui.Button[Any]) -> None:
        player = self.module.require_player(interaction)
        vc = player.voice()
        if vc and vc.is_paused():
            vc.resume()
        elif vc and vc.is_playing():
            vc.pause()
        await interaction.response.defer()

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary)
    async def skip(self, interaction: discord.Interaction, _button: discord.ui.Button[Any]) -> None:
        self.module.require_player(interaction, control=True).skip()
        await interaction.response.defer()

    @discord.ui.button(emoji="⏹️", style=discord.ButtonStyle.danger)
    async def stop_playing(self, interaction: discord.Interaction, _button: discord.ui.Button[Any]) -> None:
        player = self.module.require_player(interaction, control=True)
        await interaction.response.defer()
        await self.module.disconnect(player.guild)

    @discord.ui.button(emoji="🔁", style=discord.ButtonStyle.secondary)
    async def loop(self, interaction: discord.Interaction, _button: discord.ui.Button[Any]) -> None:
        player = self.module.require_player(interaction)
        order = list(LOOP_LABELS)
        player.loop = order[(order.index(player.loop) + 1) % len(order)]
        await interaction.response.edit_message(embed=player.np_embed())

    @discord.ui.button(emoji="📜", style=discord.ButtonStyle.secondary)
    async def show_queue(self, interaction: discord.Interaction, _button: discord.ui.Button[Any]) -> None:
        player = self.module.players.get(interaction.guild_id or 0)
        await interaction.response.send_message(embed=self.module.queue_embed(player), ephemeral=True)
