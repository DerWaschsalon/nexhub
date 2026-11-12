"""/poe preis: aktueller Preis eines Gegenstands aus dem NexHub, Vorschläge beim Tippen."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from bot.core import HubClient, ModuleCog
from bot.errors import UserError

from .embeds import GAME_LABELS, price_embed

if TYPE_CHECKING:
    from . import PoePrices

PRICE_PATH = "/api/internal/poe/price"
COMPLETE_PATH = "/api/internal/poe/complete"
NOT_CONNECTED = "NexHub nicht verbunden."
MAX_CHOICES = 25  # Discords Grenze für Vorschläge
MAX_CHOICE_TEXT = 100
DEFAULT_GAME = "poe1"  # solange beim Tippen noch kein Spiel gewählt ist
GAME_CHOICES = [app_commands.Choice(name=label, value=game) for game, label in GAME_LABELS.items()]


class PoeCog(commands.GroupCog, ModuleCog, group_name="poe", group_description="Path of Exile"):
    module: "PoePrices"

    def hub(self) -> HubClient:
        if self.module.hub is None:
            raise UserError(NOT_CONNECTED)
        return self.module.hub

    @app_commands.command(name="preis", description="Aktueller Preis eines Gegenstands (poe.ninja)")
    @app_commands.describe(spiel="Path of Exile 1 oder 2", item="Name des Gegenstands, Vorschläge beim Tippen")
    @app_commands.choices(spiel=GAME_CHOICES)
    async def price(self, interaction: discord.Interaction, spiel: app_commands.Choice[str],
                    item: app_commands.Range[str, 1, 100]) -> None:
        hub = self.hub()
        # Discord wartet nur 3 s auf eine Antwort, der Hub darf bis zu 10 s brauchen
        await interaction.response.defer()
        data = await hub.get(PRICE_PATH, {"game": spiel.value, "q": item})
        if data is None:
            raise UserError(f"Zu „{item}“ gibt es in {spiel.name} keinen Preis.")
        await interaction.followup.send(embed=price_embed(data, spiel.value))

    @price.autocomplete("item")
    async def price_autocomplete(self, interaction: discord.Interaction,
                                 current: str) -> list[app_commands.Choice[str]]:
        game = getattr(interaction.namespace, "spiel", None) or DEFAULT_GAME
        try:
            names = await self.hub().get(COMPLETE_PATH, {"game": game, "q": current})
        except UserError:
            return []  # Vorschläge sind nur eine Hilfe, ohne Hub bleibt die Liste leer
        # Der Hub hält Discords Grenzen schon ein, hier nur zur Sicherheit
        shown = [name[:MAX_CHOICE_TEXT] for name in (names or [])[:MAX_CHOICES]]
        return [app_commands.Choice(name=name, value=name) for name in shown]
