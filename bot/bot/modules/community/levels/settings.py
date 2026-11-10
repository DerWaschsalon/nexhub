"""Einstellungen des Levelsystems (auch die XP für Sprachzeit)."""

from pydantic import BaseModel

from bot.core import IdList
from bot.core.schema import setting

BASICS = "Grundeinstellungen"


class LevelSettings(BaseModel):
    level_system_enabled: bool = setting("bool", "Levelsystem an", False, group=BASICS)
    level_announce_channel: int | None = setting("channel", "Kanal für Level-Up-Nachrichten", group=BASICS,
                                                 hint="Leer: im Kanal der Nachricht.")
    voice_xp_per_minute: int = setting("int", "XP pro Minute Sprachzeit", 0, group=BASICS, hint="0 = aus",
                                       minimum=0, zero_is_off=True)
    level_no_xp_channels: IdList = setting("channels", "Kanäle ohne XP", [], group="Ausnahmen")
    level_no_xp_roles: IdList = setting("roles", "Rollen ohne XP", [], group="Ausnahmen")
