"""Einstellungen der Path-of-Exile-Preise."""

from pydantic import BaseModel

from bot.core.schema import setting


class PoeSettings(BaseModel):
    poe_channel: int | None = setting("channel", "Kanal für Preisalarme und Tagespost", group="Path of Exile",
                                      hint="Leer schaltet beides ab.")
