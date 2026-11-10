"""Embed-Ersteller: /embed-erstellen öffnet ein Formular und postet das fertige Embed in einen Kanal,
ohne JSON oder fremde Werkzeuge."""

from __future__ import annotations

from typing import ClassVar

import discord
from discord.ext import commands
from nexcore import ModuleInfo

from bot.core import BotModule
from bot.errors import UserError


def parse_colour(raw: str | None) -> discord.Colour:
    if not raw:
        return discord.Colour.blurple()
    try:
        return discord.Colour(int(raw.strip().lstrip("#"), 16))
    except ValueError:
        raise UserError(f"„{raw}“ ist keine gültige Hex-Farbe, z. B. `#5865F2`.") from None


def build_embed(title: str, description: str, colour: str, image_url: str) -> discord.Embed:
    if not title and not description:
        raise UserError("Gib mindestens Titel oder Beschreibung an.")
    embed = discord.Embed(title=title or None, description=description or None, colour=parse_colour(colour or None))
    if image_url:
        embed.set_image(url=image_url)
    return embed


class Embeds(BotModule):
    info: ClassVar[ModuleInfo] = ModuleInfo(
        id="server.embeds", name="Embed-Ersteller", category="Server", icon="mdi-card-text",
        summary="Eigenes Embed per Formular erstellen und posten.",
    )

    def cog(self) -> commands.Cog:
        from .commands import EmbedsCog

        return EmbedsCog(self)
