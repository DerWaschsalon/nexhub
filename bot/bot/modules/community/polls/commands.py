"""/umfrage."""

from __future__ import annotations

import datetime

import discord
from discord import app_commands

from bot.core import ModuleCog
from bot.errors import UserError

from . import parse_answers


class PollsCog(ModuleCog):
    @app_commands.command(name="umfrage", description="Native Discord-Umfrage erstellen")
    @app_commands.describe(
        frage="Die Frage",
        antworten="Antwortmöglichkeiten, durch | getrennt (2–10)",
        dauer_stunden="Wie lange die Umfrage läuft (Stunden, 1–168, Standard 24)",
        mehrfachauswahl="Mehrere Antworten pro Person erlauben (Standard: aus)",
    )
    @app_commands.guild_only()
    async def poll(self, interaction: discord.Interaction, frage: str, antworten: str,
                   dauer_stunden: app_commands.Range[int, 1, 168] = 24, mehrfachauswahl: bool = False) -> None:
        if not isinstance(interaction.channel, discord.abc.Messageable):
            raise UserError("Das geht nur in einem Kanal.")
        survey = discord.Poll(question=frage, duration=datetime.timedelta(hours=dauer_stunden),
                              multiple=mehrfachauswahl)
        for option in parse_answers(antworten):
            survey.add_answer(text=option)
        await interaction.channel.send(poll=survey)
        await interaction.response.send_message("Umfrage gestartet.", ephemeral=True)
