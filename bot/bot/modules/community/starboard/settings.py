"""Einstellungen des Starboards."""

from pydantic import BaseModel

from bot.core.schema import setting


class StarboardSettings(BaseModel):
    starboard_channel: int | None = setting("channel", "Highlight-Kanal", group="Starboard")
    starboard_threshold: int = setting("int", "Schwelle (Sterne, ohne den des Autors)", 3, group="Starboard",
                                       minimum=1)
