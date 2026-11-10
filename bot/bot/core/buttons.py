"""Knopf, der beim Klick eine übergebene Funktion aufruft.

discord.py erwartet dafür eine Unterklasse mit eigener callback-Methode; Views, die ihre Knöpfe erst
zur Laufzeit zusammenstellen (je nach Zustand andere Beschriftung), sparen sich so je eine Klasse.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import discord

ClickHandler = Callable[[discord.Interaction], Awaitable[Any]]


class ActionButton(discord.ui.Button[discord.ui.View]):
    def __init__(self, handler: ClickHandler, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.handler = handler

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.handler(interaction)
