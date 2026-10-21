"""Dungeon-Namen, die A2Tools (src/data/i18n/dungeons/en.json) nicht kennt.

Der Daemon nimmt Namen aus den A2Tools-Daten und schreibt sonst „Dungeon <ID>“. Diese Tabelle
füllt die Lücken, englisch wie dort. Nachtragen, sobald ein Run mit unbekannter ID auftaucht
(Name über die Bosse herausfinden); fällt weg, sobald A2Tools die ID selbst führt.
"""
from __future__ import annotations

EXTRA_DUNGEONS: dict[int, str] = {
    610062: "Shattered Arkanis",    # Siliator of Deceit, Ruthilis of Pain, Talisra of the Void
    910034: "Sanctum of Loathing",  # Ascension Trial: Featherstorm Duduri, Watchful Raptor Dodori
}


def dungeon_label(dungeon_id: int, name: str) -> str:
    """Anzeigename: der mitgeschickte Name, außer er ist der Platzhalter „Dungeon <ID>“."""
    if name == f"Dungeon {dungeon_id}":
        return EXTRA_DUNGEONS.get(dungeon_id, name)
    return name
