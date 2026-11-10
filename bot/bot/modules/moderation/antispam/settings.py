"""Einstellungen des Spamschutzes."""

from pydantic import BaseModel

from bot.core.schema import setting


class AntispamSettings(BaseModel):
    antispam: bool = setting("bool", "Spamschutz aktiv", True, group="Moderation")
    allow_invites: bool = setting("bool", "Einladungslinks erlauben", False, group="Moderation")
