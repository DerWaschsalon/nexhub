"""Einstellungen der Geburtstagsgrüße."""

from pydantic import BaseModel

from bot.core.schema import setting


class BirthdaySettings(BaseModel):
    birthday_channel: int | None = setting("channel", "Kanal für die Gratulation um 9 Uhr", group="Geburtstage",
                                           hint="Mitglieder tragen ihren Geburtstag per /geburtstag-setzen ein.")
