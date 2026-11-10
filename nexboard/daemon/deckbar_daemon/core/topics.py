"""Themen auf dem Bus, über die Module miteinander reden, ohne sich gegenseitig zu importieren."""

DPS_RESET = "dps.reset"  # Reset-Knopf der DPS-Kachel
SCHEDULE = "schedule.entries"  # sichtbare Termine (Liste von Zeilen aus Schedule.visible), fürs Overlay
LANGUAGE = "settings.language"  # Sprache der allgemeinen Einstellungen hat sich geändert (Inhalt: Kürzel)
