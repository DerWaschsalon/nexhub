"""Einstellungen der Zähler-Kanäle."""

from pydantic import BaseModel

from bot.core.schema import setting

GROUP = "Statistik-Kanäle"


class CounterSettings(BaseModel):
    member_count_channel: int | None = setting("voice", "Mitglieder-Zähler", group=GROUP)
    bots_count_channel: int | None = setting("voice", "Bots-Zähler", group=GROUP)
