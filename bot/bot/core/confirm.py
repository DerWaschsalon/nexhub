"""Rückfrage mit „Ja“ und „Abbrechen“ vor allem, was etwas löscht oder ändert. Nur wer gefragt
wurde, kann antworten."""

from __future__ import annotations

from typing import Any

import discord

TIMEOUT_S = 120


class Confirm(discord.ui.View):
    def __init__(self, author_id: int, label: str) -> None:
        super().__init__(timeout=TIMEOUT_S)
        self.author_id = author_id
        self.confirmed: bool | None = None
        self.confirm.label = label

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Das ist nicht deine Abfrage.", ephemeral=True)
            return False
        return True

    async def accept(self, interaction: discord.Interaction) -> None:
        self.confirmed = True
        await interaction.response.edit_message(content="⏳ Läuft …", view=None, embed=None)
        self.stop()

    @discord.ui.button(style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, _button: discord.ui.Button[Any]) -> None:
        await self.accept(interaction)

    @discord.ui.button(label="Abbrechen", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, _button: discord.ui.Button[Any]) -> None:
        self.confirmed = False
        await interaction.response.edit_message(content="Abgebrochen.", view=None, embed=None)
        self.stop()
