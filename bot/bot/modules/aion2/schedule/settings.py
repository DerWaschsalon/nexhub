"""Einstellungen der Termin-Tafel."""

from pydantic import BaseModel

from bot.core.schema import setting

GROUP = "Termin-Tafel"
DEFAULT_LEAD_MIN = 5


class ScheduleSettings(BaseModel):
    termine_channel: int | None = setting(
        "channel", "Kanal für die Termin-Tafel", group=GROUP,
        hint="Riss, Shugo-Fest, Beritra, Kaira, Resets, Belagerung und Nahma, aktualisiert sich jede Minute. "
             "Leer schaltet sie ab.")
    termine_role: int | None = setting("role", "Rolle, die vorher gepingt wird", group=GROUP,
                                       hint="Leer: nur die Tafel, kein Ping.")
    termine_lead_minutes: int = setting("int", "Ping so viele Minuten vorher", DEFAULT_LEAD_MIN, group=GROUP,
                                        minimum=1)
    termine_events: bool = setting(
        "bool", "Belagerung und Nahma als Discord-Events", False, group=GROUP,
        hint="Legt die Wochentermine sieben Tage im Voraus im Event-Kalender des Servers an. Der Bot braucht "
             "dafür das Recht „Events verwalten“.")
    # Zustand, keine Einstellung: die eigene Nachricht der Tafel, ihr Kanal und die schon gepingten Termine
    termine_message: int | None = None
    termine_message_channel: int | None = None
    termine_announced: str = ""  # „Schlüssel@Beginn“, durch Komma getrennt: überlebt einen Neustart des Bots
