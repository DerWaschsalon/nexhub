"""Einstellungen der Musikwiedergabe."""

from pydantic import BaseModel

from bot.core.schema import setting


class PlayerSettings(BaseModel):
    dj_role: int | None = setting("role", "DJ-Rolle", group="Musik & Voice",
                                  hint="Leer: alle dürfen die Musik steuern.")
