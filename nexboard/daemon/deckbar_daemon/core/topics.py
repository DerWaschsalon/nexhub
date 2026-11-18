"""Themen auf dem Bus, über die Module miteinander reden, ohne sich gegenseitig zu importieren."""
from __future__ import annotations

from dataclasses import dataclass

SCHEDULE = "schedule.entries"  # sichtbare Termine (Liste von Zeilen aus Schedule.visible), fürs Overlay
LANGUAGE = "settings.language"  # Sprache der allgemeinen Einstellungen hat sich geändert (Inhalt: Kürzel)
GAME_STARTED = "game.started"  # von nexcore.GameWatch (Inhalt: Name des Spiels, z. B. "poe1")
GAME_STOPPED = "game.stopped"
POE_LOG = "poe.log"  # neue Zeile aus einem Client.txt (Inhalt: poe.session.PoeLogMessage)
DECK_PAGE = "deck.page"  # ein Modul möchte eine Seite der Leiste zeigen (Inhalt: Seiten-ID, None = nicht mehr)
TILE_EVENT = "deck.tile"  # Tippen auf eine Kachel, die einem Modul gehört (Inhalt: TileEvent)


@dataclass(frozen=True)
class TileEvent:
    """Tippen auf eine Kachel mit eigenem Typ (dps, guide …): das Modul des Typs entscheidet, was passiert."""
    item_type: str
    item_id: str
    event: str  # button_press | long_press
    part: str | None  # Teil der Kachel (z. B. "reset", "next")
