"""Knöpfe und Formular der Tickets."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import discord

from . import CLOSE_ID, KINDS, PANEL_PREFIX

if TYPE_CHECKING:
    from . import Tickets

MAX_TEXT = 1000


class TicketPanelView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)
        for key, (emoji, label, _) in KINDS.items():
            self.add_item(discord.ui.Button(label=label, emoji=emoji, style=discord.ButtonStyle.secondary,
                                            custom_id=f"{PANEL_PREFIX}{key}"))


class TicketCloseView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label="Schließen", emoji="🔒", style=discord.ButtonStyle.danger,
                                        custom_id=CLOSE_ID))


class TicketModal(discord.ui.Modal):
    def __init__(self, module: "Tickets", kind: str) -> None:
        emoji, label, field_label = KINDS[kind]
        super().__init__(title=f"{emoji} {label}")
        self.module, self.kind = module, kind
        self.text: discord.ui.TextInput[Any] = discord.ui.TextInput(label=field_label,
                                                                    style=discord.TextStyle.paragraph,
                                                                    max_length=MAX_TEXT)
        self.add_item(self.text)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.module.open(interaction, self.kind, str(self.text.value))
