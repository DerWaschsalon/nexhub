"""Einstellungen der Begrüßung neuer Mitglieder."""

from pydantic import BaseModel

from bot.core.schema import setting

DEFAULT_WELCOME = "Willkommen auf **{server}**, {user}! Schau dich in Ruhe um."


class WelcomeSettings(BaseModel):
    welcome_channel: int | None = setting("channel", "Willkommenskanal", group="Willkommen")
    welcome_text: str = setting("textarea", "Begrüßungstext", "", group="Willkommen",
                                hint="Platzhalter: {user} {name} {server} {anzahl}")
    autorole: int | None = setting("role", "Autorolle", group="Willkommen",
                                   hint="Wird sofort beim Beitritt vergeben, z. B. „Neuling“.")
