"""Einstellungen der eigenen Sprachkanäle („Join to create“)."""

from pydantic import BaseModel

from bot.core.schema import setting


class TempVoiceSettings(BaseModel):
    tempvoice_hub: int | None = setting("voice", "Temp-Voice-Kanal", group="Musik & Voice",
                                        hint="Neu anlegen geht genauer per /setup temp-voice in Discord.")
