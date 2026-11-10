"""Einstellungen der Run-Posts aus dem NexBoard."""

from pydantic import BaseModel

from bot.core.schema import setting


class RunPostSettings(BaseModel):
    aion_channel: int | None = setting("channel", "Ziel-Kanal", hint="Leer schaltet die Posts ab.")
