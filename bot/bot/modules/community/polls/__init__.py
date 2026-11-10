"""Umfragen: native Discord-Umfragen per Slash-Befehl, ohne eigenes Knopf- oder Reaktionssystem."""

from __future__ import annotations

from typing import ClassVar

from discord.ext import commands
from nexcore import ModuleInfo

from bot.core import BotModule
from bot.errors import UserError

MIN_ANSWERS, MAX_ANSWERS = 2, 10  # Discords Grenzen für eine Umfrage
MAX_ANSWER_LENGTH = 55


def parse_answers(raw: str) -> list[str]:
    """Antworten aus „Ja | Nein | Vielleicht“."""
    options = [a.strip() for a in raw.split("|") if a.strip()]
    if not MIN_ANSWERS <= len(options) <= MAX_ANSWERS:
        raise UserError(f"Gib {MIN_ANSWERS} bis {MAX_ANSWERS} Antworten an, durch `|` getrennt.")
    for option in options:
        if len(option) > MAX_ANSWER_LENGTH:
            raise UserError(f"„{option}“ ist zu lang (höchstens {MAX_ANSWER_LENGTH} Zeichen pro Antwort).")
    return options


class Polls(BotModule):
    info: ClassVar[ModuleInfo] = ModuleInfo(
        id="community.polls", name="Umfragen", category="Community", icon="mdi-poll",
        summary="Native Discord-Umfragen mit 2 bis 10 Antworten.",
    )

    def cog(self) -> commands.Cog:
        from .commands import PollsCog

        return PollsCog(self)
