"""Einstellungen der Termin-Tafel."""

from pydantic import BaseModel

from bot.core.schema import setting

GROUP = "Termin-Tafel"


class ScheduleSettings(BaseModel):
    termine_channel: int | None = setting(
        "channel", "Kanal für die Termin-Tafel", group=GROUP,
        hint="Riss, Shugo-Fest, Beritra, Kaira und Resets, aktualisiert sich jede Minute. Leer schaltet sie ab.")
    termine_role: int | None = setting("role", "Rolle, die 5 Minuten vorher gepingt wird", group=GROUP,
                                       hint="Leer: nur die Tafel, kein Ping.")
    # Zustand, keine Einstellung: die eigene Nachricht der Tafel und ihr Kanal
    termine_message: int | None = None
    termine_message_channel: int | None = None
